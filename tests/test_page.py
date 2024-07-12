import pytest
from freshpointsync.client import ProductDataFetchClient
from freshpointsync.page import ProductPageData
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
        expected_url = ProductDataFetchClient.get_page_url(1)
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
