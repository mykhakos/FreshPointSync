import time
import pytest

from freshpointsync.product import (
    Product, ProductPriceUpdateInfo, ProductStockUpdateInfo
)
from freshpointsync.product._product import collect_props


def test_collect_props() -> None:

    class Foo:
        class_var: int = 1

        def __init__(self) -> None:
            self.inst_var: int = 2
            self._hidden_inst_var: int = 3

        @property
        def class_var_plus_one(self) -> float:
            return self.class_var + 1

        @property
        def inst_var_plus_one(self) -> float:
            return self.inst_var + 1

        @property
        def _hidden_prop(self) -> bool:
            return True

    props = ('class_var_plus_one', 'inst_var_plus_one')
    assert collect_props(Foo) == props
    assert collect_props(type(Foo())) == props


@pytest.mark.parametrize(
    "created, reference",
    [
        (
            Product(123, name='foo'),
            Product(123, name='foo'),
        ),
        (
            Product(123),
            Product(123, name=''),
        ),
    ]
)
def test_create_eval_name(created: Product, reference: Product):
    assert created.name == reference.name


@pytest.mark.parametrize(
    "created, reference",
    [
        (
            Product(123, price_full=10, price_curr=10),
            Product(123, price_full=10, price_curr=10),
        ),
        (
            Product(123, price_curr=10),
            Product(123, price_full=10, price_curr=10),
        ),
        (
            Product(123, price_full=10),
            Product(123, price_full=10, price_curr=10),
        ),
        (
            Product(123),
            Product(123, price_full=0, price_curr=0),
        ),
    ]
)
def test_create_eval_prices(created: Product, reference: Product):
    assert created.price_full == reference.price_full
    assert created.price_curr == reference.price_curr


@pytest.mark.parametrize(
    "prod, rate",
    [
        (Product(123, price_full=0, price_curr=0), 0),
        (Product(123, price_full=0, price_curr=10), 0),  # should not happen
        (Product(123, price_full=5, price_curr=10), 0),  # should not happen
        (Product(123, price_full=10, price_curr=0), 1),
        (Product(123, price_full=10, price_curr=5), 0.5),
        (Product(123, price_full=10, price_curr=2/3*10), 0.33),
        (Product(123, price_full=10, price_curr=10), 0),
    ]
)
def test_discount_rate(prod: Product, rate: float):
    assert prod.discount_rate == rate


def test_is_immutable():
    with pytest.raises(AttributeError):
        Product('foo', 123).product_id = 321


def test_is_newer():
    prod_1 = Product(123)
    time.sleep(0.001)
    prod_2 = Product(123)
    assert prod_2.is_newer(prod_1)


def test_as_dict():
    prod = Product(
        product_id=123,
        name='foo',
        category='bar',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=5,
        price_full=10,
        price_curr=5,
        pic_url='url',
        location_id=321,
        location_name='loc'
        )
    assert prod.as_dict() == {
        'product_id': 123,
        'name': 'foo',
        'category': 'bar',
        'is_vegetarian': True,
        'is_gluten_free': False,
        'quantity': 5,
        'price_full': 10,
        'price_curr': 5,
        'pic_url': 'url',
        'location_id': 321,
        'location_name': 'loc'
    }
    assert prod.as_dict(include_timestamp=True) == {
        'product_id': 123,
        'name': 'foo',
        'category': 'bar',
        'is_vegetarian': True,
        'is_gluten_free': False,
        'quantity': 5,
        'price_full': 10,
        'price_curr': 5,
        'pic_url': 'url',
        'location_id': 321,
        'location_name': 'loc',
        'timestamp': prod.timestamp
    }
    assert prod.as_dict(include_properties=True) == {
        'product_id': 123,
        'name': 'foo',
        'category': 'bar',
        'is_vegetarian': True,
        'is_gluten_free': False,
        'quantity': 5,
        'price_full': 10,
        'price_curr': 5,
        'pic_url': 'url',
        'location_id': 321,
        'location_name': 'loc',
        'discount_rate': 0.5,
        'is_on_sale': True,
        'is_available': True,
        'is_sold_out': False,
        'is_last_piece': False,
        'name_ascii': 'foo',
        'category_ascii': 'bar'
    }


@pytest.mark.parametrize(
    "prod_1, prod_2, diff, diff_props",
    [
        (
            Product(123, quantity=4, price_full=10),
            Product(123, quantity=4, price_full=10),
            {},
            {}
        ),
        (
            Product(123, quantity=4, price_full=10, price_curr=10),
            Product(123, quantity=4, price_full=10, price_curr=5),
            {'price_curr': (10, 5)},
            {
                'price_curr': (10, 5),
                'is_on_sale': (False, True),
                'discount_rate': (0, 0.5)
            }
        ),
        (
            Product(123, quantity=4, price_full=10, price_curr=5),
            Product(123, quantity=4, price_full=10, price_curr=10),
            {'price_curr': (5, 10)},
            {
                'price_curr': (5, 10),
                'is_on_sale': (True, False),
                'discount_rate': (0.5, 0)
            }
        ),
        (
            Product(123, quantity=5, price_full=10, price_curr=10),
            Product(123, quantity=0, price_full=10, price_curr=10),
            {'quantity': (5, 0)},
            {
                'quantity': (5, 0),
                'is_sold_out': (False, True),
                'is_available': (True, False)
            },
        ),
        (
            Product(123, name='foo', quantity=0, price_full=5),
            Product(321, name='bar', quantity=5, price_full=10),
            {
                'product_id': (123, 321),
                'name': ('foo', 'bar'),
                'quantity': (0, 5),
                'price_full': (5, 10),
                'price_curr': (5, 10)
            },
            {
                'product_id': (123, 321),
                'name': ('foo', 'bar'),
                'name_ascii': ('foo', 'bar'),
                'quantity': (0, 5),
                'price_full': (5, 10),
                'price_curr': (5, 10),
                'is_sold_out': (True, False),
                'is_available': (False, True),
            },
        ),
    ]
)
def test_diff(prod_1: Product, prod_2: Product, diff: dict, diff_props: dict):
    assert prod_1.diff(prod_2, include_properties=False) == diff
    assert prod_1.diff(prod_2, include_properties=True) == diff_props


