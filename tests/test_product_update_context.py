import pytest

from dataclasses import FrozenInstanceError

from freshpointsync.update import ProductUpdateContext


@pytest.fixture
def context_data():
    return {
        'location_id': 123,
        'location_name': 'Test Location',
        'product_new': {'name': 'New Product'},
        'product_old': {'name': 'Old Product'},
        'foo': 'bar'
        }


def test_access_kwargs(context_data):
    context = ProductUpdateContext(context_data)
    with pytest.raises(AttributeError):
        context.__kwargs


def test_getattr(context_data):
    context = ProductUpdateContext(context_data)
    assert context.location_id == 123
    assert context.location_name == 'Test Location'
    assert context.product_new == {'name': 'New Product'}
    assert context.product_old == {'name': 'Old Product'}
    with pytest.raises(AttributeError):
        context.foo


def test_getitem(context_data):
    context = ProductUpdateContext(context_data)
    assert context['location_id'] == 123
    assert context['location_name'] == 'Test Location'
    assert context['product_new'] == {'name': 'New Product'}
    assert context['product_old'] == {'name': 'Old Product'}
    assert context['foo'] == 'bar'


def test_iter(context_data):
    context = ProductUpdateContext(context_data)
    assert set(context) == {
        'location_id', 'location_name', 'product_new', 'product_old', 'foo'
        }


def test_len(context_data):
    context = ProductUpdateContext(context_data)
    assert len(context) == 5


def test_is_immutable(context_data):
    context = ProductUpdateContext(context_data)
    with pytest.raises(TypeError):
        context['location_id'] = 42
    with pytest.raises(FrozenInstanceError):
        context.location_id = 42
