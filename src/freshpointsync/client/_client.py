import asyncio
import aiohttp
import logging
import random

from typing import Any, Optional, Union


# delete this later #


def get_local_html() -> str:
    path = r"C:\Users\kmykhailov\Desktop\work\WebParserTest\page.html"
    with open(path, 'r', encoding='utf-8') as file:
        return file.read()

####


logger = logging.getLogger("freshpoint_sync.client")


class ProductDataFetchClient:
    """
    Asynchronous utility for fetching content from a specified FreshPoint
    web page address under various network conditions and server responses.
    This class wraps an `aiohttp.ClientSession` object and provided additional
    features like retries, timeouts, logging, and comprehensive error handling.
    """
    BASE_URL = "https://my.freshpoint.cz"

    def __init__(
        self,
        timeout: Optional[Union[aiohttp.ClientTimeout, int, float]] = None,
        max_retries: int = 3
    ) -> None:
        self._timeout = self._check_client_timeout(timeout)
        self._max_retries = self._check_max_retries(max_retries)
        self._client_session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """Asynchronous context manager entry."""
        await self.start_session()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        """Asynchronous context manager exit."""
        await self.close_session()

    @classmethod
    def get_page_url(cls, location_id: int) -> str:
        return f'{cls.BASE_URL}/device/product-list/{location_id}'

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        return self._client_session

    @property
    def is_session_closed(self) -> bool:
        if not self._client_session:
            return True
        return self._client_session.closed

    async def set_session(self, session: aiohttp.ClientSession) -> None:
        if not self.is_session_closed:
            await self.close_session()
        self._client_session = session

    @property
    def timeout(self) -> aiohttp.ClientTimeout:
        return self._timeout

    @staticmethod
    def _check_client_timeout(timeout: Any) -> aiohttp.ClientTimeout:
        if timeout is None:
            return aiohttp.ClientTimeout()
        if isinstance(timeout, aiohttp.ClientTimeout):
            return timeout
        try:
            timeout = float(timeout)
            if timeout < 0:
                raise ValueError("Timeout cannot be negative.")
            return aiohttp.ClientTimeout(total=timeout)
        except ValueError as err:
            raise ValueError(f'Invalid timeout argument "{timeout}".') from err

    def set_timeout(
        self, timeout: Optional[Union[aiohttp.ClientTimeout, int, float]]
    ) -> None:
        self._timeout = self._check_client_timeout(timeout)

    @property
    def max_retries(self) -> int:
        return self._max_retries

    @staticmethod
    def _check_max_retries(max_retries: Any) -> int:
        if not isinstance(max_retries, int):
            raise TypeError("The number of max retries must be an integer.")
        if max_retries < 1:
            raise ValueError("The number of max retries must be positive.")
        return max_retries

    def set_max_retries(self, max_retries: int) -> None:
        self._max_retries = self._check_max_retries(max_retries)

    async def start_session(self) -> None:
        """Start an aiohttp client session if not already started."""
        if not self.is_session_closed:
            logger.debug(
                'Client session for "%s" is already started.', self.BASE_URL
                )
            return
        logger.info('Starting new client session for "%s".', self.BASE_URL)
        self._client_session = aiohttp.ClientSession(base_url=self.BASE_URL)
        logger.debug(
            'Successfully opened client session for "%s".', self.BASE_URL
            )

    async def close_session(self) -> None:
        """Close the aiohttp client session if it's open."""
        if self.is_session_closed:
            logger.debug(
                'Client session for "%s" is already closed.', self.BASE_URL
                )
            return
        logger.info('Closing client session for "%s".', self.BASE_URL)
        await self._client_session.close()  # type: ignore
        logger.debug(
            'Successfully closed client session for "%s".', self.BASE_URL
            )

    def _check_fetch_args(
        self, location_id: Any, timeout: Any, max_retries: Any
    ) -> tuple[aiohttp.ClientSession, str, aiohttp.ClientTimeout, int]:
        if not self._client_session or self._client_session.closed:
            raise ValueError('Client session is not initialized or is closed.')
        else:
            session = self._client_session
        if timeout is None:
            timeout = self._timeout
        else:
            timeout = self._check_client_timeout(timeout)
        if max_retries is None:
            max_retries = self._max_retries
        else:
            max_retries = self._check_max_retries(max_retries)
        relative_url = f'/device/product-list/{location_id}'
        return session, relative_url, timeout, max_retries

    @staticmethod
    def _get_fetch_delay(timeout: aiohttp.ClientTimeout) -> float:
        min_delay = 0.1
        max_delay = min_delay * 3
        delay = max_delay
        for t in (
            timeout.total,
            timeout.connect,
            timeout.sock_connect,
            timeout.sock_read
        ):
            if t and (t < delay) and (min_delay < t < max_delay):
                delay = t
        return random.uniform(delay - min_delay, delay + min_delay)

    async def _fetch_once(
        self,
        session: aiohttp.ClientSession,
        relative_url: str,
        timeout: aiohttp.ClientTimeout
    ) -> Optional[str]:
        try:
            logger.info(
                'Fetching data from "%s%s"', self.BASE_URL, relative_url
                )
            await asyncio.sleep(self._get_fetch_delay(timeout))
            async with session.get(relative_url, timeout=timeout) as response:
                if response.status == 200:
                    logger.debug(
                        'Successfully fetched data from "%s"', response.url
                        )
                    return await response.text()
                else:
                    logger.error(
                        'Error occurred while fetching data from "%s": '
                        'HTTP Status %s', response.url, response.status
                        )
        except asyncio.TimeoutError:
            logger.warning(
                'Timeout occurred when fetching data from "%s%s"',
                self.BASE_URL, relative_url
                )
        except Exception as exc:
            logger.error(
                'Exception occurred while fetching data from "%s%s": %s',
                self.BASE_URL, relative_url, str(exc)
                )
        return None

    async def fetch(
        self,
        location_id: Union[int, str],
        timeout: Optional[Union[aiohttp.ClientTimeout, int, float]] = None,
        max_retries: Optional[int] = None
    ) -> Optional[str]:
        """Fetch data from the URL using the aiohttp session."""
        args = self._check_fetch_args(location_id, timeout, max_retries)
        session, relative_url, timeout, max_retries = args
        attempt = 0
        while attempt < max_retries:
            text = await self._fetch_once(session, relative_url, timeout)
            if text is not None:
                return text
            attempt += 1
            if attempt < max_retries:
                wait_time: int = 2 ** attempt  # exponential backoff
                logger.info('Retrying in %i seconds...', wait_time)
                await asyncio.sleep(wait_time)
        return None
