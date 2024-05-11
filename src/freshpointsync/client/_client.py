import asyncio
import aiohttp
import logging

import os

from typing import Any, Optional, Union


logger = logging.getLogger("freshpointsync.client")
"""Logger for the `freshpointsync.client` module."""


class ProductDataFetchClient:
    """Asynchronous utility for fetching contents of a specified FreshPoint.cz
    web page.

    This class wraps an `aiohttp.ClientSession` object and provides additional
    features like retries, timeouts, logging, and comprehensive error handling.
    """
    BASE_URL = "https://my.freshpoint.cz"
    """The base URL of the FreshPoint.cz website."""

    def __init__(
        self,
        timeout: Optional[Union[aiohttp.ClientTimeout, int, float]] = None,
        max_retries: int = 5
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
        """Generate a page URL for a given location ID.

        Args:
            location_id (int): The ID of the location, as it appears in
                the FreshPoint.cz web page URL. For example, in
                https://my.freshpoint.cz/device/product-list/296,
                the ID is 296.

        Returns:
            str: The full page URL for the given location ID.
        """
        return f'{cls.BASE_URL}/device/product-list/{location_id}'

    @property
    def session(self) -> Optional[aiohttp.ClientSession]:
        """The `aiohttp` client session object used for fetching data."""
        return self._client_session

    @property
    def is_session_closed(self) -> bool:
        """Check if the client session is closed.

        Returns:
            bool: True if the client session is closed, False otherwise.
        """
        if not self._client_session:
            return True
        return self._client_session.closed

    async def set_session(self, session: aiohttp.ClientSession) -> None:
        """Set the client session object. If the previous session
        is not closed, it is closed before setting the new one.

        Args:
            session (aiohttp.ClientSession): The client session to set.
        """
        if not self.is_session_closed:
            await self.close_session()
        self._client_session = session

    @property
    def timeout(self) -> aiohttp.ClientTimeout:
        """Client request timeout."""
        return self._timeout

    @staticmethod
    def _check_client_timeout(timeout: Any) -> aiohttp.ClientTimeout:
        """Check and validate the client timeout value.

        Args:
            timeout (Any): The timeout value to be checked.

        Returns:
            aiohttp.ClientTimeout: The validated client timeout object.

        Raises:
            ValueError: If the timeout value is negative or invalid.
        """
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
        """Set the client request timeout.

        Args:
            timeout (Optional[Union[aiohttp.ClientTimeout, int, float]]):
                The timeout value. It can be an `aiohttp.ClientTimeout` object,
                an integer or a float representing the total timeout in
                seconds, or None for the default aiohttp client timeout.

        Raises:
            ValueError: If the timeout value is negative or invalid.
        """
        self._timeout = self._check_client_timeout(timeout)

    @property
    def max_retries(self) -> int:
        """The maximum number of retries for fetching data."""
        return self._max_retries

    @staticmethod
    def _check_max_retries(max_retries: Any) -> int:
        """Check if the given max_retries value is valid.

        Args:
            max_retries (Any): The number of max retries.

        Returns:
            int: The validated max_retries value.

        Raises:
            TypeError: If the max_retries value is not an integer.
            ValueError: If the max_retries value is less than 1.
        """
        if not isinstance(max_retries, int):
            raise TypeError("The number of max retries must be an integer.")
        if max_retries < 1:
            raise ValueError("The number of max retries must be positive.")
        return max_retries

    def set_max_retries(self, max_retries: int) -> None:
        """Set the maximum number of retries for the fetching data.

        Args:
            max_retries (int): The maximum number of retries.

        Raises:
            TypeError: If the max_retries value is not an integer.
            ValueError: If the max_retries value is less than 1.
        """
        self._max_retries = self._check_max_retries(max_retries)

    async def start_session(self) -> None:
        """Start an aiohttp client session if one is not already started."""
        if self.is_session_closed:
            logger.info('Starting new client session for "%s".', self.BASE_URL)
            session = aiohttp.ClientSession(base_url=self.BASE_URL)
            self._client_session = session
            logger.debug(
                'Successfully started client session for "%s".', self.BASE_URL
                )
        else:
            logger.debug(
                'Client session for "%s" is already started.', self.BASE_URL
                )

    async def close_session(self) -> None:
        """Close the aiohttp client session if one is open."""
        if self.is_session_closed:
            logger.debug(
                'Client session for "%s" is already closed.', self.BASE_URL
                )
        else:
            logger.info('Closing client session for "%s".', self.BASE_URL)
            await self._client_session.close()  # type: ignore
            logger.debug(
                'Successfully closed client session for "%s".', self.BASE_URL
                )

    def _check_fetch_args(
        self, location_id: Any, timeout: Any, max_retries: Any
    ) -> tuple[aiohttp.ClientSession, str, aiohttp.ClientTimeout, int]:
        """Check and validate the arguments for fetching data. Note that this
        method may raise exceptions via the checks for timeout and max_retries.

        Args:
            location_id (Any): The ID of the location.
            timeout (Any): The timeout value for the request.
            max_retries (Any): The maximum number of retries for the request.

        Returns:
            tuple[aiohttp.ClientSession, str, aiohttp.ClientTimeout, int]:
                A tuple containing the client session, relative URL, timeout,
                and max retries.
        """
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

    async def _fetch_once(
        self,
        session: aiohttp.ClientSession,
        relative_url: str,
        timeout: aiohttp.ClientTimeout
    ) -> Optional[str]:
        """Fetch data from the specified URL using the provided session and
        timeout.

        Args:
            session (aiohttp.ClientSession): The client session to use for
                the request.
            relative_url (str): The relative URL to fetch data from.
            timeout (aiohttp.ClientTimeout): The timeout for the request.

        Returns:
            Optional[str]: The fetched data as a string,
                or None if an error occurred.
        """
        try:
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
        """Fetch HTML data from a FreshPoint.cz web page.

        Args:
            location_id (Union[int, str]): The ID the FreshPoint location.
            timeout (Optional[Union[aiohttp.ClientTimeout, int, float]]):\
            The timeout for the request. If None, the default timeout is used.
            max_retries (Optional[int]): The maximum number of retries.
                If None, the default number of retries is used.

        Returns:
            Optional[str]: The fetched data as a string,\
                or None if the fetch failed.
        """
        args = self._check_fetch_args(location_id, timeout, max_retries)
        session, relative_url, timeout, max_retries = args
        attempt = 0
        while attempt < max_retries:
            logger.info(
                'Fetching data from "%s%s" (attempt %s of %s)',
                self.BASE_URL, relative_url, attempt + 1, max_retries
                )
            text = await self._fetch_once(session, relative_url, timeout)
            if text is not None:
                return text
            attempt += 1
            if attempt < max_retries:
                wait_time: int = 2 ** attempt  # exponential backoff
                logger.debug('Retrying in %i seconds...', wait_time)
                await asyncio.sleep(wait_time)
        return None
