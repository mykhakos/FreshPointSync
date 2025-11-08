import asyncio
import logging
import sys
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor
from dataclasses import dataclass
from typing import (
    Any,
    Dict,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
)

from freshpointparser import get_location_page_url, get_product_page_url
from freshpointparser.models import (
    BaseItem,
    BasePage,
    Location,
    LocationPage,
    Product,
    ProductPage,
)
from freshpointparser.parsers import (
    BasePageHTMLParser,
    LocationPageHTMLParser,
    ProductPageHTMLParser,
)

from ._callable_runner import AwaitableRunner as CallableRunner
from ._html_client import PageHTMLClient
from .update._update import (
    ItemUpdateContext,
    PageUpdateContext,
    UpdateConsumerRegistry,
    UpdatePublisher,
)

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


logger = logging.getLogger('freshpointsync.page')
"""Logger for the `freshpointsync.page` package."""


TPageHTMLParser = TypeVar('TPageHTMLParser', bound=BasePageHTMLParser)
TPage = TypeVar('TPage', bound=BasePage)
TItem = TypeVar('TItem', bound=BaseItem)


@dataclass
class ParseResult(Generic[TPage]):
    page_old: Optional[TPage] = None
    page_new: Optional[TPage] = None
    parsed: Optional[bool] = None


class BasePageClient(ABC, Generic[TPageHTMLParser, TPage, TItem]):
    """Product page object that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        parser: TPageHTMLParser,
        enable_multiprocessing: bool = False,
        **client_kwargs: Any,
    ) -> None:
        self._parser = parser
        self._client = PageHTMLClient(**client_kwargs)
        self._update_context: dict[Any, Any] = {}
        self._update_registry_page = UpdateConsumerRegistry[PageUpdateContext[TPage]]()
        self._update_registry_items = UpdateConsumerRegistry[ItemUpdateContext[TItem]]()
        self._update_publisher_page = UpdatePublisher(
            registry=self._update_registry_page
        )
        self._update_publisher_items = UpdatePublisher(
            registry=self._update_registry_items
        )
        self._runner = CallableRunner()
        if enable_multiprocessing:
            self._executor = ProcessPoolExecutor(max_workers=None)
        else:
            self._executor = None

    def __str__(self) -> str:
        return self._construct_page_url()

    async def __aenter__(self) -> Self:
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

    @abstractmethod
    def _construct_page_url(self) -> str:
        """Construct the URL of the product page."""
        pass

    async def _fetch_content(self, retries: int = 3, **kwargs: Any) -> str:
        """Fetch the HTML content of the product page."""
        url = self._construct_page_url()
        try:
            content = await self._client.fetch(url, retries=retries, **kwargs)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('Failed to fetch content from page %s: %s', url, exc)
            return ''
        return content

    async def _parse_content(self, content: str, force: bool) -> ParseResult:
        """Parse the content of the product page and extract product data. If the data
        has changed, return the differences between the old and new product data.
        """
        if self._parser.parse_status is not None:  # store the old page if it exists
            page_old = self._parser.page
        else:
            page_old = None
        loop = asyncio.get_running_loop()
        try:
            await loop.run_in_executor(
                self._executor, self._parser.parse, content, force
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning(
                'Failed to parse content from page %s: %s',
                self._construct_page_url(),
                exc,
            )
            return ParseResult()
        if page_old is None:  # if the old page was not set, use the new one
            page_old = self._parser.page
        return ParseResult(
            page_old=page_old,
            page_new=self._parser.page,
            parsed=self._parser.parse_status,
        )

    async def _post(
        self,
        page_new: TPage,
        page_old: TPage,
        await_handlers: bool,
        **kwargs: Any,
    ) -> None:
        page_url = self._construct_page_url()
        page_diff = page_new.item_diff(page_old)
        if not page_diff:
            logger.debug('No changes detected in page %s', page_url)
            return
        page_update_context = PageUpdateContext(
            page_new=page_new,
            page_old=page_old,
            page_diff=page_diff,
            context={**self._update_context, **kwargs},
        )
        tasks = [
            self._runner.run(self._update_publisher_page.post(page_update_context))
        ]
        for item_id in page_diff:
            item_diff = page_diff[item_id]
            if not item_diff:
                logger.debug(
                    'No changes detected for item %s in page %s', item_id, page_url
                )
                continue
            item_new = page_new.items.get(item_id)
            item_old = page_old.items.get(item_id)
            item_update_context = ItemUpdateContext(
                item_new=item_new,
                item_old=item_old,
                item_diff=item_diff,
                context={**self._update_context, **kwargs},
            )
            task = self._runner.run(
                self._update_publisher_items.post(item_update_context)
            )
            tasks.append(task)
        if await_handlers:
            await self._runner.await_(tasks)

    @property
    def data(self) -> TPage:
        """Current parsed page data."""
        return self._parser.page

    @property
    def update_context(self) -> Dict[Any, Any]:
        """Update context passed to event handlers."""
        return self._update_context

    @property
    def page_update(self) -> UpdateConsumerRegistry[PageUpdateContext[TPage]]:
        """Registry for page update event handlers."""
        return self._update_registry_page

    @property
    def item_update(self) -> UpdateConsumerRegistry[ItemUpdateContext[TItem]]:
        """Registry for item update event handlers."""
        return self._update_registry_items

    async def start_session(self) -> None:
        self._client.start_session()

    async def close_session(self, await_update_handlers: bool = True) -> None:
        """Close the aiohttp client session if one is open."""
        if await_update_handlers:
            await self.await_update_handlers()
        else:
            await self.cancel_update_handlers()
        await self._client.close_session()
        # if self._runner.executor:
        #     self._runner.executor.shutdown(wait=True)

    async def update(
        self,
        force: bool = False,
        silent: bool = False,
        await_handlers: bool = False,
        **kwargs: Any,
    ) -> None:
        """Fetch the content of the product page, extract the product data,
        update the internal state of the page, and trigger event handlers.

        Args:
            force (bool, optional): If True, the content is parsed even if
                the product data has not changed. Defaults to False.
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            await_handlers (bool, optional): If True, all event handlers are
                awaited to complete execution. This parameter has no effect if
                `silent` is True. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        content = await self._fetch_content()
        if not content:
            return
        parse_result = await self._parse_content(content, force)
        if silent or not parse_result.parsed:
            return
        # should not happen - guarded by parse_result.parsed
        assert parse_result.page_new is not None, 'New parsed page cannot be None'
        assert parse_result.page_old is not None, 'Old parsed page cannot be None'
        await self._post(
            parse_result.page_new,
            parse_result.page_old,
            await_handlers,
            **kwargs,
        )

    async def update_forever(
        self,
        interval: float = 10.0,
        force: bool = False,
        silent: bool = False,
        await_handlers: bool = False,
        **kwargs: Any,
    ) -> None:
        """Update the product page at regular intervals.

        This method is a coroutine that runs indefinitely, updating
        the product page at regular intervals.

        Args:
            interval (float, optional): The time interval in seconds between
                updates. Defaults to 10.0.
            force (bool, optional): If True, the content is parsed even if
                the product data has not changed. Defaults to False.
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
                await self.update(force, silent, await_handlers, **kwargs)
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)

    async def await_update_handlers(self) -> None:
        """Wait for all event handlers to complete execution."""
        await self._runner.await_all()

    async def cancel_update_handlers(self) -> None:
        """Cancel all running event handlers."""
        await self._runner.cancel_all()


class ProductPageClient(BasePageClient[ProductPageHTMLParser, ProductPage, Product]):
    """Product page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        location_id: Union[str, int],
        enable_multiprocessing: bool = False,
        **client_kwargs: Any,
    ) -> None:
        super().__init__(
            ProductPageHTMLParser(),
            enable_multiprocessing=enable_multiprocessing,
            **client_kwargs,
        )
        self._location_id = location_id

    def _construct_page_url(self) -> str:
        return get_product_page_url(self._location_id)