@pytest.mark.parametrize(
    "prod_1, prod_2, info",
    [
        (
            Product(123),
            Product(123),
            ProductStockUpdateInfo(
                stock_decrease=0,
                stock_increase=0,
                stock_depleted=False,
                stock_restocked=False
            )
        ),
        (
            Product(123, quantity=4, price_full=10),
            Product(123, quantity=4, price_full=10),
            ProductStockUpdateInfo(
                stock_decrease=0,
                stock_increase=0,
                stock_depleted=False,
                stock_restocked=False
            )
        ),
        (
            Product(123, quantity=4, price_full=10, price_curr=10),
            Product(123, quantity=4, price_full=10, price_curr=5),
            ProductStockUpdateInfo(
                stock_decrease=0,
                stock_increase=0,
                stock_depleted=False,
                stock_restocked=False
            )
        ),
        (
            Product(123, quantity=0, price_full=10, price_curr=10),
            Product(123, quantity=0, price_full=10, price_curr=10),
            ProductStockUpdateInfo(
                stock_decrease=0,
                stock_increase=0,
                stock_depleted=False,
                stock_restocked=False
            )
        ),
        (
            Product(123, quantity=5),
            Product(123, quantity=2),
            ProductStockUpdateInfo(
                stock_decrease=3,
                stock_increase=0,
                stock_depleted=False,
                stock_restocked=False
            )
        ),
        (
            Product(123, quantity=2),
            Product(123, quantity=0),
            ProductStockUpdateInfo(
                stock_decrease=2,
                stock_increase=0,
                stock_depleted=True,
                stock_restocked=False
            )
        ),
        (
            Product(123, quantity=0),
            Product(123, quantity=2),
            ProductStockUpdateInfo(
                stock_decrease=0,
                stock_increase=2,
                stock_depleted=False,
                stock_restocked=True
            )
        ),
        (
            Product(123, quantity=2),
            Product(123, quantity=5),
            ProductStockUpdateInfo(
                stock_decrease=0,
                stock_increase=3,
                stock_depleted=False,
                stock_restocked=False
            )
        ),
    ]
)
def test_compare_stock(prod_1: Product, prod_2: Product, info):
    assert prod_1.compare_stock(prod_2) == info


@pytest.mark.parametrize(
    "prod_1, prod_2, info",
    [
        (
            Product(123),
            Product(123),
            ProductPriceUpdateInfo(
                price_full_decrease=0,
                price_full_increase=0,
                price_curr_decrease=0,
                price_curr_increase=0,
                discount_rate_decrease=0,
                discount_rate_increase=0,
                sale_started=False,
                sale_ended=False
            )
        ),
        (
            Product(123, quantity=4, price_full=10, price_curr=10),
            Product(123, quantity=8, price_full=10, price_curr=10),
            ProductPriceUpdateInfo(
                price_full_decrease=0,
                price_full_increase=0,
                price_curr_decrease=0,
                price_curr_increase=0,
                discount_rate_decrease=0,
                discount_rate_increase=0,
                sale_started=False,
                sale_ended=False
            )
        ),
        (
            Product(123, price_full=10, price_curr=10),
            Product(123, price_full=10, price_curr=5),
            ProductPriceUpdateInfo(
                price_full_decrease=0,
                price_full_increase=0,
                price_curr_decrease=5,
                price_curr_increase=0,
                discount_rate_decrease=0,
                discount_rate_increase=0.5,
                sale_started=True,
                sale_ended=False
            )
        ),
        (
            Product(123, price_full=10, price_curr=5),
            Product(123, price_full=10, price_curr=10),
            ProductPriceUpdateInfo(
                price_full_decrease=0,
                price_full_increase=0,
                price_curr_decrease=0,
                price_curr_increase=5,
                discount_rate_decrease=0.5,
                discount_rate_increase=0,
                sale_started=False,
                sale_ended=True
            )
        ),
        (
            Product(123, price_full=10, price_curr=5),
            Product(123, price_full=20, price_curr=10),
            ProductPriceUpdateInfo(
                price_full_decrease=0,
                price_full_increase=10,
                price_curr_decrease=0,
                price_curr_increase=5,
                discount_rate_decrease=0,
                discount_rate_increase=0,
                sale_started=False,
                sale_ended=False
            )
        ),
        (
            Product(123, price_full=10, price_curr=5),
            Product(123, price_full=20, price_curr=15),
            ProductPriceUpdateInfo(
                price_full_decrease=0,
                price_full_increase=10,
                price_curr_decrease=0,
                price_curr_increase=10,
                discount_rate_decrease=0.25,
                discount_rate_increase=0,
                sale_started=False,
                sale_ended=False
            )
        ),
    ]
)
def test_compare_price(prod_1: Product, prod_2: Product, info):
    assert prod_1.compare_price(prod_2) == info
