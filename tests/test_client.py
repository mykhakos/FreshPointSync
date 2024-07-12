import asyncio

import aiohttp
import pytest
from freshpointsync.client import ProductDataFetchClient


@pytest.fixture(name='client', scope='module')
def fixture_client():
    return ProductDataFetchClient()


def test_init_client():
    client = ProductDataFetchClient()
    assert client
    assert client.BASE_URL == 'https://my.freshpoint.cz'
    assert client.timeout == aiohttp.ClientTimeout()
    assert client.max_retries == 5
    assert client.session is None


def test_get_page_url():
    url = ProductDataFetchClient.get_page_url(296)
    assert url == 'https://my.freshpoint.cz/device/product-list/296'


def test_is_timeout_readonly(client):
    with pytest.raises(AttributeError):
        client.timeout = 5


@pytest.mark.parametrize('timeout', ['5', 'timeout', [5, 5, 5, 5]])
def test_set_timeout_invalid(client, timeout):
    with pytest.raises(ValueError):
        client.set_timeout(timeout)


@pytest.mark.parametrize(
    'timeout, expected_timeout',
    [
        (None, aiohttp.ClientTimeout()),
        (5, aiohttp.ClientTimeout(total=5)),
        (5.5, aiohttp.ClientTimeout(total=5.5)),
        (0, aiohttp.ClientTimeout(total=0)),
        (-1, aiohttp.ClientTimeout(total=-1)),
        (aiohttp.ClientTimeout(total=10), aiohttp.ClientTimeout(total=10)),
        (
            aiohttp.ClientTimeout(total=10, connect=5),
            aiohttp.ClientTimeout(total=10, connect=5),
        ),
    ],
)
def test_set_timeout(client, timeout, expected_timeout):
    client = ProductDataFetchClient()
    client.set_timeout(timeout)
    assert client.timeout == expected_timeout


def test_is_max_retries_readonly(client):
    with pytest.raises(AttributeError):
        client.max_retries = 5


@pytest.mark.parametrize('retries', ['5', 5.5, -1, None, []])
def test_set_max_retries_invalid(client, retries):
    with pytest.raises(ValueError):
        client.set_max_retries(retries)


@pytest.mark.parametrize(
    'retries, expected_retries', [(0, 0), (1, 1), (5, 5), (10, 10)]
)
def test_set_max_retries(client, retries, expected_retries):
    client.set_max_retries(retries)
    assert client.max_retries == expected_retries


@pytest.mark.asyncio
async def test_client_init_session():
    client = ProductDataFetchClient()
    try:
        await client.start_session()
        assert client.session
        assert isinstance(client.session, aiohttp.ClientSession)
    finally:
        await client.close_session()
        assert client.session is None


@pytest.mark.asyncio
async def test_client_init_context_manager():
    async with ProductDataFetchClient() as client:
        assert client.session
        assert isinstance(client.session, aiohttp.ClientSession)
    assert client.session is None


@pytest.mark.asyncio
async def test_client_fetch():
    async with ProductDataFetchClient() as client:
        response = await client.fetch(location_id=296)
        assert response


@pytest.mark.asyncio
async def test_client_fetch_multiple_simultaneously():
    async with ProductDataFetchClient() as client:
        tasks = [
            asyncio.create_task(client.fetch(location_id=location_id))
            for location_id in range(1, 20)
        ]
        await asyncio.gather(*tasks)
