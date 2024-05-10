import pytest

from freshpointsync.product import Product
from freshpointsync.parser import ProductFinder


@pytest.fixture()
def products():
    yield [
        Product(
            id_=1,
            name="orange",
            category="fruit",
            quantity=1,
            price_full=2,
            price_curr=2,
        ),
        Product(
            id_=2,
            name="cheesecake",
            category="dessert",
            quantity=5,
            price_full=1.5,
            price_curr=2.2,
        ),
        Product(
            id_=3,
            name="apple",
            category="fruit",
            quantity=10,
            price_full=1.5,
            price_curr=1.2,
        ),
        Product(
            id_=4,
            name="banana",
            category="fruit",
            quantity=0,
            price_full=0.5,
            price_curr=0.4,
            is_vegetarian=True,
        ),
        Product(
            id_=5,
            name="carrot",
            category="vegetable",
            quantity=15,
            price_full=2.0,
            is_gluten_free=True,
        ),
        Product(
            id_=6,
            name="doughnut",
            category="pastry",
            quantity=5,
            price_full=1.0,
            price_curr=0.8,
        ),
        Product(
            id_=7,
            name="eggs",
            category="dairy",
            quantity=12,
            price_full=3.0,
            price_curr=2.5,
        ),
        Product(
            id_=8,
            name="fish",
            category="seafood",
            quantity=8,
            price_full=5.0,
            price_curr=4.5,
        ),
        Product(
            id_=9,
            name="grapes",
            category="fruit",
            quantity=20,
            price_full=2.0,
            price_curr=1.8,
            is_vegetarian=True,
        ),
        Product(
            id_=10,
            name="honey",
            category="sweetener",
            quantity=0,
            price_full=4.0,
            price_curr=3.5,
        ),
        Product(
            id_=11,
            name="ice cream",
            category="dessert",
            quantity=10,
            price_full=2.5,
            price_curr=2.0,
        ),
        Product(
            id_=12,
            name="jam",
            category="spread",
            quantity=7,
            price_full=3.0,
            price_curr=2.5,
            is_gluten_free=True,
        ),
    ]


@pytest.mark.usefixtures("products")
class TestProductFinder:

    def test_product_matches(self, products):
        matches = ProductFinder.product_matches(products[0], name='orange')
        assert matches
        not_matches = ProductFinder.product_matches(products[0], name='apple')
        assert not not_matches

    def test_find_product_by_name(self, products):
        product = ProductFinder.find_product(products, name='apple')
        assert product and product.id_ == 3

    def test_find_product_by_category(self, products):
        product = ProductFinder.find_product(products, category='seafood')
        assert product and product.id_ == 8

    def test_find_vegetarian_product(self, products):
        product = ProductFinder.find_product(products, is_vegetarian=True)
        assert product and product.id_ == 4

    def test_find_gluten_free_product(self, products):
        product = ProductFinder.find_product(products, is_gluten_free=True)
        assert product and product.id_ == 5

    def test_find_product_by_count(self, products):
        product = ProductFinder.find_product(products, quantity=15)
        assert product and product.id_ == 5

    def test_find_non_existing_product(self, products):
        product = ProductFinder.find_product(products, name='zucchini')
        assert product is None

    def test_find_products_by_full_price(self, products):
        products = ProductFinder.find_products(products, price_full=3.0)
        assert all(product.id_ in [7, 12] for product in products)

    def test_find_product_price_range(self, products):
        products = ProductFinder.find_products(
            products,
            constraint=lambda p: p.price_curr < 2.0
        )
        assert all(product.id_ in [3, 4, 6, 9] for product in products)

    def test_find_out_of_stock_products(self, products):
        products = ProductFinder.find_products(products, quantity=0)
        print(products)
        assert all(product.id_ in [1, 4, 10] for product in products)

    def test_find_products_in_category_with_constraint(self, products):
        products = ProductFinder.find_products(
            products,
            category='fruit',
            constraint=lambda p: p.is_available
        )
        assert all(product.id_ in [1, 3, 9] for product in products)
