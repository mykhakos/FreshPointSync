import httpx
import pytest
import sys
import types

# freshpointsync package expects a parser module which is no longer present.
dummy_parser = types.ModuleType('freshpointsync.parser._parser')
dummy_parser.ProductFinder = object
dummy_parser.hash_text = lambda *a, **k: ''
dummy_parser.normalize_text = lambda x: x
dummy_parser.parse_page_contents = lambda *a, **k: []
sys.modules.setdefault('freshpointsync.parser', types.ModuleType('parser'))
sys.modules.setdefault('freshpointsync.parser._parser', dummy_parser)
dummy_product = types.ModuleType('freshpointsync.product._product')
dummy_product.Product = object
sys.modules.setdefault('freshpointsync.product', types.ModuleType('product'))
sys.modules.setdefault('freshpointsync.product._product', dummy_product)

from freshpointsync.client._client import ProductDataFetchClient


class DummyResponse(httpx.Response):
    def __init__(self, text: str = "ok", status_code: int = 200, url: str = "http://example.com"):
        request = httpx.Request("GET", url)
        super().__init__(status_code=status_code, content=text, request=request)


def create_mock_get(responses):
    async def _mock_get(self, url, **kwargs):
        result = responses.pop(0)
        if isinstance(result, Exception):
            raise result
        return result
    return _mock_get


@pytest.mark.asyncio
async def test_start_and_close_session():
    client = ProductDataFetchClient()
    assert client._client is None
    client.start_session()
    assert isinstance(client._client, httpx.AsyncClient)
    await client.close_session()
    assert client._client is None


@pytest.mark.asyncio
async def test_context_manager(monkeypatch):
    async def dummy_get(self, url, **kwargs):
        return DummyResponse(url=url)
    monkeypatch.setattr(httpx.AsyncClient, "get", dummy_get)
    async with ProductDataFetchClient() as client:
        assert isinstance(client._client, httpx.AsyncClient)
        text = await client.fetch("http://example.com")
        assert text == "ok"
    assert client._client is None


@pytest.mark.asyncio
async def test_fetch(monkeypatch):
    async def dummy_get(self, url, **kwargs):
        assert url == "http://example.com/page"
        return DummyResponse("data", url=url)
    monkeypatch.setattr(httpx.AsyncClient, "get", dummy_get)
    async with ProductDataFetchClient() as client:
        text = await client.fetch("http://example.com/page")
        assert text == "data"


@pytest.mark.asyncio
async def test_retry(monkeypatch):
    err = httpx.RequestError("boom", request=httpx.Request("GET", "http://x"))
    responses = [err, DummyResponse("ok", url="http://example.com")]
    monkeypatch.setattr(httpx.AsyncClient, "get", create_mock_get(responses))
    async with ProductDataFetchClient(retries=2) as client:
        text = await client.fetch("http://example.com")
        assert text == "ok"

