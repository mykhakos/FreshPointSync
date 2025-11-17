import sys
import time
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


class PageClient(BasePageClient[httpx.Client, TPageHTMLParser, TPage, TItem]):
    def __init__(
        self,
        url: str,
        client: Optional[httpx.Client],
        owns_client: bool,
        parser: TPageHTMLParser,
    ) -> None:
        super().__init__(url, client, httpx.Client, owns_client, parser)

    def __enter__(self) -> Self:
        """Synchronous context manager entry."""
        if self._owns_client:
            self._client.__enter__()
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:  # noqa: ANN001
        """Synchronous context manager exit."""
        self.close()

    def _fetch_content(self, **kwargs: Any) -> FetchResult:
        """Fetch the HTML content of the product page."""
        try:
            response = self._client.get(url=self._url, **kwargs)
            response.raise_for_status()
            return FetchResult(content=response.text)
        except httpx.HTTPError as exc:
            logger.warning('Failed to fetch content from page %s: %s', self._url, exc)
            return FetchResult(err=exc)

    def _parse_content(self, content: str, force: bool) -> ParseResult:
        """Parse the content of the product page and extract product data. If the data
        has changed, return the differences between the old and new product data.
        """
        if self._parser.parse_status is None:  # store the old page if it exists
            page_old = None
        else:
            page_old = self._parser.page

        try:
            self._parser.parse(content, force)
        except Exception as exc:
            logger.warning('Failed to parse content from page %s: %s', self._url, exc)
            return ParseResult(err=exc)

        if page_old is None:  # if the old page was not set, use the new one
            page_old = self._parser.page

        return ParseResult(page_old=page_old, page_new=self._parser.page)

    def _execute_update_hooks(self, parse_result: ParseResult) -> None:
        page_update_context = self._get_page_update_context(parse_result)
        if page_update_context.page_diff:
            for hook in self._update_hooks:
                hook(page_update_context)

    def close(self) -> None:
        """Close the client session if one is open."""
        if self._owns_client:
            self._client.close()

    def update(
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
        fetch_result = self._fetch_content(**kwargs)
        if fetch_result.err:
            return
        parse_result = self._parse_content(fetch_result.content, force)
        if silent or parse_result.err:
            return
        self._execute_update_hooks(parse_result)

    def update_forever(
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
                self.update(force, silent, **kwargs)
            except KeyboardInterrupt:
                break
            time.sleep(interval)


class FreshPoint(PageClient[ProductPageHTMLParser, ProductPage, Product]):
    """Product page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        location_id: Union[str, int],
        client: Optional[httpx.Client] = None,
        owns_client: bool = True,
    ) -> None:
        super().__init__(
            url=get_product_page_url(location_id),
            client=client,
            owns_client=owns_client,
            parser=ProductPageHTMLParser(),
        )


class FreshPointLocations(PageClient[LocationPageHTMLParser, LocationPage, Location]):
    """Location page client that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        client: Optional[httpx.Client] = None,
        owns_client: bool = True,
    ) -> None:
        super().__init__(
            url=get_location_page_url(),
            client=client,
            owns_client=owns_client,
            parser=LocationPageHTMLParser(),
        )


# class PageClientGroup:
#     """Group of page clients that can be managed together."""

#     def __init__(self, fetcher: PageHTMLFetcher | None = None) -> None:
#         self._fetcher = fetcher if fetcher is not None else PageHTMLFetcher()
#         self._pages: Dict[str, PageClient] = {}
#         self._executor = ThreadPoolExecutor()

#     def __enter__(self) -> Self:
#         self._fetcher.start_session()
#         return self

#     def __exit__(self, exc_type, exc_value, traceback) -> None:
#         self._fetcher.close_session()
#         self._executor.shutdown(wait=True)

#     def _add_page(self, page: PageClient) -> None:
#         self._pages[page.url] = page

#     def _get_page(self, url: str) -> PageClient:
#         page = self._pages.get(url)
#         if page is None:
#             raise KeyError(f"Page with URL '{url}' was not found.")
#         return page

#     def _remove_page(self, url: str) -> None:
#         self._pages.pop(url, None)

#     def add_product_page(self, id_: Union[str, int]) -> None:
#         """Add a product page client to the group."""
#         page = ProductPageClient(location_id=id_, fetcher=self._fetcher)
#         self._add_page(page)

#     def get_product_page(self, id_: Union[str, int]) -> ProductPageClient:
#         """Get a product page client by location ID."""
#         return self._get_page(get_product_page_url(id_))  # type: ignore[return-value]

#     def remove_product_page(self, id_: Union[str, int]) -> None:
#         """Remove a product page client from the group by location ID."""
#         self._remove_page(get_product_page_url(id_))

#     def add_location_page(self) -> None:
#         """Add the location page client to the group."""
#         page = LocationPageClient(fetcher=self._fetcher)
#         self._add_page(page)

#     def get_location_page(self) -> LocationPageClient:
#         """Get the location page client."""
#         return self._get_page(get_location_page_url())  # type: ignore[return-value]

#     def remove_location_page(self) -> None:
#         """Remove the location page client from the group."""
#         self._remove_page(get_location_page_url())

#     def update(
#         self,
#         force: bool = False,
#         silent: bool = False,
#         **kwargs: Any,
#     ) -> None:
#         # Phase 1: Fetch all pages in parallel (I/O-bound - threads excel)
#         fetch_futures = []
#         for page in self._pages.values():
#             future = self._executor.submit(page._fetch_content, **kwargs)
#             fetch_futures.append((page, future))

#         fetch_results = [(page, future.result()) for page, future in fetch_futures]

#         # Phase 2: Parse all pages in parallel (CPU-bound - threads still help)
#         parse_futures = []
#         for page, result in fetch_results:
#             if not result.fetched:
#                 continue
#             future = self._executor.submit(
#                 page._parse_content, page._parser, result.content, force
#             )
#             parse_futures.append((page, future))

#         # Phase 3: Execute update hooks
#         for page, future in parse_futures:
#             parse_result = future.result()
#             if silent or not parse_result.parsed:
#                 continue
#             page._execute_update_hooks(parse_result, **kwargs)
