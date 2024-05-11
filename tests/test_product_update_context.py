import pytest

from freshpointsync.product import Product
from freshpointsync.update import ProductUpdateContext


def get_product_new():
    return Product(id_=1, location_id=123, quantity=42, timestamp=1)


def get_product_old():
    return Product(id_=1, location_id=123, quantity=24, timestamp=0)


@pytest.fixture
def context_data():
    return {
        'product_new': get_product_new(),
        'product_old': get_product_old(),
        'foo': 'bar'
        }


def test_access_kwargs(context_data):
    context = ProductUpdateContext(context_data)
    with pytest.raises(AttributeError):
        context.__kwargs


def test_getattr(context_data):
    context = ProductUpdateContext(context_data)
    assert context.location_id == 123
    assert context.product_new == get_product_new()
    assert context.product_old == get_product_old()
    with pytest.raises(AttributeError):  # access a user-defined attribute
        context.foo  # type: ignore


def test_getitem(context_data):
    context = ProductUpdateContext(context_data)
    assert context['product_new'] == get_product_new()
    assert context['product_old'] == get_product_old()
    assert context['foo'] == 'bar'


def test_iter(context_data):
    context = ProductUpdateContext(context_data)
    assert set(context) == {'product_new', 'product_old', 'foo'}


def test_len(context_data):
    context = ProductUpdateContext(context_data)
    assert len(context) == 3


def test_is_immutable(context_data):
    context = ProductUpdateContext(context_data)
    with pytest.raises(TypeError):
        context['location_id'] = 42  # type: ignore
    with pytest.raises(AttributeError):
        context.location_id = 42  # type: ignore
