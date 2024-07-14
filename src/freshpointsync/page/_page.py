import asyncio
import logging
from concurrent.futures import ProcessPoolExecutor
from functools import cached_property
from typing import (
    Any,
    Callable,
    Dict,
    Iterable,
    List,
    NamedTuple,
    Optional,
    Tuple,
    Type,
    TypeVar,
    Union,
)

from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel

from ..client._client import ProductDataFetchClient
from ..parser._parser import (
    ProductFinder,
    hash_text,
    normalize_text,
    parse_page_contents,
)
from ..product._product import Product
from ..runner._runner import CallableRunner
from ..update._update import (
    Handler,
    ProductCacheUpdater,
    ProductUpdateEvent,
    ProductUpdateEventPublisher,
)

logger = logging.getLogger('freshpointsync.page')
"""Logger for the `freshpointsync.page` package."""


class FetchInfo(NamedTuple):
    """Named tuple for a product page fetch information."""

    contents: Optional[str]
    """The fetched contents of the product page."""
    contents_hash: Optional[str]
    """The SHA-256 hash of the fetched contents."""
    is_updated: bool
    """Flag indicating whether the contents have been updated."""


class ProductPageData(BaseModel):
    """Data model of a product page."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    location_id: int = Field(frozen=True)
    """ID of the product location."""
    html_hash: str = Field(default='')
    """SHA-256 hash of the HTML contents of the product page."""
    products: Dict[int, Product] = Field(default={}, repr=False, frozen=True)
    """Dictionary of products' IDs and data models on the page."""

    @cached_property
    def url(self) -> str:
        """URL of the product page."""
        return ProductDataFetchClient.get_page_url(self.location_id)

    @property  # not cached because products may be missing upon initialization
    def location(self) -> str:
        """Name of the product location. Infers from the first product in
        the products dictionary. If the dictionary is empty, returns an empty
        string.
        """
        for product in self.products.values():
            return product.location
        return ''

    @property  # not cached because "location" is not cached
    def location_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the location name."""
        return normalize_text(self.location)

    @property
    def product_names(self) -> List[str]:
        """List of string product names on the page."""
        return [p.name for p in self.products.values() if p.name]

    @property
    def product_categories(self) -> List[str]:
        """List of string product categories on the page."""
        categories = []
        for p in self.products.values():
            if p.category and p.category not in categories:
                categories.append(p.category)
        return categories


TProductPage = TypeVar('TProductPage', bound='ProductPage')


class ProductPage:
    """Product page object that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        location_id: Optional[int] = None,
        data: Optional[ProductPageData] = None,
        client: Optional[ProductDataFetchClient] = None,
    ) -> None:
        """Initializes a new product page object.

        Args:
            location_id (Optional[int], optional): ID of the product location
                (product page). Defaults to None.
            data (Optional[ProductPageData], optional): Data model of the
                product page to be used as the initial cached state. Defaults
                to None.
            client (Optional[ProductDataFetchClient], optional): Client for
                fetching product data. Defaults to None.
        """
        self._data = self._validate_data(location_id, data)
        self._client = client or ProductDataFetchClient()
        self._publisher = ProductUpdateEventPublisher()
        self._runner = CallableRunner(executor=None)
        self._update_forever_task: Optional[asyncio.Task] = None
        self._updater = ProductCacheUpdater(
            self._data.products, self._publisher
        )

    def __str__(self) -> str:
        """String representation of the product page object."""
        return self._data.url

    def __repr__(self) -> str:
        """String representation of the product page object instantiation."""
        cls_name = self.__class__.__name__
        return f'{cls_name}(location_id={self._data.location_id})'

    async def __aenter__(self: TProductPage) -> TProductPage:
        """Asynchronous context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[object],
    ) -> None:
        """Asynchronous context manager exit."""
        await self.close_session()

    @staticmethod
    def _validate_data(
        location_id: Optional[int] = None,
        data: Optional[ProductPageData] = None,
    ) -> ProductPageData:
        """Validates the product page data and location ID.

        Args:
            location_id (Optional[int], optional): ID of the product location.
                Defaults to None.
            data (Optional[ProductPageData], optional): Data model of the
                product page. Defaults to None.

        Raises:
            ValueError: If both location ID and data are None or
                if location ID provided explicitly does not match the location
                ID inferred from the data model.

        Returns:
            ProductPageData: Validated product page data model.
        """
        if data is None:
            if location_id is None:
                raise ValueError('Location ID is required')
            return ProductPageData(location_id=location_id)
        if location_id is not None and location_id != data.location_id:
            raise ValueError('Location ID mismatch')
        return data

    async def start_session(self) -> None:
        """Start an aiohttp client session if one is not already started."""
        await self._client.start_session()

    async def close_session(self) -> None:
        """Close the aiohttp client session if one is open."""
        await self._client.close_session()
        await self.cancel_update_forever_task()
        await self.cancel_update_handlers()
        if self._runner.executor:
            self._runner.executor.shutdown(wait=True)

    @property
    def data(self) -> ProductPageData:
        """Product page data model."""
        return self._data  # copy is not necessary because fields are frozen

    @property
    def context(self) -> Dict[Any, Any]:
        """Product page context data."""
        return self._publisher.context

    @property
    def client(self) -> ProductDataFetchClient:
        """Product data fetch client."""
        return self._client

    async def set_client(self, client: ProductDataFetchClient) -> None:
        """Set the product data fetch client.

        This method is asynchronous and closes the current session if there is
        an active session.

        Args:
            client (ProductDataFetchClient): The new product data fetch client.
        """
        if not self._client.is_session_closed:
            await self.client.close_session()
        self._client = client

    def subscribe_for_update(
        self,
        handler: Handler,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
        call_safe: bool = True,
        call_blocking: bool = True,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None,
    ) -> None:
        """Subscribe a handler to specific product update event(s). The handler
        will be invoked when the event is posted, with the event context
        passed as an argument.

        The handler can be an asynchronous function, method, or any callable
        object that accepts exactly one argument (a `ProductUpdateContext`
        object) and returns `None` or a coroutine that resolves to `None`.

        Args:
            handler (Handler): The function or callable to invoke for
                the event(s).
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.
            call_safe (bool, optional): If True, exceptions raised by
                the handler are caught and logged. If False, exceptions are
                propagated and must be handled by the caller. Defaults to True.
            call_blocking (bool, optional): If True, the synchronous handler
                is executed in a blocking manner, i.e., called directly without
                using an executor. If False, the synchronous handler is executed
                in a non-blocking manner in a separate thread. Asynchronous
                handlers are always executed in a non-blocking manner, this
                parameter has no effect on them. Defaults to True.
            handler_done_callback (Optional[Callable[[asyncio.Future], Any]]):
                Optional function to be called when the handler completes
                execution. Depending on the type of the handler, the callback
                receives an `asyncio.Task` or `asyncio.Future` object as its
                argument, which represents the return value of the callback
                execution. Defaults to None.

        Raises:
            TypeError: If the handler does not have a valid signature.
        """
        self._publisher.subscribe(
            handler, event, call_safe, call_blocking, handler_done_callback
        )

    def unsubscribe_from_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
    ) -> None:
        """Unsubscribe a handler from specific product update event(s),
        or all handlers if no specific handler is provided. The unsubscribed
        handler will no longer be invoked when the event is posted.

        Args:
            handler (Handler): The handler to be unsubscribed from the
                event(s). if None, all handlers for the event are unsubscribed.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.
        """
        self._publisher.unsubscribe(handler, event)

    def is_subscribed_for_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
    ) -> bool:
        """Check if there are any subscribers for the given event(s).

        Args:
            handler (Optional[Handler], optional): The handler to check for
                subscription. If None, all handlers are checked.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.

        Returns:
            bool: True if there are subscribers for the event, False otherwise.
        """
        return self._publisher.is_subscribed(handler, event)

    async def _fetch_contents(self) -> FetchInfo:
        """Fetch the HTML contents of the product page.

        Returns:
            FetchInfo: Named tuple containing the fetched HTML contents,
                the hash of the contents, and a flag indicating whether
                the contents have been updated.
        """
        is_updated: bool = False
        try:
            contents = await self._runner.run_async(
                self._client.fetch, self._data.location_id
            )
        except asyncio.CancelledError:
            return FetchInfo(None, None, is_updated)
        if not contents:
            return FetchInfo(None, None, is_updated)
        contents_hash = hash_text(contents)
        if contents_hash != self.data.html_hash:
            is_updated = True
            # do not update the html data hash attribute value here because
            # fetching is not supposed to modify the inner state of the page
        return FetchInfo(contents, contents_hash, is_updated)

    async def _parse_contents(self, contents: str) -> Tuple[Product, ...]:
        """Parse the contents of the product page and extract product data.

        The blocking synchronous parsing function is executed in a separate
        thread or process to avoid blocking the event loop.

        Args:
            contents (str): The HTML contents of the product page.

        Returns:
            tuple[Product]: Tuple of product data extracted from the contents.
        """
        if not contents:
            return tuple()
        try:
            products = await self._runner.run_sync(
                parse_page_contents,
                contents,
                run_safe=False,  # run_safe=True crashes ProcessPoolExecutor
                run_blocking=False,
            )
        except asyncio.CancelledError:
            raise
        except Exception:
            return tuple()
        return products or tuple()

    async def _update_products(
        self,
        products: Iterable[Product],
        html_hash: str,
        silent: bool,
        await_handlers: bool,
        **kwargs: Any,
    ) -> None:
        """Update the internal state of the product page with the new product
        data. Optionally trigger and await event handlers.

        Args:
            products (Iterable[Product]): An iterable of product data to update.
            html_hash (str): The SHA-256 hash of the HTML contents of the page.
            silent (bool): If True, the product data is updated without
                triggering any event handlers.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        self.data.html_hash = html_hash
        if silent:
            self._updater.update_silently(products)
        else:
            await self._updater.update(products, await_handlers, **kwargs)

    async def fetch(self) -> List[Product]:
        """Fetch the contents of the product page and extract the product data.
        This method does not update the internal state of the page, nor does it
        trigger any event handlers.

        Returns:
            list[Product]: List of product data extracted from the contents.
        """
        fetch_info = await self._fetch_contents()
        if fetch_info.is_updated:
            assert fetch_info.contents is not None, 'Invalid contents'
            products = await self._parse_contents(fetch_info.contents)
            return [product for product in products]
        else:
            return [product for product in self._data.products.values()]

    async def update(
        self, silent: bool = False, await_handlers: bool = False, **kwargs: Any
    ) -> None:
        """Fetch the contents of the product page, extract the product data,
        update the internal state of the page, and trigger event handlers.

        Args:
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        fetch_info = await self._fetch_contents()
        if fetch_info.is_updated:
            assert fetch_info.contents is not None, 'Invalid contents'
            assert fetch_info.contents_hash is not None, 'Invalid hash'
            products = await self._parse_contents(fetch_info.contents)
            await self._update_products(
                products,
                fetch_info.contents_hash,
                silent,
                await_handlers,
                **kwargs,
            )

    async def update_forever(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        silent: bool = False,
        **kwargs: Any,
    ) -> None:
        """Update the product page at regular intervals.

        This method is a coroutine that runs indefinitely, updating
        the product page at regular intervals.

        Args:
            interval (float, optional): The time interval in seconds between
                updates. Defaults to 10.0.
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        while True:
            try:
                await self.update(await_handlers, silent, **kwargs)
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)

    def init_update_forever_task(
        self,
        interval: float = 10.0,
        silent: bool = False,
        await_handlers: bool = False,
        **kwargs: Any,
    ) -> asyncio.Task:
        """Initialize the update forever task. If the task is already running,
        the method does nothing.

        This method is not a coroutine. It creates a new task from
        the `update_forever` coroutine with the `asyncio.create_task` function.
        The task is stored internally and can be cancelled with
        the `cancel_update_forever` method.

        Args:
            interval (float, optional): The time interval in seconds between
                updates. Defaults to 10.0.
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.

        Returns:
            asyncio.Task: The task object created by `asyncio.create_task`.
        """
        task = self._update_forever_task
        if task is None or task.done():
            task = asyncio.create_task(
                self.update_forever(interval, silent, await_handlers, **kwargs)
            )
            self._update_forever_task = task
        return task

    async def cancel_update_forever_task(self) -> None:
        """Cancel the update forever task if it is running."""
        if self._update_forever_task:
            if not self._update_forever_task.done():
                task = self._update_forever_task
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._update_forever_task = None

    async def await_update_handlers(self) -> None:
        """Wait for all event handlers to complete execution."""
        await self._runner.await_all()

    async def cancel_update_handlers(self) -> None:
        """Cancel all running event handlers."""
        await self._runner.cancel_all()

    def _find_product_by_id(
        self,
        constraint: Optional[Callable[[Product], bool]] = None,
        **attributes: Any,
    ) -> Optional[Product]:
        """Find a product by ID.

        Args:
            constraint (Optional[Callable[[Product], bool]], optional): Optional
                constraint function to filter products. Defaults to None.
            **attributes (Any): Product attributes to match.

        Returns:
            Optional[Product]: The product object if found, None otherwise.
        """
        product_id = attributes['product_id']
        product = self.data.products.get(product_id)
        if product is None:
            return None
        if ProductFinder.product_matches(product, constraint, **attributes):
            return product
        return None

    def find_product(
        self,
        constraint: Optional[Callable[[Product], bool]] = None,
        **attributes: Any,
    ) -> Optional[Product]:
        """Find a product on the page that matches the specified attributes.

        Attributes are specific product state information and should match
        the product data model fields, such as `product_id`, `name`, `category`,
        etc. A constraint function can be provided to filter products based on
        additional criteria or more complex conditions.

        Args:
            constraint (Optional[Callable[[Product], bool]], optional): Optional
                function that takes a `Product` instance as input and returns
                a boolean indicating whether a certain constraint is met for
                this instance.
            **attributes (Any): Product attributes to match.

        Returns:
            Optional[Product]: The product object if found, None otherwise.
        """
        if 'product_id' in attributes:  # optimization for product ID lookup
            return self._find_product_by_id(constraint, **attributes)
        return ProductFinder.find_product(
            self.data.products.values(), constraint, **attributes
        )

    def find_products(
        self,
        constraint: Optional[Callable[[Product], bool]] = None,
        **attributes: Any,
    ) -> List[Product]:
        """Find products on the page that match the specified attributes.

        Attributes are specific product state information and should match
        the product data model fields, such as `product_id`, `name`, `category`,
        etc. A constraint function can be provided to filter products based on
        additional criteria or more complex conditions.

        Args:
            constraint (Optional[Callable[[Product], bool]], optional): Optional
                function that takes a `Product` instance as input and returns
                a boolean indicating whether a certain constraint is met for
                this instance.
            **attributes (Any): Product attributes to match.

        Returns:
            list[Product]: List of product objects that match the specified
                attributes.
        """
        if 'product_id' in attributes:  # optimization for product ID lookup
            product = self._find_product_by_id(constraint, **attributes)
            if product is None:
                return []
            return [product]
        return ProductFinder.find_products(
            self.data.products.values(), constraint, **attributes
        )


