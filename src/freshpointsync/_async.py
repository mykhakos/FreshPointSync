import asyncio
import inspect
import sys
from typing import (
    Any,
    Optional,
    Union,
)

import httpx
from freshpointparser import get_location_page_url, get_product_page_url
from freshpointparser.models import (
    Location,
    LocationPage,
    Product,
    ProductPage,
)
from freshpointparser.parsers import (
    LocationPageHTMLParser,
    ProductPageHTMLParser,
)

from ._base import (
    BasePageClient,
    FetchResult,
    ParseResult,
    TItem,
    TPage,
    TPageHTMLParser,
    logger,
)

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


class AsyncPageClient(BasePageClient[httpx.AsyncClient, TPageHTMLParser, TPage, TItem]):
    def __init__(
        self,
        url: str,
        client: Optional[httpx.AsyncClient],
        owns_client: bool,
        parser: TPageHTMLParser,
    ) -> None:
        super().__init__(url, client, httpx.AsyncClient, owns_client, parser)

    async def __aenter__(self) -> Self:
        """Asynchronous context manager entry."""
        if self._owns_client:
            await self._client.__aenter__()
        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> None:  # noqa: ANN001
        """Asynchronous context manager exit."""
        await self.close()

    async def _fetch_content(self, **kwargs: Any) -> FetchResult:
        """Fetch the HTML content of the product page."""
        try:
            response = await self._client.get(url=self._url, **kwargs)
            response.raise_for_status()
            return FetchResult(content=response.text)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('Failed to fetch content from page %s: %s', self._url, exc)
            return FetchResult(err=exc)

    async def _parse_content(self, content: str, force: bool) -> ParseResult:
        """Parse the content of the product page and extract product data. If the data
        has changed, return the differences between the old and new product data.
        """
        if self._parser.parse_status is None:  # store the old page if it exists
            page_old = None
        else:
            page_old = self._parser.page

        loop = asyncio.get_running_loop()
        try:
            self._parser = await loop.run_in_executor(
                None, self._parser.parse, content, force
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.warning('Failed to parse content from page %s: %s', self._url, exc)
            return ParseResult(err=exc)

        if page_old is None:  # if the old page was not set, use the new one
            page_old = self._parser.page

        return ParseResult(page_old=page_old, page_new=self._parser.page)

    async def _execute_update_hooks(self, parse_result: ParseResult) -> None:
        page_update_context = self._get_page_update_context(parse_result)
        if page_update_context.page_diff:
            hooks_to_await = []
            for hook in self._update_hooks:
                result = hook(page_update_context)
                if inspect.isawaitable(result):
                    hooks_to_await.append(result)
            await asyncio.gather(*hooks_to_await)

    async def close(self) -> None:
        """Close the aiohttp client session if one is open."""
        if self._owns_client:
            await self._client.aclose()

    async def update(
        self,
        force: bool = False,
        silent: bool = False,
        **kwargs: Any,
    ) -> None:
        """Fetch the content of the product page, extract the product data,
        update the internal state of the page, and trigger event handlers.

        Args:
            force (bool, optional): If True, the content is parsed even if
                the product data has not changed. Defaults to False.
            silent (bool, optional): If True, the product data is updated
                without triggering any event handlers. Defaults to False.
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        fetch_result = await self._fetch_content(**kwargs)
        if fetch_result.err:
            return
        parse_result = await self._parse_content(fetch_result.content, force)
        if silent or parse_result.err:
            return
        await self._execute_update_hooks(parse_result)

    async def update_forever(
        self,
        interval: float = 10.0,
        force: bool = False,
        silent: bool = False,
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
            **kwargs (Any): Additional keyword arguments to pass to the event
                handlers. If the `silent` parameter is True, these arguments
                are ignored.
        """
        while True:
            try:
                await self.update(force, silent, **kwargs)
            except asyncio.CancelledError:
                break
            await asyncio.sleep(interval)


class AsyncFreshPoint(AsyncPageClient[ProductPageHTMLParser, ProductPage, Product]):
    """Product page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        location_id: Union[str, int],
        client: Optional[httpx.AsyncClient] = None,
        owns_client: bool = True,
    ) -> None:
        super().__init__(
            url=get_product_page_url(location_id),
            client=client,
            owns_client=owns_client,
            parser=ProductPageHTMLParser(),
        )


class AsyncFreshPointLocations(
    AsyncPageClient[LocationPageHTMLParser, LocationPage, Location]
):
    """Location page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        client: Optional[httpx.AsyncClient] = None,
        owns_client: bool = True,
    ) -> None:
        super().__init__(
            url=get_location_page_url(),
            client=client,
            owns_client=owns_client,
            parser=LocationPageHTMLParser(),
        )
