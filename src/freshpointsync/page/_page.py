import asyncio
import logging
import typing

from concurrent.futures import ProcessPoolExecutor

from ..client._client import ProductDataFetchClient
from ..parser._parser import ProductPageHTMLParser, ProductFinder
from ..product._product import Product
from ..update._update import (
    SafeAsyncTaskRunner,
    ProductUpdateEvent,
    ProductUpdateEventPublisher,
    ProductCacheUpdater,
    Handler
)

logger = logging.getLogger('freshpoint_sync.product_page')


class FreshPointProductPage:
    def __init__(
        self,
        location_id: int,
        client: typing.Optional[ProductDataFetchClient] = None
    ) -> None:
        self._client = client or ProductDataFetchClient()
        self._location_id = location_id
        self._url = self._client.get_page_url(location_id)
        self._products: dict[int, Product] = {}
        self._publisher = ProductUpdateEventPublisher()
        self._runner = SafeAsyncTaskRunner(executor=None)
        self._updater = ProductCacheUpdater(self._products, self._publisher)
        self._update_forever_task: typing.Optional[asyncio.Task] = None
        self._html = ''

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        await self.start_session()
        try:
            await self.update_silently()
            await asyncio.sleep(0)  # prevent two subsequent fetch() calls
        except Exception as exc:
            await self.close_session()
            raise exc
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        await self.close_session()
        await self.cancel_update_handlers()
        await self.cancel_update_forever()

    @property
    def html(self) -> str:
        return self._html

    @property
    def products(self) -> list[Product]:
        return [p for p in self._products.values()]

    @property
    def context(self) -> dict[typing.Any, typing.Any]:
        return self._publisher.context

    @property
    def location_id(self) -> int:
        return self._location_id

    @property
    def location_name(self) -> str:
        for product in self._products.values():
            return product.location_name
        return ''

    @property
    def url(self) -> str:
        return self._url

    @property
    def client(self) -> ProductDataFetchClient:
        return self._client

    async def set_client(self, client: ProductDataFetchClient) -> None:
        if not self._client.is_session_closed:
            await self.client.close_session()
        self._client = client

    def is_subscribed_for_update(self, event: ProductUpdateEvent) -> bool:
        return self._publisher.is_subscribed(event)

    def subscribe_for_update(
        self,
        event: ProductUpdateEvent,
        handler: Handler
    ) -> None:
        self._publisher.subscribe(event, handler)

    def unsubscribe_from_update(
        self,
        event: ProductUpdateEvent,
        handler: typing.Optional[Handler] = None
    ) -> None:
        self._publisher.unsubscribe(event, handler)

    async def start_session(self) -> None:
        await self._client.start_session()

    async def close_session(self) -> None:
        await self._client.close_session()
        await self._runner.cancel_all()
        await self.cancel_update_forever()

    async def _fetch_contents(self) -> tuple[str, bool]:

        async def fetch() -> str:
            contents = await self._client.fetch(self._location_id)
            if contents is None:
                raise ValueError('Client returned "None"')
            return contents

        is_updated: bool = False
        contents = await self._runner.run_async(fetch())
        if contents is None:
            return '', is_updated
        if contents != self._html:
            is_updated = True
        return contents, is_updated

    @staticmethod
    def _parse_contents_blocking(contents: str) -> list[Product]:
        return [p for p in ProductPageHTMLParser(contents).products]

    async def _parse_contents(self, contents: str) -> list[Product]:
        if not contents:
            return []
        func = self._parse_contents_blocking
        products = await self._runner.run_sync(func, contents)
        return products or []

    async def fetch(self) -> list[Product]:
        contents, is_updated = await self._fetch_contents()
        if is_updated:
            return await self._parse_contents(contents)
        return self.products

    def _update_silently(
        self, html_contents: str, products: typing.Iterable[Product]
    ) -> None:
        self._html = html_contents
        self._updater.update_silently(products)

    async def update_silently(self) -> None:
        contents, is_updated = await self._fetch_contents()
        if is_updated:
            products = await self._parse_contents(contents)
            self._update_silently(contents, products)

    async def _update(
        self,
        html_contents: str,
        products: typing.Iterable[Product],
        await_handlers: bool = False,
        **kwargs: typing.Any
    ) -> None:
        self._html = html_contents
        await self._updater.update(products, await_handlers, **kwargs)

    async def update(
        self, await_handlers: bool = False, **kwargs: typing.Any
    ) -> None:
        contents, is_updated = await self._fetch_contents()
        if is_updated:
            products = await self._parse_contents(contents)
            await self._update(contents, products, await_handlers, **kwargs)

    async def update_forever_blocking(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: typing.Any
    ) -> None:
        while True:
            await self.update(await_handlers, **kwargs)
            await asyncio.sleep(interval)

    async def update_forever(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: typing.Any
    ) -> None:
        self._update_forever_task = asyncio.create_task(
            self.update_forever_blocking(interval, await_handlers, **kwargs)
            )

    async def await_update_handlers(self) -> None:
        await self._runner.await_all()

    async def cancel_update_handlers(self) -> None:
        await self._runner.cancel_all()

    async def cancel_update_forever(self) -> None:
        if self._update_forever_task:
            task = self._update_forever_task
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                logger.debug('Task "%s" has been cancelled', task.get_name())
            self._update_forever_task = None

    def find_product_by_id(self, id: int) -> typing.Optional[Product]:
        return self._products.get(id)

    def find_product(
        self,
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes
    ) -> typing.Optional[Product]:
        return ProductFinder.find_product(
            self._products.values(), constraint, **attributes
            )

    def find_products(
        self,
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes
    ) -> list[Product]:
        return ProductFinder.find_products(
            self._products.values(), constraint, **attributes
            )


