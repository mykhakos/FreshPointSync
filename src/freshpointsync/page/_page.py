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
    SafeAsyncTaskRunner,
    ProductUpdateEvent,
    ProductUpdateEventPublisher,
    ProductCacheUpdater,
    Handler
)


logger = logging.getLogger('freshpointsync.page')


class FetchInfo(NamedTuple):
    contents: Optional[str]
    contents_hash: Optional[str]
    is_updated: bool


class ProductPageData(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        )

    location_id: int = Field(frozen=True)
    html_hash: str = Field(default='')
    products: dict[int, Product] = Field(
        default_factory=dict, repr=False, frozen=True
        )

    @cached_property
    def url(self) -> str:
        return ProductDataFetchClient.get_page_url(self.location_id)

    @property  # not cached because products may be missing upon initialization
    def location_name(self) -> str:
        for product in self.products.values():
            return product.location_name
        return ''

    @property  # not cached because "location_name" is not cached
    def location_name_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the location name."""
        return normalize_text(self.location_name)

    @property
    def product_names(self) -> list[str]:
        return [p.name for p in self.products.values() if p.name]

    @property
    def product_categories(self) -> list[str]:
        categories = []
        for p in self.products.values():
            if p.category and p.category not in categories:
                categories.append(p.category)
        return categories


class ProductPage:
    def __init__(
        self,
        location_id: Optional[int] = None,
        data: Optional[ProductPageData] = None,
        client: Optional[ProductDataFetchClient] = None
    ) -> None:
        self._data = self._validate_data(location_id, data)
        self._client = client or ProductDataFetchClient()
        self._publisher = ProductUpdateEventPublisher()
        self._runner = SafeAsyncTaskRunner(executor=None)
        self._update_forever_task: Optional[asyncio.Task] = None
        self._updater = ProductCacheUpdater(
            self._data.products, self._publisher
            )

    def __str__(self) -> str:
        return self._data.url

    def __repr__(self) -> str:
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

    def _validate_data(
        self,
        location_id: Optional[int] = None,
        data: Optional[ProductPageData] = None
    ) -> ProductPageData:
        if data is None:
            if location_id is None:
                raise ValueError('Location ID is required')
            return ProductPageData(location_id=location_id)
        if location_id is not None and location_id != data.location_id:
            raise ValueError('Location ID mismatch')
        return data

    @property
    def data(self) -> ProductPageData:
        return self._data  # copy is not necessary because fields are frozen

    @property
    def context(self) -> dict[Any, Any]:
        return self._publisher.context

    @property
    def client(self) -> ProductDataFetchClient:
        return self._client

    async def set_client(self, client: ProductDataFetchClient) -> None:
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
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
    ) -> None:
        self._publisher.subscribe(
            handler, event, call_safe, handler_done_callback
            )

    def unsubscribe_from_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
            ] = None
    ) -> None:
        self._publisher.unsubscribe(handler, event)

    def is_subscribed_for_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
            ] = None
    ) -> bool:
        return self._publisher.is_subscribed(handler, event)

    async def start_session(self) -> None:
        await self._client.start_session()

    async def close_session(self) -> None:
        await self._client.close_session()
        await self._runner.cancel_all()
        await self.cancel_update_forever()

    async def _fetch_contents(self) -> FetchInfo:
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
        return [p for p in ProductPageHTMLParser(contents).products]

    async def _parse_contents(self, contents: str) -> list[Product]:
        if not contents:
            return []
        try:
            func = self._parse_contents_blocking
            products = await self._runner.run_sync(func, contents)
        except asyncio.CancelledError:
            return []
        return products or []

    async def fetch(self) -> list[Product]:
        fetch_info = await self._fetch_contents()
        if fetch_info.is_updated:
            assert fetch_info.contents is not None, 'Invalid contents'
            return await self._parse_contents(fetch_info.contents)
        return [p for p in self._data.products.values()]

    def _update_silently(
        self, html_hash: str, products: Iterable[Product]
    ) -> None:
        self.data.html_hash = html_hash
        self._updater.update_silently(products)

    async def update_silently(self) -> None:
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
        self.data.html_hash = html_hash
        await self._updater.update(products, await_handlers, **kwargs)

    async def update(
        self, await_handlers: bool = False, **kwargs: Any
    ) -> None:
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
    ) -> None:
        task = self._update_forever_task
        if task is None or task.done():
            self._update_forever_task = asyncio.create_task(
                self.update_forever(interval, await_handlers, **kwargs)
                )

    async def await_update_handlers(self) -> None:
        await self._runner.await_all()

    async def cancel_update_handlers(self) -> None:
        await self._runner.cancel_all()

    async def cancel_update_forever(self) -> None:
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
        if 'product_id' in attributes:
            return self._find_product_by_id(constraint, **attributes)
        return ProductFinder.find_product(
            self.data.products.values(), constraint, **attributes
            )

    def find_products(
        self,
        constraint: Optional[Callable[[Product], bool]] = None,
        **attributes
    ) -> list[Product]:
        if 'product_id' in attributes:
            product = self._find_product_by_id(constraint, **attributes)
            if product is None:
                return []
            return [product]
        return ProductFinder.find_products(
            self.data.products.values(), constraint, **attributes
            )


class ProductPageHubData(BaseModel):
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        )

    pages: dict[int, ProductPageData] = Field(
        default_factory=dict, repr=False, frozen=True
        )


class ProductPageHub:
    def __init__(
        self,
        data: Optional[ProductPageHubData] = None,
        client: Optional[ProductDataFetchClient] = None,
        enable_multiprocessing: bool = False
    ) -> None:
        self._client = client or ProductDataFetchClient()
        self._data = data or ProductPageHubData()
        self._pages: dict[int, ProductPage] = {
            page_id: ProductPage(data=page_data, client=self._client)
            for page_id, page_data in self._data.pages.items()
            }
        self._publisher = ProductUpdateEventPublisher()
        executor = ProcessPoolExecutor() if enable_multiprocessing else None
        self._runner = SafeAsyncTaskRunner(executor=executor)
        self._update_forever_task: Optional[asyncio.Task] = None

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
        return self._data  # copy is not necessary because fields are frozen

    @property
    def client(self) -> ProductDataFetchClient:
        return self._client

    async def set_client(self, client: ProductDataFetchClient) -> None:
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
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
    ) -> None:
        self._publisher.subscribe(
            handler, event, call_safe, handler_done_callback
            )  # will not be directly invoked upon page updates
        for page in self._pages.values():
            page.subscribe_for_update(
                handler, event, call_safe, handler_done_callback
                )

    def unsubscribe_from_update(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
            ] = None
    ) -> None:
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
        if self._publisher.is_subscribed(handler, event):
            return True
        for page in self._pages.values():
            if page.is_subscribed_for_update(handler, event):
                return True
        return False

    def set_context(self, key: Any, value: Any) -> None:
        self._publisher.context[key] = value
        for page in self._pages.values():
            page.context[key] = value

    def del_context(self, key: Any) -> None:
        self._publisher.context.pop(key, None)
        for page in self._pages.values():
            page.context.pop(key, None)

    async def start_session(self) -> None:
        await self._client.start_session()

    async def close_session(self) -> None:
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
        self._data.pages[page.data.location_id] = page.data
        self._pages[page.data.location_id] = page
        # add common handlers
        pub = self._publisher
        for subscribers in (pub.sync_subscribers, pub.async_subscribers):
            assert isinstance(subscribers, dict), 'Invalid subscribers type'
            for event, handlers in subscribers.items():
                for handler in handlers:
                    page.subscribe_for_update(event, handler)
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
        self._data.pages.pop(location_id)
        self._pages.pop(location_id)

    async def new_page(
        self,
        location_id: int,
        fetch_contents: bool = False,
        trigger_handlers: bool = False
    ) -> ProductPage:
        page = ProductPage(location_id=location_id, client=self._client)
        await self._register_page(page, fetch_contents, trigger_handlers)
        return page

    async def add_page(
        self,
        page: ProductPage,
        update_contents: bool = False,
        trigger_handlers: bool = False
    ) -> None:
        if page.client != self._client:
            await page.set_client(self._client)
        await self._register_page(page, update_contents, trigger_handlers)

    def get_page(self, location_id: int) -> ProductPage:
        try:
            return self._pages[location_id]
        except KeyError:
            raise KeyError(f'Page not found: {location_id}')

    def get_pages(self) -> dict[int, ProductPage]:
        return self._pages.copy()

    async def remove_page(
        self,
        location_id: int,
        await_handlers: bool = False
    ) -> ProductPage:
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
        tasks: list[asyncio.Task] = []
        for page in self._pages.values():
            tasks.append(self._runner.run_async(page._fetch_contents))
        results: list[FetchInfo] = await asyncio.gather(*tasks)
        return dict(zip(self._pages.keys(), results))

    def _filter_updated_contents(
        self, pages_fetch_info: dict[int, FetchInfo]
    ) -> dict[int, FetchInfo]:
        return {
            page_id: page_fetch_info
            for page_id, page_fetch_info in pages_fetch_info.items()
            if page_fetch_info.is_updated
            }

    async def _parse_contents(
        self, pages_fetch_info: dict[int, FetchInfo]
    ) -> dict[int, list[Product]]:
        tasks: list[asyncio.Future] = []
        # for some reason, when multiprocessing is enabled, the runner
        # fails to run the parsing function with run_safe=True (in this case
        # it is wrapped in a safe runner function inside of the runner).
        # Something is not pickable, but I don't know what it is.
        run_safe = not isinstance(self._runner.executor, ProcessPoolExecutor)
        for page_id, page_fetch_info in pages_fetch_info.items():
            contents = page_fetch_info.contents or ''
            func = self._pages[page_id]._parse_contents_blocking
            task = self._runner.run_sync(func, contents, run_safe=run_safe)
            tasks.append(task)
        results: list[list[Product]] = [
            result if isinstance(result, list) else []
            for result in await asyncio.gather(*tasks, return_exceptions=True)
            ]
        return dict(zip(pages_fetch_info.keys(), results))

    async def update_silently(self) -> None:
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
    ) -> None:
        task = self._update_forever_task
        if task is None or task.done():
            self._update_forever_task = asyncio.create_task(
                self.update_forever(interval, await_handlers, **kwargs)
                )

    async def await_update_handlers(self) -> None:
        tasks = [p.await_update_handlers() for p in self._pages.values()]
        await asyncio.gather(*tasks)

    async def cancel_update_handlers(self) -> None:
        tasks = [p.cancel_update_handlers() for p in self._pages.values()]
        await asyncio.gather(*tasks)

    async def cancel_update_forever(self) -> None:
        if self._update_forever_task:
            task = self._update_forever_task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            self._update_forever_task = None
