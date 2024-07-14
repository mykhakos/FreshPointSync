import pytest
from freshpointsync.client import ProductDataFetchClient
from freshpointsync.page import (
    ProductPage,
    ProductPageData,
    ProductPageHub,
    ProductPageHubData,
)
from freshpointsync.product import Product


class TestProductPageData:
    @pytest.fixture(name='product_page_data')
    def fixture_product_page_data(self):
        return ProductPageData(
            location_id=1,
            html_hash='',
            products={},
        )

    def test_url(self, product_page_data):
        expected_url = ProductDataFetchClient.get_page_url(location_id=1)
        assert product_page_data.url == expected_url

    def test_location_id_immutable(self, product_page_data):
        with pytest.raises(ValueError):
            product_page_data.location_id = 2

    def test_location(self, product_page_data):
        assert not product_page_data.location
        product = Product(id_=1, location="L'Oréal Česká republika")
        product_page_data.products[1] = product
        expected_location = "L'Oréal Česká republika"
        actual_location = product_page_data.location
        assert actual_location == expected_location

    def test_location_lowercase_ascii(self, product_page_data):
        product = Product(id_=1, location="L'Oréal Česká republika")
        product_page_data.products[1] = product
        expected_location = "l'oreal ceska republika"
        actual_location = product_page_data.location_lowercase_ascii
        assert actual_location == expected_location


class TestProductPage:
    def test_page_created(self):
        page = ProductPage(location_id=296)
        assert page.data == ProductPageData(location_id=296)

    @pytest.mark.asyncio
    async def test_fetch(self):
        async with ProductPage(location_id=296) as page:
            page_hash = page.data.html_hash
            products = await page.fetch()
            assert products and isinstance(products, list)
            assert page.data.html_hash == page_hash

    @pytest.mark.asyncio
    async def test_update(self):
        async with ProductPage(location_id=296) as page:
            await page.update()


class TestProductPageHub:
    def test_hub_created(self):
        hub = ProductPageHub()
        assert hub.data == ProductPageHubData()

    @pytest.mark.asyncio
    async def test_hub(self):
        async with ProductPageHub() as hub:
            assert not hub.pages
            # update with empty pages dict
            await hub.update()
            assert not hub.pages
            # scan pages from 10 to 30
            await hub.scan(start=10, stop=20)
            assert hub.pages and all(
                page_location_id >= 10 and page_location_id <= 20
                for page_location_id in hub.pages
            )
            # add new page with location_id 296
            page = await hub.new_page(location_id=296)
            assert isinstance(page, ProductPage)
            assert page.data.location_id == 296
            assert page.data.location_id in hub.pages
            assert page in hub.pages.values()
            assert page.client is hub.client
            assert page._runner is hub._runner
            # remove page with location_id 296
            await hub.remove_page(location_id=296)
            assert page.data.location_id not in hub.pages
            assert page not in hub.pages.values()
            assert id(page.client) != id(hub.client)
            assert id(page._runner) != id(hub._runner)
            # add page with location_id 296 again
            await hub.add_page(page)
            assert page.data.location_id in hub.pages
            assert page in hub.pages.values()
            assert page.client is hub.client
            assert page._runner is hub._runner
