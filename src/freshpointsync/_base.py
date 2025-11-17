import logging
from abc import ABC
from dataclasses import dataclass
from typing import Any, Callable, Dict, Generic, List, Optional, Type, TypeVar, Union

import httpx
from freshpointparser.models import BaseItem, BasePage
from freshpointparser.models.types import FieldDiff, ModelDiffMapping
from freshpointparser.parsers import BasePageHTMLParser
from httpx_retries import Retry, RetryTransport

from ._config import config

logger = logging.getLogger('freshpointsync')
"""Main logger for the `freshpointsync` library."""


TClient = TypeVar('TClient', bound=Union[httpx.Client, httpx.AsyncClient])
TPageHTMLParser = TypeVar('TPageHTMLParser', bound=BasePageHTMLParser)
TPage = TypeVar('TPage', bound=BasePage)
TItem = TypeVar('TItem', bound=BaseItem)


@dataclass(frozen=True, eq=True)
class FetchResult(Generic[TPage]):
    content: str = ''
    err: Optional[Exception] = None


@dataclass(frozen=True, eq=True)
class ParseResult(Generic[TPage]):
    page_old: Optional[TPage] = None
    page_new: Optional[TPage] = None
    err: Optional[Exception] = None


@dataclass(frozen=True, eq=True)
class PageUpdateContext(Generic[TPage]):
    page_new: Optional[TPage]
    page_old: Optional[TPage]
    page_diff: ModelDiffMapping
    context: Dict[Any, Any]

    def get_item_attr_diff(
        self, item_id: Union[str, int], attr: str
    ) -> Optional[FieldDiff]:
        """Get the diff for a specific attribute of the item if it exists.

        Shortcut for `context.page_diff[item_id]['diff'][attr]` with safety checks.

        Args:
            item_id (Union[str, int]): The ID of the item.
            attr (str): The name of the item attribute to get the diff for.

        Returns:
            Optional[FieldDiff]: The field diff if it exists, otherwise None.
        """
        return self.page_diff.get(int(item_id), {}).get('diff', {}).get(attr)


class BasePageClient(ABC, Generic[TClient, TPageHTMLParser, TPage, TItem]):
    """Product page object that provides methods for fetching, updating, and
    managing product data on the page. May be used as an asynchronous context
    manager.
    """

    def __init__(
        self,
        url: str,
        client: Optional[TClient],
        client_cls: Type[TClient],
        owns_client: bool,
        parser: TPageHTMLParser,
    ) -> None:
        self._url = url

        if client is None:
            self._client = client_cls(
                timeout=config.httpx.timeout,
                transport=RetryTransport(
                    retry=Retry(
                        total=config.httpx.retries_total,
                        max_backoff_wait=config.httpx.retries_max_backoff_wait,
                        backoff_factor=config.httpx.retries_backoff_factor,
                        backoff_jitter=config.httpx.retries_backoff_jitter,
                        allowed_methods={'GET'},
                    )
                ),
            )
            if owns_client is False:
                logger.warning(
                    "'owns_client' parameter is ignored when default client is used"
                )
            self._owns_client = True
        else:
            if not isinstance(client, client_cls):
                raise TypeError(
                    f'Client must be an instance of {client_cls.__name__}, '
                    f'got {type(client).__name__} instead.'
                )
            if client.is_closed:
                raise RuntimeError(
                    f'{client_cls.__name__} client instance is already closed.'
                )
            self._client = client
            self._owns_client = owns_client

        self._parser = parser
        self._update_context: Dict[Any, Any] = {}
        self._update_hooks: List[Callable[[PageUpdateContext[TPage]], Any]] = []

    def __str__(self) -> str:
        return self._url

    def _get_page_update_context(
        self, parse_result: ParseResult[TPage]
    ) -> PageUpdateContext[TPage]:
        if parse_result.page_new is None or parse_result.page_old is None:
            raise ValueError('Page update context requires both old and new page data')
        page_diff = parse_result.page_new.item_diff(parse_result.page_old)
        if not page_diff:
            logger.debug("No changes detected in page '%s'", self._url)
        return PageUpdateContext(
            page_new=parse_result.page_new,
            page_old=parse_result.page_old,
            page_diff=page_diff,
            context=self._update_context.copy(),
        )

    @property
    def url(self) -> str:
        """Current page URL."""
        return self._url

    @property
    def page(self) -> TPage:
        """Current parsed page data."""
        return self._parser.page

    @property
    def update_context(self) -> Dict[Any, Any]:
        """Update context passed to event handlers."""
        return self._update_context

    def on_update(self, hook: Callable[[PageUpdateContext[TPage]], Any]) -> None:
        """Register an update hook to be called on page updates."""
        self._update_hooks.append(hook)

    def clear_update_hooks(self) -> None:
        """Clear all registered update hooks."""
        self._update_hooks.clear()
