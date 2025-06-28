import asyncio
import logging
import sys
from abc import ABC, abstractmethod
from concurrent.futures import ProcessPoolExecutor  # noqa
from dataclasses import dataclass
from typing import (
    Any,
    Callable,
    Dict,
    Generic,
    Optional,
    Type,
    TypeVar,
    Union,
)

from freshpointparser import get_location_page_url, get_product_page_url
from freshpointparser.models import BasePage, LocationPage, ProductPage
from freshpointparser.parsers import (
    BasePageHTMLParser,
    LocationPageHTMLParser,
    ProductPageHTMLParser,
)
from pydantic import BaseModel, ConfigDict, Field  # noqa
from pydantic.alias_generators import to_camel  # noqa

from ..client._client import PageHTMLClient
from ..runner._runner import CallableRunner
from ..update._update import ItemUpdateContext, PageUpdateContext, UpdatePublisher

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


logger = logging.getLogger('freshpointsync.page')
"""Logger for the `freshpointsync.page` package."""


TPageHTMLParser = TypeVar('TPageHTMLParser', bound=BasePageHTMLParser)
TPage = TypeVar('TPage', bound=BasePage)


@dataclass
class ParseResult(Generic[TPage]):
    page_old: Optional[TPage] = None
    page_new: Optional[TPage] = None
    parsed: Optional[bool] = None


class BasePageClient(ABC, Generic[TPageHTMLParser, TPage]):
    """Product page object that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        parser: TPageHTMLParser,
        **client_kwargs: Any,
    ) -> None:
        self._parser = parser
        self._client = PageHTMLClient(**client_kwargs)
        self._update_context: dict[Any, Any] = {}
        self._publisher_page = UpdatePublisher()
        self._publisher_items = UpdatePublisher()
        self._runner = CallableRunner()

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

        async def _fetch_content() -> str:
            return await self._client.fetch(url, retries=retries, **kwargs)

        content = await self._runner.run_async(_fetch_content)
        if content is None:
            logger.warning('Failed to fetch content from page %s', url)
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
        parser = await self._runner.run_sync(  # parser == self._parser
            self._parser.parse,
            content,
            force,
            run_safe=False,  # run_safe=True crashes ProcessPoolExecutor
        )
        if parser is None:  # means something went wrong when running parser.parse()
            logger.warning(
                'Failed to parse content from page %s', self._construct_page_url()
            )
            return ParseResult()
        if page_old is None:  # if the old page was not set, use the new one
            page_old = self._parser.page
        return ParseResult(
            page_old=page_old,
            page_new=self._parser.page,
            parsed=parser.parse_status,
        )

    async def _post(
        self,
        page_new: TPage,
        page_old: TPage,
        await_handlers: bool,
        **kwargs: Any,
    ) -> None:
        page_diff = page_new.item_diff(page_old)
        page_update_context = PageUpdateContext(
            page_new=page_new,
            page_old=page_old,
            page_diff=page_diff,
            context={**self._update_context, **kwargs},
        )
        tasks = [asyncio.create_task(self._publisher_page.post(page_update_context))]
        for item_id in page_diff:
            item_new = page_new.items.get(item_id)
            item_old = page_old.items.get(item_id)
            item_diff = page_diff[item_id]
            item_update_context = ItemUpdateContext(
                item_new=item_new,
                item_old=item_old,
                item_diff=item_diff,
                context={**self._update_context, **kwargs},
            )
            task = asyncio.create_task(self._publisher_items.post(item_update_context))
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

    async def start_session(self) -> None:
        self._client.start_session()

    async def close_session(self) -> None:
        """Close the aiohttp client session if one is open."""
        await self._client.close_session()
        await self.cancel_update_handlers()
        if self._runner.executor:
            self._runner.executor.shutdown(wait=True)

    def subscribe_for_item_update(
        self,
        handler: Callable,
        filter_: Callable,
    ) -> None:
        self._publisher_items.subscribe(handler, filter_)

    def unsubscribe_from_item_update(
        self,
        handler: Callable,
    ) -> None:
        self._publisher_items.unsubscribe(handler)

    def subscribe_for_page_update(
        self,
        handler: Callable,
        filter_: Callable,
    ) -> None:
        """Subscribe to page update events."""
        self._publisher_page.subscribe(handler, filter_)

    def unsubscribe_from_page_update(
        self,
        handler: Callable,
    ) -> None:
        """Unsubscribe from page update events."""
        self._publisher_page.unsubscribe(handler)

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
        if not parse_result.page_new or not parse_result.page_old:
            return  # should not happen (guarded by parse_result.parsed)
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


class ProductPageClient(BasePageClient[ProductPageHTMLParser, ProductPage]):
    """Product page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        location_id: Union[str, int],
        **client_kwargs: Any,
    ) -> None:
        super().__init__(ProductPageHTMLParser(), **client_kwargs)
        self._location_id = location_id

    def _construct_page_url(self) -> str:
        return get_product_page_url(self._location_id)


class LocationPageClient(BasePageClient[LocationPageHTMLParser, LocationPage]):
    """Location page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(self, **client_kwargs: Any) -> None:
        super().__init__(LocationPageHTMLParser(), **client_kwargs)

    def _construct_page_url(self) -> str:  # noqa: PLR6301
        return get_location_page_url()


class BasePageHub(Generic[TPageHTMLParser, TPage]):
    """Base class for a page hub that manages multiple product pages."""

    def __init__(self, **client_kwargs: Any) -> None:
        self._client = PageHTMLClient(**client_kwargs)
        self._update_context: dict[Any, Any] = {}
        self._publisher_page = UpdatePublisher()
        self._publisher_items = UpdatePublisher()
        self._runner = CallableRunner()
        self._pages: Dict[str, BasePageClient[TPageHTMLParser, TPage]] = {}

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

    async def start_session(self) -> None:
        self._client.start_session()

    async def close_session(self) -> None:
        await self._client.close_session()
