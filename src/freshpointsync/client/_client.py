import logging
import sys
from typing import Any, Optional, Type

import httpx
from tenacity import (
    AsyncRetrying,
    retry_if_exception_type,
    stop_after_attempt,
    wait_exponential,
)

if sys.version_info >= (3, 11):
    from typing import Self
else:
    from typing_extensions import Self


logger = logging.getLogger('freshpointsync.client')


class PageHTMLClient:
    """Lightweight async client for fetching HTML pages."""

    def __init__(self, *, retries: int = 3, **kwargs: Any) -> None:
        self._retries = retries
        self._client_kwargs = kwargs
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self) -> Self:
        self.start_session()
        return self

    async def __aexit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[object],
    ) -> None:
        await self.close_session()

    async def fetch(
        self, url: str, *, retries: Optional[int] = None, **kwargs: Any
    ) -> str:
        """Fetch page contents with retry logic.

        Args:
            url: Target URL to fetch.
        """
        if not self._client or self._client.is_closed:
            raise RuntimeError('HTTPX client is not initialized or already closed.')
        retries = retries if retries is not None else self._retries

        # Tenacity retry logic
        retry_strategy = AsyncRetrying(
            retry=retry_if_exception_type((
                httpx.HTTPStatusError,
                httpx.RequestError,
                httpx.TimeoutException,
            )),
            stop=stop_after_attempt(retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            reraise=True,
        )
        async for attempt in retry_strategy:
            with attempt:
                logger.info(
                    f"Fetching HTML content from '{url}', "
                    f'attempt {attempt.retry_state.attempt_number}'
                )
                response = await self._client.get(url, **kwargs)
                response.raise_for_status()
                return response.text

        # should not reach here due to reraise=True
        raise RuntimeError(
            f"Failed to fetch HTML content from '{url}' after {retries} attempts."
        )

    def start_session(self) -> None:
        """Start the HTTPX client session."""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(**self._client_kwargs)

    async def close_session(self) -> None:
        """Close the HTTPX client session."""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None


# Backwards compatibility -----------------------------------------------------

ProductDataFetchClient = PageHTMLClient

__all__ = [
    'PageHTMLClient',
    'ProductDataFetchClient',
    'logger',
]