class FreshPointProductPageHub:
    def __init__(
        self,
        client: typing.Optional[ProductDataFetchClient] = None,
        enable_multiprocessing: bool = False
    ) -> None:
        self._client = client or ProductDataFetchClient()
        self._pages: dict[int, FreshPointProductPage] = {}
        self._publisher = ProductUpdateEventPublisher()
        executor = ProcessPoolExecutor() if enable_multiprocessing else None
        self._runner = SafeAsyncTaskRunner(executor=executor)

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        await self.start_session()
        try:
            await asyncio.sleep(0)
        except Exception as exc:
            await self.close_session()
            raise exc
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        await self.close_session()
        await self.await_update_handlers()

    def subscribe_for_update(
        self,
        event: ProductUpdateEvent,
        handler: Handler
    ) -> None:
        self._publisher.subscribe(event, handler)
        for page in self._pages.values():
            page.subscribe_for_update(event, handler)

    def unsubscribe_from_update(
        self,
        event: ProductUpdateEvent,
        handler: typing.Optional[Handler] = None
    ) -> None:
        self._publisher.unsubscribe(event, handler)
        for page in self._pages.values():
            page.unsubscribe_from_update(event, handler)

    def set_context(self, key: typing.Any, value: typing.Any) -> None:
        self._publisher.context[key] = value
        for page in self._pages.values():
            page.context[key] = value

    async def start_session(self) -> None:
        await self._client.start_session()

    async def close_session(self) -> None:
        await self._client.close_session()
        await self.cancel_update_handlers()
        if self._runner.executor:
            self._runner.executor.shutdown(wait=True)

    async def _register_page(
        self,
        page: FreshPointProductPage,
        update_contents: bool,
        trigger_handlers: bool = False
    ) -> None:
        self._pages[page.location_id] = page
        # add common handlers
        pub = self._publisher
        for subscribers in (pub.sync_subscribers, pub.async_subscribers):
            assert isinstance(subscribers, dict)
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

    async def scan(self, location_range: int = 500) -> None:
        for loc in range(1, location_range + 1):
            await self.new_page(
                location_id=loc,
                fetch_contents=False,
                trigger_handlers=False
                )
        await self.update_silently()
        locs = [loc for loc, page in self._pages.items() if not page.products]
        for loc in locs:
            del self._pages[loc]

    async def new_page(
        self,
        location_id: int,
        fetch_contents: bool = False,
        trigger_handlers: bool = False
    ) -> FreshPointProductPage:
        page = FreshPointProductPage(location_id, client=self._client)
        await self._register_page(page, fetch_contents, trigger_handlers)
        return page

    async def add_page(
        self,
        page: FreshPointProductPage,
        update_contents: bool = False,
        trigger_handlers: bool = False
    ) -> None:
        if page.client != self._client:
            await page.set_client(self._client)
        await self._register_page(page, update_contents, trigger_handlers)

    async def remove_page(
        self,
        location_id: int,
        await_handlers: bool = False
    ) -> None:
        if location_id not in self._pages:
            return
        page = self._pages.pop(location_id)
        if await_handlers:
            await page.await_update_handlers()
        else:
            await page.cancel_update_handlers()

    async def _fetch_contents(self) -> dict[int, tuple[str, bool]]:
        tasks: list[asyncio.Task] = []
        for page in self._pages.values():
            tasks.append(self._runner.run_async(page._fetch_contents()))
        results: list[tuple[str, bool]] = await asyncio.gather(*tasks)
        return dict(zip(self._pages.keys(), results))

    def _filter_updated_contents(
        self, contents: dict[int, tuple[str, bool]]
    ) -> dict[int, str]:
        return {
            page_id: contents_info[0]  # 0, 1 == page_html_contents, is_updated
            for page_id, contents_info in contents.items() if contents_info[1]
            }

    async def _parse_contents(
        self, contents: dict[int, str]
    ) -> dict[int, list[Product]]:
        tasks: list[asyncio.Task] = []
        for page_id, page_contents in contents.items():
            func = self._pages[page_id]._parse_contents_blocking
            tasks.append(self._runner.run_sync(func, page_contents))
        results: list[list[Product]] = await asyncio.gather(*tasks)
        return dict(zip(contents.keys(), results))

    async def update_silently(self) -> None:
        contents = await self._fetch_contents()
        contents_to_update = self._filter_updated_contents(contents)
        products = await self._parse_contents(contents_to_update)
        for page_id, page_products in products.items():
            page = self._pages[page_id]
            page._update_silently(contents_to_update[page_id], page_products)

    async def update(
        self,
        await_handlers: bool = False,
        **kwargs
    ) -> None:
        contents = await self._fetch_contents()
        contents_to_update = self._filter_updated_contents(contents)
        products = await self._parse_contents(contents_to_update)
        tasks: list[asyncio.Task] = []
        for page_id, page_products in products.items():
            page = self._pages[page_id]
            page_contents = contents_to_update[page_id]
            task = self._runner.run_async(
                page._update(
                    page_contents, page_products, await_handlers, **kwargs
                    )
                )
            tasks.append(task)
        await asyncio.gather(*tasks)

    async def update_forever(
        self,
        interval: float = 10.0,
        await_handlers: bool = False,
        **kwargs: typing.Any
    ) -> None:
        while True:
            await self.update(await_handlers, **kwargs)
            await asyncio.sleep(interval)

    async def await_update_handlers(self) -> None:
        tasks = [p.await_update_handlers() for p in self._pages.values()]
        await asyncio.gather(*tasks)

    async def cancel_update_handlers(self) -> None:
        tasks = [p.cancel_update_handlers() for p in self._pages.values()]
        await asyncio.gather(*tasks)
