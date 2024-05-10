import pytest

from freshpointsync.page import ProductPageData
from freshpointsync.product import Product
from freshpointsync.client import ProductDataFetchClient


class TestProductPageData:
    @pytest.fixture
    def product_page_data(self):
        return ProductPageData(
            location_id=1,
            products={},
            html="<html></html>"
            )

    def test_url(self, product_page_data):
        expected_url = ProductDataFetchClient.get_page_url(1)
        assert product_page_data.url == expected_url

    def test_location_id_immutable(self, product_page_data):
        with pytest.raises(ValueError):
            product_page_data.location_id = 2

    def test_location_name(self, product_page_data):
        assert product_page_data.location_name == ""
        product = Product(id_=1, location_name="L'Oréal Česká republika")
        product_page_data.products[1] = product
        expected_location_name = "L'Oréal Česká republika"
        actual_location_name = product_page_data.location_name
        assert actual_location_name == expected_location_name

    def test_location_name_lowercase_ascii(self, product_page_data):
        product = Product(id_=1, location_name="L'Oréal Česká republika")
        product_page_data.products[1] = product
        expected_location_name = "l'oreal ceska republika"
        actual_location_name = product_page_data.location_name_lowercase_ascii
        assert actual_location_name == expected_location_name