class ProductPageHubData(BaseModel):
    """Data model of a product page hub."""

    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
    )

    pages: Dict[int, ProductPageData] = Field(
        default={}, repr=False, frozen=True
    )
    """Dictionary of product page IDs and data models."""


TProductPageHub = TypeVar('TProductPageHub', bound='ProductPageHub')


class ProductPageHub:
    """Product page hub object that provides methods for managing multiple
    product pages at once. Each page retains its own state and can be accessed
    individually. Page data updates are done in parallel using asyncio tasks to
    optimize performance. May be used as an asynchronous context manager.
    """

    def __init__(
        self,
        data: Optional[ProductPageHubData] = None,
        client: Optional[ProductDataFetchClient] = None,
        enable_multiprocessing: bool = False,
    ) -> None:
        """Initializes a new product page hub object.

        Args:
            data (Optional[ProductPageHubData], optional): Data model of
                the product page hub to be used as the initial cached state.
            client (Optional[ProductDataFetchClient], optional): Client for
                fetching product data. Defaults to None.
            enable_multiprocessing (bool, optional): If True, multiprocessing
                is enabled for parsing product data. The parsing is then done
                in a `ProcessPoolExecutor` instead of the default
                `TheadPoolExecutor`. While this may improve startup performance,
                it should be used with caution. See the `concurrent.futures`
                documentation for more information. Defaults to False.
        """
        self._client = client or ProductDataFetchClient()
        self._data = data or ProductPageHubData()
        self._pages: dict[int, ProductPage] = {
            page_id: ProductPage(data=page_data, client=self._client)
            for page_id, page_data in self._data.pages.items()
        }
        self._publisher = ProductUpdateEventPublisher()
        executor = ProcessPoolExecutor() if enable_multiprocessing else None
        self._runner = CallableRunner(executor=executor)
        self._update_forever_task: Optional[asyncio.Task] = None

    def __str__(self) -> str:
        """String representation of the product page hub object."""
        page_ids = ', '.join(str(pid) for pid in self._pages.keys())
        return f'ProductPageHub for pages: {page_ids}'

    async def __aenter__(self: TProductPageHub) -> TProductPageHub:
        """Asynchronous context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[object],
    ) -> None:
        """Asynchronous context manager exit."""
        await self.close_session()

    async def start_session(self) -> None:
        """Start an aiohttp client session if one is not already started."""
        await self._client.start_session()

    async def close_session(self) -> None:
        """Close the aiohttp client session if one is open."""
        await self._client.close_session()
        await self.cancel_update_forever_task()
        pages_cancel_tasks = [
            page.cancel_update_forever_task() for page in self._pages.values()
        ]
        await asyncio.gather(*pages_cancel_tasks)
        await self.cancel_update_handlers()
        if self._runner.executor:
            self._runner.executor.shutdown(wait=True)

    @property
    def data(self) -> ProductPageHubData:
        """Product page hub data model."""
        return self._data  # copy is not necessary because fields are frozen

    @property
    def client(self) -> ProductDataFetchClient:
        """Product data fetch client."""
        return self._client

    async def set_client(self, client: ProductDataFetchClient) -> None:
        """Set the product data fetch client.

        This method is asynchronous and closes the current session if there is
        an active session.

        Args:
            client (ProductDataFetchClient): The new product data fetch client.
        """
        if not self._client.is_session_closed:
            await self.client.close_session()
        self._client = client
        for page in self._pages.values():
            page._client = client

    def subscribe_for_update(
        self,
        handler: Handler,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
        call_safe: bool = True,
        call_blocking: bool = True,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None,
    ) -> None:
        """Subscribe a handler to specific product update event(s) for all
        pages in the hub. The handler will be invoked when the event is posted,
        with the event context passed as an argument.

        The handler can be an asynchronous function, method, or any callable
        object that accepts exactly one argument (a `ProductUpdateContext`
        object) and returns `None` or a coroutine that resolves to `None`.

        Args:
            handler (Handler): The function or callable to invoke for
                the event(s).
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.
            call_safe (bool, optional): If True, exceptions raised by
                the handler are caught and logged. If False, exceptions are
                propagated and must be handled by the caller. Defaults to True.
            call_blocking (bool, optional): If True, the synchronous handler
                is executed in a blocking manner, i.e., called directly without
                using an executor. If False, the synchronous handler is executed
                in a non-blocking manner in a separate thread. Asynchronous
                handlers are always executed in a non-blocking manner, this
                parameter has no effect on them. Defaults to True.
            handler_done_callback (Optional[Callable[[asyncio.Future], Any]]):
                Optional function to be called when the handler completes
                execution. Depending on the type of the handler, the callback
                receives an `asyncio.Task` or `asyncio.Future` object as its
                argument, which represents the return value of the callback
                execution. Defaults to None.

        Raises:
            TypeError: If the handler does not have a valid signature.
        """
        self._publisher.subscribe(
            handler, event, call_safe, call_blocking, handler_done_callback
        )  # will not be directly invoked upon page updates
        for page in self._pages.values():
            page.subscribe_for_update(
                handler, event, call_safe, call_blocking, handler_done_callback
            )

    def unsubscribe_from_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
    ) -> None:
        """Unsubscribe a handler from specific product update event(s) for all
        pages in the hub, or all handlers if no specific handler is provided.
        The unsubscribed handler will no longer be invoked when the event is
        posted.

        Args:
            handler (Handler): The handler to be unsubscribed from the
                event(s). if None, all handlers for the event are unsubscribed.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.
        """
        self._publisher.unsubscribe(handler, event)
        for page in self._pages.values():
            page.unsubscribe_from_update(handler, event)

    def is_subscribed_for_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
    ) -> bool:
        """Check if there are any subscribers for the given event(s) for any
        page in the hub.

        Args:
            handler (Optional[Handler], optional): The handler to check for
                subscription. If None, all handlers are checked.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.

        Returns:
            bool: True if there are subscribers for the event, False otherwise.
        """
        if self._publisher.is_subscribed(handler, event):
            return True
        for page in self._pages.values():
            if page.is_subscribed_for_update(handler, event):
                return True
        return False

    def set_context(self, key: object, value: object) -> None:
        """Set a context key-value pair for all pages in the hub.

        Args:
            key (Any): Context key.
            value (Any): Context value.
        """
        self._publisher.context[key] = value
        for page in self._pages.values():
            page.context[key] = value

    def del_context(self, key: object) -> None:
        """Delete a context key-value pair for all pages in the hub. If the key
        does not exist in the page context, the method does nothing.

        Args:
            key (Any): Context key.
        """
        self._publisher.context.pop(key, None)
        for page in self._pages.values():
            page.context.pop(key, None)

    async def _register_page(
        self,
        page: ProductPage,
        update_contents: bool,
        update_silent: bool = True,
    ) -> None:
        """Register a new product page in the hub.

        Args:
            page (ProductPage): The product page object to register.
            update_contents (bool): If True, the page contents are fetched and
                updated. If False, the page contents are not fetched.
            update_silent (bool, optional): If True, the event handlers are not
                triggered after the page is updated. If `update_contents` is
                False, this parameter has no effect. Defaults to True.
        """
        self._data.pages[page.data.location_id] = page.data
        self._pages[page.data.location_id] = page
        if page.client != self._client:
            await page.set_client(self._client)
        page._runner = self._runner
        # add common handlers
        pub = self._publisher
        for subscribers in (pub.sync_subscribers, pub.async_subscribers):
            assert isinstance(subscribers, dict), 'Invalid subscribers type'
            for event, handlers_list in subscribers.items():
                for handler_data in handlers_list:
                    page.subscribe_for_update(
                        handler_data.handler,
                        event,
                        handler_data.exec_params.run_safe,
                        handler_data.exec_params.run_blocking,
                        handler_data.exec_params.done_callback,
                    )
        # add common context
        for key, value in self._publisher.context.items():
            page.context[key] = value
        # update page contents (optional)
        if update_contents:
            await page.update(silent=update_silent)

    def _unregister_page(self, location_id: int) -> None:
        """Unregister a product page from the hub.

        Args:
            location_id (int): ID of the product location.
        """
        self._data.pages.pop(location_id)
        self._pages.pop(location_id)

    @property
    def pages(self) -> Dict[int, ProductPage]:
        """Dictionary of product page objects with location IDs as keys."""
        return self._pages.copy()

    async def new_page(
        self,
        location_id: int,
        fetch_contents: bool = False,
        trigger_handlers: bool = False,
    ) -> ProductPage:
        """Create a new product page and register it in the hub. The page
        receives a common client. Its contents can be fetched and updated
        optionally.

        Args:
            location_id (int): ID of the product location.
            fetch_contents (bool, optional): If True, the page contents are
                fetched and updated. If False, the page contents are empty.
                Defaults to False.
            trigger_handlers (bool, optional): If True, the event handlers are
                triggered after the page contents are fetched. This parameter
                has no effect if `fetch_contents` is False. Defaults to False.

        Returns:
            ProductPage: The newly created product page object.
        """
        page = ProductPage(location_id=location_id, client=self._client)
        await self._register_page(page, fetch_contents, trigger_handlers)
        return page

    async def add_page(
        self,
        page: ProductPage,
        update_contents: bool = False,
        trigger_handlers: bool = False,
    ) -> None:
        """Add an existing product page to the hub. The page retains its own
        state, but receives a common client. Its contents can be fetched and
        updated optionally.

        Args:
            page (ProductPage): The product page object to add.
            update_contents (bool, optional): If True, the page contents are
                fetched and updated. If False, the page contents remain as is.
            trigger_handlers (bool, optional): If True, the event handlers are
                triggered after the page contents are updated. This parameter
                has no effect if `update_contents` is False. Defaults to False.
        """
        await self._register_page(page, update_contents, trigger_handlers)

    async def remove_page(
        self, location_id: int, await_handlers: bool = False
    ) -> ProductPage:
        """Remove a product page from the hub. The page retains its own state,
        but receives a new client. All event handlers are cancelled or awaited.

        Args:
            location_id (int): ID of the product location.
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers bound to the page to complete execution.
                Otherwise, the method will cancel all event handlers. Defaults
                to False.

        Raises:
            KeyError: If the page is not found.

        Returns:
            ProductPage: The removed product page object.
        """
        if location_id not in self._pages:
            raise KeyError(f'Page with location ID {location_id} not found')
        page = self._pages[location_id]
        if await_handlers:
            await page.await_update_handlers()
        else:
            await page.cancel_update_handlers()
        self._unregister_page(location_id)
        page._client = ProductDataFetchClient()
        page._runner = CallableRunner(executor=None)
        return page

    async def scan(
        self, start: int = 1, stop: int = 999, step: int = 1
    ) -> None:
        """Scan for new product pages in a range of location IDs. The pages
        that are valid and have products are registered in the hub. The existing
        pages are updated. The update handlers are not triggered.

        Note: unlike Python's `range` function, the `stop` parameter is
        inclusive.

        Args:
            start (int, optional): Start location ID. Defaults to 1.
            stop (int, optional): Stop location ID. Defaults to 999.
            step (int, optional): Step size for location IDs. Defaults to 1.
        """
        # init new pages without fetching contents
        for loc in range(start, stop + 1, step):
            if loc not in self._pages:
                await self.new_page(location_id=loc, fetch_contents=False)
        # update new and existing pages
        await self.update(silent=True)
        # remove pages with invalid location IDs (no products)
        inexistent_location_ids = [
            loc for loc, page in self._pages.items() if not page.data.products
        ]
        for loc in inexistent_location_ids:
            self._unregister_page(loc)

    async def update(
        self, silent: bool = False, await_handlers: bool = False, **kwargs: Any
    ) -> None:
        """Fetch the contents of all product pages in the hub, extract the
        product data, update the internal state of the pages, and trigger
        event handlers.

        Args:
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        # fetch the HTML contents of all pages
        fetch_tasks = [page._fetch_contents() for page in self._pages.values()]
        fetch_results = await asyncio.gather(*fetch_tasks)
        # filter the pages that have been updated
        updated_pages = {
            page: fetch_info
            for page, fetch_info in zip(self._pages.values(), fetch_results)
            if fetch_info.is_updated
        }
        # parse the contents of the pages that have been updated
        parse_tasks = []
        for page, fetch_info in updated_pages.items():
            assert fetch_info.contents is not None, 'Invalid contents'
            parse_tasks.append(page._parse_contents(fetch_info.contents))
        parse_results = await asyncio.gather(*parse_tasks)
        # update the internal state of the pages
        update_tasks = []
        for page, fetch_info, products in zip(
            updated_pages.keys(), updated_pages.values(), parse_results
        ):
            assert fetch_info.contents_hash is not None, 'Invalid hash'
            update_tasks.append(
                page._update_products(
                    products,
                    fetch_info.contents_hash,
                    silent,
                    await_handlers,
                    **kwargs,
                )
            )
        await asyncio.gather(*update_tasks)

    async def update_forever(
        self,
        interval: float = 10.0,
        silent: bool = False,
        await_handlers: bool = False,
        **kwargs: Any,
    ) -> None:
        """Update all product pages in the hub at regular intervals.

        This method is a coroutine that runs indefinitely, updating
        the product page at regular intervals.

        Args:
            interval (float, optional): The time interval in seconds between
                the updates. Defaults to 10 seconds.
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        while True:
            try:
                await self.update(silent, await_handlers, **kwargs)
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)

    def init_update_forever_task(
        self,
        interval: float = 10.0,
        silent: bool = False,
        await_handlers: bool = False,
        **kwargs: Any,
    ) -> asyncio.Task:
        """Initialize the update forever task for all product pages in the hub.
        If a task is already running, the method does nothing.

        This method is not a coroutine. It creates a new task from
        the `update_forever` coroutine with the `asyncio.create_task` function.
        The task is stored internally and can be cancelled with
        the `cancel_update_forever` method. Note that the task is created
        for the hub, not for individual pages.

        Args:
            interval (float, optional): The time interval in seconds between
                the updates. Defaults to 10.0 seconds.
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        task = self._update_forever_task
        if task is None or task.done():
            task = asyncio.create_task(
                self.update_forever(interval, silent, await_handlers, **kwargs)
            )
            self._update_forever_task = task
        return task

    async def cancel_update_forever_task(self) -> None:
        """Cancel the update forever task of the hub. Note that the separate
        update forever tasks of individual pages are not cancelled.
        """
        if self._update_forever_task:
            task = self._update_forever_task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._update_forever_task = None

    async def await_update_handlers(self) -> None:
        """Wait for all event handlers to complete execution."""
        await self._runner.await_all()

    async def cancel_update_handlers(self) -> None:
        """Cancel all running event handlers."""
        await self._runner.cancel_all()