class LocationPageClient(
    BasePageClient[LocationPageHTMLParser, LocationPage, Location]
):
    """Location page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        enable_multiprocessing: bool = False,
        **client_kwargs: Any,
    ) -> None:
        super().__init__(
            LocationPageHTMLParser(),
            enable_multiprocessing=enable_multiprocessing,
            **client_kwargs,
        )

    def _construct_page_url(self) -> str:  # noqa: PLR6301
        return get_location_page_url()


def group_pages(*pages: BasePageClient) -> ProcessPoolExecutor:
    executor = ProcessPoolExecutor(max_workers=None)
    for page in pages:
        page._executor = executor
    return executor


class PageClientGroup:
    def __init__(
        self,
        enable_multiprocessing: bool = False,
        **client_kwargs: Any,
    ) -> None:
        self._client = PageHTMLClient(**client_kwargs)
        if enable_multiprocessing:
            self._executor = ProcessPoolExecutor(max_workers=None)
        else:
            self._executor = None
        self._pages: Dict[str, BasePageClient] = {}

    def add_page(self, page: BasePageClient) -> None:
        page._client = self._client
        page._executor = self._executor
        page_url = page._construct_page_url()
        self._pages[page_url] = page


# class PageClientGroup:
#     def __init__(
#         self, *, use_multiprocessing: bool = False, **client_kwargs: Any
#     ) -> None:
#         self._client = PageHTMLClient(**client_kwargs)
#         self._update_context: dict[Any, Any] = {}
#         self._publisher_page = UpdatePublisher()
#         self._publisher_items = UpdatePublisher()
#         self._pages: Dict[str, BasePageClient] = {}
#         if use_multiprocessing:
#             executor = ProcessPoolExecutor(max_workers=None)
#             self._runner = CallableRunner(executor=executor)
#         else:
#             self._runner = CallableRunner()

#     async def __aenter__(self) -> Self:
#         """Asynchronous context manager entry."""
#         await self.start_session()
#         return self

#     async def __aexit__(
#         self,
#         exc_type: Optional[Type[BaseException]],
#         exc_value: Optional[BaseException],
#         traceback: Optional[object],
#     ) -> None:
#         """Asynchronous context manager exit."""
#         await self.close_session()

#     async def _group_item_update_proxy(self, context: ItemUpdateContext) -> None:
#         """Proxy method to post item update events."""
#         await self._runner.run_async(self._publisher_items.post, context)

#     async def _group_page_update_proxy(self, context: PageUpdateContext) -> None:
#         """Proxy method to post page update events."""
#         await self._runner.run_async(self._publisher_page.post, context)

#     @property
#     def update_context(self) -> Dict[Any, Any]:
#         """Update context passed to event handlers."""
#         return self._update_context

#     async def start_session(self) -> None:
#         self._client.start_session()

#     async def close_session(self, await_update_handlers: bool = True) -> None:
#         if await_update_handlers:
#             await self.await_update_handlers()
#         else:
#             await self.cancel_update_handlers()
#         for page in self._pages.values():
#             await self.remove_page(page, await_update_handlers)
#         await self._client.close_session()
#         if self._runner.executor:
#             self._runner.executor.shutdown()

#     def subscribe_for_item_update(
#         self, handler: Handler, filter_: Optional[Filter] = None
#     ) -> None:
#         self._publisher_items.subscribe(handler, filter_)

#     def unsubscribe_from_item_update(self, handler: Handler) -> None:
#         self._publisher_items.unsubscribe(handler)

#     def subscribe_for_page_update(
#         self, handler: Handler, filter_: Optional[Filter] = None
#     ) -> None:
#         """Subscribe to page update events."""
#         self._publisher_page.subscribe(handler, filter_)

#     def unsubscribe_from_page_update(self, handler: Handler) -> None:
#         """Unsubscribe from page update events."""
#         self._publisher_page.unsubscribe(handler)

#     async def add_page(self, page: BasePageClient) -> None:
#         """Add a page to the group."""
#         page_url = page._construct_page_url()
#         if page_url in self._pages:
#             logger.warning('Page %s already exists in the group.', page_url)
#             return
#         logger.info('Adding page %s to the group.', page_url)
#         await page.close_session()
#         page._client = self._client
#         page._runner = self._runner
#         page.subscribe_for_item_update(handler=self._group_item_update_proxy)
#         page.subscribe_for_page_update(handler=self._group_page_update_proxy)
#         self._pages[page_url] = page

#     async def remove_page(
#         self, page: BasePageClient, await_update_handlers: bool = True
#     ) -> None:
#         """Remove a page from the group."""
#         page_url = page._construct_page_url()
#         if page_url not in self._pages:
#             logger.warning('Page %s does not exist in the group.', page_url)
#             return
#         logger.info('Removing page %s from the group.', page_url)
#         if await_update_handlers:
#             await page.await_update_handlers()
#         else:
#             await page.cancel_update_handlers()
#         self._pages.pop(page_url)
#         page.unsubscribe_from_item_update(self._group_item_update_proxy)
#         page.unsubscribe_from_page_update(self._group_page_update_proxy)
#         page._client = PageHTMLClient()
#         page._runner = CallableRunner()

#     def get_page(self, page_url: str) -> Optional[BasePageClient]:
#         """Get a page by its URL."""
#         return self._pages.get(page_url)

#     async def update_all(
#         self,
#         force: bool = False,
#         silent: bool = False,
#         await_handlers: bool = False,
#         **kwargs: Any,
#     ) -> None:
#         update_tasks = [
#             self._runner.run_async(page.update, force, silent, await_handlers, **kwargs)
#             for page in self._pages.values()
#         ]
#         await self._runner.await_(update_tasks)

#     async def update_all_forever(
#         self,
#         interval: float = 10.0,
#         force: bool = False,
#         silent: bool = False,
#         await_handlers: bool = False,
#         **kwargs: Any,
#     ) -> None:
#         """Update all pages at regular intervals."""
#         while True:
#             try:
#                 await self.update_all(force, silent, await_handlers, **kwargs)
#             except asyncio.CancelledError:
#                 break
#             await asyncio.sleep(interval)

#     async def await_update_handlers(self) -> None:
#         """Wait for all event handlers to complete execution."""
#         await self._runner.await_all()

#     async def cancel_update_handlers(self) -> None:
#         """Cancel all running event handlers."""
#         await self._runner.cancel_all()
