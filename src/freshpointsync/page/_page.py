from __future__ import annotations

import asyncio
import logging

from concurrent.futures import ProcessPoolExecutor
from functools import cached_property
from pydantic import BaseModel, ConfigDict, Field
from pydantic.alias_generators import to_camel
from typing import Any, Callable, Iterable, Optional, NamedTuple, Union

from ..client._client import ProductDataFetchClient
from ..parser._parser import (
    ProductPageHTMLParser,
    ProductFinder,
    hash_text,
    normalize_text
)
from ..product._product import Product
from ..update._update import (
    CallableRunner,
    ProductUpdateEvent,
    ProductUpdateEventPublisher,
    ProductCacheUpdater,
    Handler
)


logger = logging.getLogger('freshpointsync.page')
"""Logger for the `freshpointsync.page` module."""


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
    products: dict[int, Product] = Field(default={}, repr=False, frozen=True)
    """Dictionary of products' data on the page."""

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
    def product_names(self) -> list[str]:
        """List of string product names on the page."""
        return [p.name for p in self.products.values() if p.name]

    @property
    def product_categories(self) -> list[str]:
        """List of string product categories on the page."""
        categories = []
        for p in self.products.values():
            if p.category and p.category not in categories:
                categories.append(p.category)
        return categories


class ProductPage:
    """Product page object that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """
    def __init__(
        self,
        location_id: Optional[int] = None,
        data: Optional[ProductPageData] = None,
        client: Optional[ProductDataFetchClient] = None
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

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        await self.close_session()
        await self.cancel_update_handlers()
        await self.cancel_update_forever()

    @staticmethod
    def _validate_data(
        location_id: Optional[int] = None,
        data: Optional[ProductPageData] = None
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

    @property
    def data(self) -> ProductPageData:
        """Product page data model."""
        return self._data  # copy is not necessary because fields are frozen

    @property
    def context(self) -> dict[Any, Any]:
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
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
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
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent],\
            None], optional): The type of product update event(s) to
                subscribe to. If None, the handler will be subscribed to
                all events.
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
            ] = None
    ) -> None:
        """Unsubscribe a handler from specific product update event(s),
        or all handlers if no specific handler is provided. The unsubscribed
        handler will no longer be invoked when the event is posted.

        Args:
            handler (Handler): The handler to be unsubscribed from the
                event(s). if None, all handlers for the event are unsubscribed.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent],\
            None], optional): The type of product update event(s)
                to unsubscribe from. If None, the handler(s) will be subscribed
                from all events.
        """
        self._publisher.unsubscribe(handler, event)

    def is_subscribed_for_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
            ] = None
    ) -> bool:
        """Check if there are any subscribers for the given event(s).

        Args:
            handler (Optional[Handler], optional): The handler to check for
                subscription. If None, all handlers are checked.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent],\
            None], optional): The type of product update event(s) to check for
                subscribers. If None, all events are checked.

        Returns:
            bool: True if there are subscribers for the event, False otherwise.
        """
        return self._publisher.is_subscribed(handler, event)

    async def start_session(self) -> None:
        """Start an aiohttp client session if one is not already started."""
        await self._client.start_session()

    async def close_session(self) -> None:
        """Close the aiohttp client session if one is open."""
        await self._client.close_session()
        await self._runner.cancel_all()
        await self.cancel_update_forever()

    async def _fetch_contents(self) -> FetchInfo:
        """Fetch the contents of the product page.

        Returns:
            FetchInfo: Named tuple containing the fetched contents, the hash
                of the contents, and a flag indicating whether the contents
                have been updated.
        """
        is_updated: bool = False
        try:
            contents = await self._runner.run_async(
                self._client.fetch, self._data.location_id
                )
        except asyncio.CancelledError:
            return FetchInfo(None, None, is_updated)
        if contents is None:
            return FetchInfo(None, None, is_updated)
        contents_hash = hash_text(contents)
        if contents_hash != self.data.html_hash:
            is_updated = True
            # do not update the html data hash attribute value here because
            # fetching is not supposed to modify the inner state of the page
        return FetchInfo(contents, contents_hash, is_updated)

    @staticmethod
    def _parse_contents_blocking(contents: str) -> list[Product]:
        """Blocking synchronous function to parse the contents of the product
        page and extract product data.

        Args:
            contents (str): The HTML contents of the product page.

        Returns:
            list[Product]: List of product data extracted from the contents.
        """
        return [p for p in ProductPageHTMLParser(contents).products]

    async def _parse_contents(self, contents: str) -> list[Product]:
        """Asynchronously parse the contents of the product page and extract
        product data. This method is a wrapper around the blocking synchronous
        parsing function that run in a way that does not block the event loop.

        Args:
            contents (str): The HTML contents of the product page.

        Returns:
            list[Product]: List of product data extracted from the contents.
        """
        if not contents:
            return []
        try:
            func = self._parse_contents_blocking
            products = await self._runner.run_sync(func, contents)
        except asyncio.CancelledError:
            return []
        return products or []

    async def fetch(self) -> list[Product]:
        """Fetch the contents of the product page and extract the product data.
        This method does not update the internal state of the page, nor does it
        trigger any event handlers.

        Returns:
            list[Product]: List of product data extracted from the contents.
        """
        fetch_info = await self._fetch_contents()
        if fetch_info.is_updated:
            assert fetch_info.contents is not None, 'Invalid contents'
            return await self._parse_contents(fetch_info.contents)
        return [p for p in self._data.products.values()]

    def _update_silently(
        self, html_hash: str, products: Iterable[Product]
    ) -> None:
        """Fetch the contents of the product page, extract the product data,
        and update the internal state of the page without triggering any event
        handlers.

        Args:
            html_hash (str): The SHA-256 hash of the HTML contents.
            products (Iterable[Product]): Iterable of product data to update.
        """
        self.data.html_hash = html_hash
        self._updater.update_silently(products)

    async def update_silently(self) -> None:
        """Fetch the contents of the product page, extract the product data,
        and update the internal state of the page without triggering any event
        handlers.
        """
        fetch_info = await self._fetch_contents()
        if fetch_info.is_updated:
            assert fetch_info.contents is not None, 'Invalid contents'
            assert fetch_info.contents_hash is not None, 'Invalid hash'
            products = await self._parse_contents(fetch_info.contents)
            self._update_silently(fetch_info.contents_hash, products)

    async def _update(
        self,
        html_hash: str,
        products: Iterable[Product],
        await_handlers: bool = False,
        **kwargs: Any
    ) -> None:
        """Fetch the contents of the product page, extract the product data,
        update the internal state of the page, and trigger event handlers.

        Args:
            html_hash (str): The SHA-256 hash of the HTML contents.
            products (Iterable[Product]): Iterable of product data to update.
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.
        """
        self.data.html_hash = html_hash
        await self._updater.update(products, await_handlers, **kwargs)

    async def update(
        self, await_handlers: bool = False, **kwargs: Any
    ) -> None:
        """Fetch the contents of the product page, extract the product data,
        update the internal state of the page, and trigger event handlers.

        Args:
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.
        """
        fetch_info = await self._fetch_contents()
        if fetch_info.is_updated:
            assert fetch_info.contents is not None, 'Invalid contents'
            assert fetch_info.contents_hash is not None, 'Invalid hash'
            products = await self._parse_contents(fetch_info.contents)
            await self._update(
                fetch_info.contents_hash, products, await_handlers, **kwargs
                )

    async def update_forever(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: Any
    ) -> None:
        """Update the product page at regular intervals.

        This method is a coroutine that runs indefinitely, updating
        the product page at regular intervals.

        Args:
            interval (float, optional): The time interval in seconds between
                updates. Defaults to 10.0.
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.
        """
        while True:
            try:
                await self.update(await_handlers, **kwargs)
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)

    def init_update_forever_task(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: Any
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
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.

        Returns:
            asyncio.Task: The task object created by `asyncio.create_task`.
        """
        task = self._update_forever_task
        if task is None or task.done():
            task = asyncio.create_task(
                self.update_forever(interval, await_handlers, **kwargs)
                )
            self._update_forever_task = task
        return task

    async def await_update_handlers(self) -> None:
        """Wait for all event handlers to complete execution."""
        await self._runner.await_all()

    async def cancel_update_handlers(self) -> None:
        """Cancel all running event handlers."""
        await self._runner.cancel_all()

    async def cancel_update_forever(self) -> None:
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

    def _find_product_by_id(
        self,
        constraint: Optional[Callable[[Product], bool]] = None,
        **attributes
    ) -> Optional[Product]:
        """Find a product by ID.

        Args:
            constraint (Optional[Callable[[Product], bool]], optional): Optional
                constraint function to filter products. Defaults to None.

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
        **attributes
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
        **attributes
    ) -> list[Product]:
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

    pages: dict[int, ProductPageData] = Field(
        default_factory=dict, repr=False, frozen=True
        )
    """Dictionary of product page data models."""


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
        enable_multiprocessing: bool = False
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
        page_ids = ", ".join(str(pid) for pid in self._pages.keys())
        return f'ProductPageHub for pages: {page_ids}'

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        await self.close_session()
        await self.await_update_handlers()

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
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
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
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent],\
            None], optional): The type of product update event(s) to
                subscribe to. If None, the handler will be subscribed to
                all events.
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
            ] = None
    ) -> None:
        """Unsubscribe a handler from specific product update event(s) for all
        pages in the hub, or all handlers if no specific handler is provided.
        The unsubscribed handler will no longer be invoked when the event is
        posted.

        Args:
            handler (Handler): The handler to be unsubscribed from the
                event(s). if None, all handlers for the event are unsubscribed.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent],\
            None], optional): The type of product update event(s)
                to unsubscribe from. If None, the handler(s) will be subscribed
                from all events.
        """
        self._publisher.unsubscribe(handler, event)
        for page in self._pages.values():
            page.unsubscribe_from_update(handler, event)

    def is_subscribed_for_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
            ] = None
    ) -> bool:
        """Check if there are any subscribers for the given event(s) for any
        page in the hub.

        Args:
            handler (Optional[Handler], optional): The handler to check for
                subscription. If None, all handlers are checked.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent],\
            None], optional): The type of product update event(s) to check for
                subscribers. If None, all events are checked.

        Returns:
            bool: True if there are subscribers for the event, False otherwise.
        """
        if self._publisher.is_subscribed(handler, event):
            return True
        for page in self._pages.values():
            if page.is_subscribed_for_update(handler, event):
                return True
        return False

    def set_context(self, key: Any, value: Any) -> None:
        """Set a context key-value pair for all pages in the hub.

        Args:
            key (Any): Context key.
            value (Any): Context value.
        """
        self._publisher.context[key] = value
        for page in self._pages.values():
            page.context[key] = value

    def del_context(self, key: Any) -> None:
        """Delete a context key-value pair for all pages in the hub. If the key
        does not exist in the page context, the method does nothing.

        Args:
            key (Any): Context key.
        """
        self._publisher.context.pop(key, None)
        for page in self._pages.values():
            page.context.pop(key, None)

    async def start_session(self) -> None:
        """Start an aiohttp client session if one is not already started."""
        await self._client.start_session()

    async def close_session(self) -> None:
        """Close the aiohttp client session if one is open."""
        await self._client.close_session()
        await self.cancel_update_handlers()
        if self._runner.executor:
            self._runner.executor.shutdown(wait=True)
        for page in self._pages.values():
            await page.cancel_update_forever()

    async def _register_page(
        self,
        page: ProductPage,
        update_contents: bool,
        trigger_handlers: bool = False
    ) -> None:
        """Register a new product page in the hub.

        Args:
            page (ProductPage): The product page object to register.
            update_contents (bool): If True, the page contents are fetched and
                updated. If False, the page contents are not fetched.
            trigger_handlers (bool, optional): If True, the event handlers are
                triggered after the page is updated. Defaults to False.
        """
        self._data.pages[page.data.location_id] = page.data
        self._pages[page.data.location_id] = page
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
                        handler_data.exec_params.done_callback
                        )
        # add common context
        for key, value in self._publisher.context:
            page.context[key] = value
        # add page contents (optional)
        if update_contents:
            if trigger_handlers:
                await page.update()
            else:
                await page.update_silently()

    def _unregister_page(self, location_id: int) -> None:
        """Unregister a product page from the hub.

        Args:
            location_id (int): ID of the product location.
        """
        self._data.pages.pop(location_id)
        self._pages.pop(location_id)

    async def new_page(
        self,
        location_id: int,
        fetch_contents: bool = False,
        trigger_handlers: bool = False
    ) -> ProductPage:
        """Create a new product page and register it in the hub.

        Args:
            location_id (int): ID of the product location.
            fetch_contents (bool, optional): If True, the page contents are
                fetched and updated. If False, the page contents are empty.
                Defaults to False.
            trigger_handlers (bool, optional): If True, the event handlers are
                triggered after the page is updated. Defaults to False.

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
        trigger_handlers: bool = False
    ) -> None:
        """Add an existing product page to the hub. The page retains its own
        state, but receives a common client. Its contents and event handlers
        are updated, too.

        Args:
            page (ProductPage): The product page object to add.
            update_contents (bool, optional): If True, the page contents are
                fetched and updated. If False, the page contents remain as is.
            trigger_handlers (bool, optional): If True, the event handlers are
                triggered after the page is updated. Defaults to False.
        """
        if page.client != self._client:
            await page.set_client(self._client)
        await self._register_page(page, update_contents, trigger_handlers)

    def get_page(self, location_id: int) -> ProductPage:
        """Get a registered product page by location ID.

        Args:
            location_id (int): ID of the product location.

        Raises:
            KeyError: If the page is not found.

        Returns:
            ProductPage: The product page object.
        """
        try:
            return self._pages[location_id]
        except KeyError:
            raise KeyError(f'Page not found: {location_id}')

    def get_pages(self) -> dict[int, ProductPage]:
        """Get all registered product pages.

        Returns:
            dict[int, ProductPage]: Dictionary of product page objects with
                location IDs as keys.
        """
        return self._pages.copy()

    async def remove_page(
        self,
        location_id: int,
        await_handlers: bool = False
    ) -> ProductPage:
        """Remove a product page from the hub.

        This method unregisters the page from the hub, creates a new client
        for the page, and cancels (or awaits) all event handlers. It acts
        similarly to the dictionary `pop` method.

        Args:
            location_id (int): ID of the product location.
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers bound to the page to complete execution.
                Defaults to False.
        
        Raises:
            KeyError: If the page is not found.

        Returns:
            ProductPage: The removed product page object.
        """
        page = self.get_page(location_id)
        self._unregister_page(location_id)
        if await_handlers:
            await page.await_update_handlers()
        else:
            await page.cancel_update_handlers()
        page._client = ProductDataFetchClient()
        return page

    async def scan(
        self, start: int = 0, stop: int = 500, step: int = 1
    ) -> None:
        """Scan for new product pages in a range of location IDs. The pages
        that are valid and have products are registered in the hub.

        Args:
            start (int, optional): Start location ID. Defaults to 0.
            stop (int, optional): Stop location ID. Defaults to 500.
            step (int, optional): Step size for location IDs. Defaults to 1.
        """
        for loc in range(start, stop, step):
            if loc in self._pages:
                continue
            await self.new_page(
                location_id=loc,
                fetch_contents=False,
                trigger_handlers=False
                )
        await self.update_silently()
        inexistent_locations = [
            loc for loc, page in self._pages.items() if not page.data.products
            ]
        for loc in inexistent_locations:
            self._unregister_page(loc)

    async def _fetch_contents(self) -> dict[int, FetchInfo]:
        """Fetch the contents of all product pages in the hub.

        Returns:
            dict[int, FetchInfo]: Dictionary of fetched contents, hashes, and
                update flags for each page.
        """
        tasks: list[asyncio.Task] = []
        for page in self._pages.values():
            tasks.append(self._runner.run_async(page._fetch_contents))
        results: list[FetchInfo] = await asyncio.gather(*tasks)
        return dict(zip(self._pages.keys(), results))

    def _filter_updated_contents(
        self, pages_fetch_info: dict[int, FetchInfo]
    ) -> dict[int, FetchInfo]:
        """Filter the fetched contents to only include pages the contents of
        which have been updated.

        Args:
            pages_fetch_info (dict[int, FetchInfo]): Dictionary of fetched
                contents, hashes, and update flags for each page.

        Returns:
            dict[int, FetchInfo]: Dictionary of updated pages and their fetch
                info.
        """
        return {
            page_id: page_fetch_info
            for page_id, page_fetch_info in pages_fetch_info.items()
            if page_fetch_info.is_updated
            }

    async def _parse_contents(
        self, pages_fetch_info: dict[int, FetchInfo]
    ) -> dict[int, list[Product]]:
        """Parse the contents of all product pages in the hub and extract
        product data.

        Args:
            pages_fetch_info (dict[int, FetchInfo]): Dictionary of fetched
                contents, hashes, and update flags for each page.

        Returns:
            dict[int, list[Product]]: Dictionary of parsed product data for
                each page.
        """
        tasks: list[asyncio.Future] = []
        # for some reason, when multiprocessing is enabled, the runner
        # fails to run the parsing function with run_safe=True (in this case
        # it is wrapped in a safe runner function inside of the runner).
        # Something is not pickable, but I don't know what it is.
        run_safe = not isinstance(self._runner.executor, ProcessPoolExecutor)
        for page_id, page_fetch_info in pages_fetch_info.items():
            contents = page_fetch_info.contents or ''
            func = self._pages[page_id]._parse_contents_blocking
            task = self._runner.run_sync(
                func, contents, run_safe=run_safe, run_blocking=False
                )
            tasks.append(task)
        results: list[list[Product]] = [
            result if isinstance(result, list) else []
            for result in await asyncio.gather(*tasks, return_exceptions=True)
            ]
        return dict(zip(pages_fetch_info.keys(), results))

    async def update_silently(self) -> None:
        """Fetch the contents of all product pages in the hub, extract the
        product data, and update the internal state of the pages without
        triggering any event handlers.
        """
        pages_fetch_info = await self._fetch_contents()
        pages_fetch_info = self._filter_updated_contents(pages_fetch_info)
        pages_products = await self._parse_contents(pages_fetch_info)
        for page_id, page_products in pages_products.items():
            page = self._pages[page_id]
            page_html_hash = pages_fetch_info[page_id].contents_hash
            assert page_html_hash is not None, 'Invalid hash'
            page._update_silently(page_html_hash, page_products)

    async def update(
        self,
        await_handlers: bool = False,
        **kwargs
    ) -> None:
        """Fetch the contents of all product pages in the hub, extract the
        product data, update the internal state of the pages, and trigger
        event handlers.

        Args:
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.
        """
        pages_fetch_info = await self._fetch_contents()
        pages_fetch_info = self._filter_updated_contents(pages_fetch_info)
        pages_products = await self._parse_contents(pages_fetch_info)
        tasks: list[asyncio.Task] = []
        for page_id, page_products in pages_products.items():
            page = self._pages[page_id]
            page_html_hash = pages_fetch_info[page_id].contents_hash
            assert page_html_hash is not None, 'Invalid hash'
            task = self._runner.run_async(
                page._update,
                page_html_hash,
                page_products,
                await_handlers,
                **kwargs
                )
            tasks.append(task)
        await asyncio.gather(*tasks)

    async def update_forever(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: Any
    ) -> None:
        """Update all product pages in the hub at regular intervals.

        This method is a coroutine that runs indefinitely, updating
        the product page at regular intervals.

        Args:
            interval (float, optional): The time interval in seconds between
                updates. Defaults to 10.0.
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.
        """
        while True:
            try:
                await self.update(await_handlers, **kwargs)
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)

    async def init_update_forever_tasks(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: Any
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
                updates. Defaults to 10.0.
            await_handlers (bool, optional): If True, the method will wait for
                all event handlers to complete execution. Defaults to False.
        """
        task = self._update_forever_task
        if task is None or task.done():
            task = asyncio.create_task(
                self.update_forever(interval, await_handlers, **kwargs)
                )
            self._update_forever_task = task
        return task

    async def await_update_handlers(self) -> None:
        """Wait for all event handlers to complete execution."""
        tasks = [p.await_update_handlers() for p in self._pages.values()]
        await asyncio.gather(*tasks)

    async def cancel_update_handlers(self) -> None:
        """Cancel all running event handlers."""
        tasks = [p.cancel_update_handlers() for p in self._pages.values()]
        await asyncio.gather(*tasks)

    async def cancel_update_forever(self) -> None:
        """Cancel the update forever task if it is running."""
        if self._update_forever_task:
            task = self._update_forever_task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._update_forever_task = None
