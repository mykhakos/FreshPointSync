import asyncio

import httpx
import pytest

from freshpointsync._html_client import PageHTMLClient


class DummyResponse(httpx.Response):
    def __init__(
        self, text: str = 'ok', status_code: int = 200, url: str = 'http://example.com'
    ) -> None:
        request = httpx.Request('GET', url)
        super().__init__(status_code=status_code, content=text, request=request)


def create_mock_get(responses):
    async def _mock_get(self, url, **kwargs):
        await asyncio.sleep(0)  # simulate async behavior
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result

    return _mock_get


@pytest.mark.asyncio
async def test_start_and_close_session():
    client = PageHTMLClient()
    assert client._client is None
    client.start_session()
    assert isinstance(client._client, httpx.AsyncClient)
    await client.close_session()
    assert client._client is None


@pytest.mark.asyncio
async def test_context_manager(monkeypatch):
    async def dummy_get(self, url, **kwargs):
        await asyncio.sleep(0)  # simulate async behavior
        return DummyResponse(url=url)

    monkeypatch.setattr(httpx.AsyncClient, 'get', dummy_get)
    async with PageHTMLClient() as client:
        assert isinstance(client._client, httpx.AsyncClient)
        text = await client.fetch('http://example.com')
        assert text == 'ok'
    assert client._client is None


@pytest.mark.asyncio
async def test_fetch(monkeypatch):
    async def dummy_get(self, url, **kwargs):
        await asyncio.sleep(0)  # simulate async behavior
        assert url == 'http://example.com/page'
        return DummyResponse('data', url=url)

    monkeypatch.setattr(httpx.AsyncClient, 'get', dummy_get)
    async with PageHTMLClient() as client:
        text = await client.fetch('http://example.com/page')
        assert text == 'data'


@pytest.mark.asyncio
async def test_retry(monkeypatch):
    err = httpx.RequestError('boom', request=httpx.Request('GET', 'http://x'))
    responses = [err, DummyResponse('ok', url='http://example.com')]
    monkeypatch.setattr(httpx.AsyncClient, 'get', create_mock_get(responses))
    async with PageHTMLClient(retries=2) as client:
        text = await client.fetch('http://example.com')
        assert text == 'ok'


@pytest.mark.asyncio
async def test_retry_exceeded(monkeypatch):
    err = httpx.RequestError('boom', request=httpx.Request('GET', 'http://x'))
    responses = [err, err, err]
    monkeypatch.setattr(httpx.AsyncClient, 'get', create_mock_get(responses))
    async with PageHTMLClient(retries=3) as client:
        with pytest.raises(httpx.RequestError):
            await client.fetch('http://example.com')


@pytest.mark.asyncio
async def test_fetch_with_kwargs(monkeypatch):
    async def dummy_get(self, url, **kwargs):
        await asyncio.sleep(0)  # simulate async behavior
        assert url == 'http://example.com/page'
        assert kwargs == {'headers': {'User-Agent': 'test-agent'}}
        return DummyResponse('data', url=url)

    monkeypatch.setattr(httpx.AsyncClient, 'get', dummy_get)
    async with PageHTMLClient() as client:
        text = await client.fetch(
            'http://example.com/page', headers={'User-Agent': 'test-agent'}
        )
        assert text == 'data'
