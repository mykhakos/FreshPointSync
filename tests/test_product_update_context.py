import pytest
from freshpointsync.product import Product
from freshpointsync.update import ProductUpdateContext, ProductUpdateEvent


def get_product_old():
    return Product(
        id_=1,
        name='Harboe Cola',
        category='Soda',
        is_vegetarian=True,
        is_gluten_free=True,
        quantity=10,
        price_full=25.9,
        price_curr=19.9,
        info='1.5L',
        location_id=296,
        location='Silent Hill',
        timestamp=1609459200,
    )


def get_product_new():
    product = get_product_old()
    product.quantity = 5  # decrease the quantity
    product.price_curr = 25.9  # increase to the full price
    product.timestamp += 10  # simulate a time delay
    return product


@pytest.fixture(name='context_kwargs', scope='module')
def fixture_context_kwargs():
    return {
        'product_new': get_product_new(),
        'product_old': get_product_old(),
        'event': ProductUpdateEvent.PRODUCT_UPDATED,
        'foo': 'bar',
        42: '42',
    }


@pytest.fixture(name='context', scope='module')
def fixture_context(context_kwargs):
    yield ProductUpdateContext(context_kwargs)


def test_str(context: ProductUpdateContext, context_kwargs: dict):
    assert str(context) == str(context_kwargs)


def test_iter(context: ProductUpdateContext):
    assert set(context) == {'product_new', 'product_old', 'event', 'foo', 42}


def test_len(context: ProductUpdateContext):
    assert len(context) == 5


def test_access_kwargs(context: ProductUpdateContext):
    with pytest.raises(AttributeError):
        context.__kwargs  # noqa: B018


def test_is_immutable(context: ProductUpdateContext):
    with pytest.raises(TypeError):
        context['location_id'] = 42  # type: ignore
    with pytest.raises(AttributeError):
        context.location_id = 42  # type: ignore


def test_getitem(context: ProductUpdateContext):
    assert context['product_new'] == get_product_new()
    assert context['product_old'] == get_product_old()
    assert context['event'] == ProductUpdateEvent.PRODUCT_UPDATED
    assert context['foo'] == 'bar'
    assert context[42] == '42'


def test_getattr(context: ProductUpdateContext):
    assert context.product_id == 1
    assert context.product_name == 'Harboe Cola'
    assert context.product_name_lowercase_ascii == 'harboe cola'
    assert context.location_id == 296
    assert context.location == 'Silent Hill'
    assert context.location_lowercase_ascii == 'silent hill'
    assert context.product_new == get_product_new()
    assert context.product_old == get_product_old()
    assert context.event == ProductUpdateEvent.PRODUCT_UPDATED
    assert context.timestamp == 1609459210  # 1609459200 + 10
    with pytest.raises(AttributeError):  # access a user-defined attribute
        context.foo  # noqa: B018  # type: ignore


def test_getattr_default():
    context = ProductUpdateContext({})
    with pytest.raises(KeyError):
        context.event  # noqa: B018
    with pytest.raises(KeyError):
        context.product_new  # noqa: B018
    with pytest.raises(KeyError):
        context.product_old  # noqa: B018


def test_asdict(context: ProductUpdateContext, context_kwargs: dict):
    assert context.asdict() == context_kwargs
