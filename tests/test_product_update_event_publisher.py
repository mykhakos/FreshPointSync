import asyncio
import pytest

from inspect import Parameter, Signature
from unittest.mock import AsyncMock, MagicMock, create_autospec

from freshpointsync.product import Product
from freshpointsync.update import (
    ProductUpdateEvent, ProductUpdateEventPublisher, ProductUpdateContext
)


def new_sync_handler() -> MagicMock:
    def handler(context):
        pass
    return create_autospec(handler, return_value=None)


@pytest.fixture
def sync_handler() -> MagicMock:
    return new_sync_handler()


def new_async_handler() -> AsyncMock:
    params = [Parameter("context", Parameter.POSITIONAL_OR_KEYWORD)]
    handler = AsyncMock()
    handler.__signature__ = Signature(parameters=params)
    return handler


@pytest.fixture
def async_handler() -> AsyncMock:
    return new_async_handler()


def test_subscribe_sync(sync_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(event, sync_handler)
    assert event not in publisher.async_subscribers
    assert sync_handler in publisher.sync_subscribers[event]
    sync_handler.assert_not_called()


def test_subscribe_async(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(event, async_handler)
    assert event not in publisher.sync_subscribers
    assert async_handler in publisher.async_subscribers[event]
    async_handler.assert_not_called()


def test_subscribe_same_twice(async_handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    subscribers = publisher.async_subscribers[ProductUpdateEvent.PRODUCT_ADDED]
    assert subscribers.count(async_handler) == 1


def test_unsubscribe_subscribed(async_handler):
    publisher = ProductUpdateEventPublisher()
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    subscribers = publisher.async_subscribers[ProductUpdateEvent.PRODUCT_ADDED]
    assert async_handler in subscribers
    publisher.unsubscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    assert async_handler not in subscribers


def test_unsubscribe_unsubscribed(async_handler):
    publisher = ProductUpdateEventPublisher()
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers
    publisher.unsubscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers


@pytest.mark.asyncio
async def test_post_no_sunscriptions():
    publisher = ProductUpdateEventPublisher()
    publisher.post(ProductUpdateEvent.PRODUCT_ADDED, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [new_async_handler(), new_sync_handler()])
async def test_subscribe_one_to_one_and_post_wrong(handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, handler)
    publisher.post(ProductUpdateEvent.PRODUCT_REMOVED, None, None)
    handler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [new_async_handler(), new_sync_handler()])
async def test_subscribe_one_to_one_and_post_once(handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, handler)
    product_new = Product('foo', 123)
    product_old = None
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_new, product_old, foo='bar'
        )
    context = ProductUpdateContext(
        {
            'foo': 'bar',
            'product_new': product_new,
            'product_old': product_old,
            'location_id': 0,
            'location_name': ''
        }
    )
    handler.assert_called_once_with(context)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [new_async_handler(), new_sync_handler()])
async def test_subscribe_one_to_one_and_post_twice(handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, handler)
    product_new = Product('foo', 123)
    product_old = None
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_new, product_old, foo='bar'
        )
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_old, product_new, bar='foo'
        )
    await asyncio.sleep(0.1)  # let the event loop run
    assert handler.call_count == 2
    last_context = ProductUpdateContext(
        {
            'bar': 'foo',
            'product_new': None,
            'product_old': product_new,
            'location_id': 0,
            'location_name': ''
        }
    )
    handler.assert_called_with(last_context)


@pytest.mark.asyncio
@pytest.mark.parametrize("handler", [new_async_handler(), new_sync_handler()])
async def test_subscribe_one_to_multiple_and_post_each_once(handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, handler)
    publisher.subscribe(ProductUpdateEvent.PRODUCT_REMOVED, handler)
    product_new = Product('foo', 123)
    product_old = None
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_new, product_old
        )
    publisher.post(
        ProductUpdateEvent.PRODUCT_REMOVED, product_old, product_new
        )
    await asyncio.sleep(0.1)  # let the event loop run
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_subscribe_multiple_to_multiple_and_post_multiple():
    publisher = ProductUpdateEventPublisher()
    handler_1 = new_async_handler()
    handler_2 = new_async_handler()
    handler_3 = new_async_handler()
    handler_4 = new_async_handler()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_UPDATED, handler_1)
    publisher.subscribe(ProductUpdateEvent.PRICE_UPDATED, handler_2)
    publisher.subscribe(ProductUpdateEvent.STOCK_UPDATED, handler_3)
    publisher.subscribe(ProductUpdateEvent.PIC_URL_UPDATED, handler_4)
    product_new = Product('foo', 123, quantity=1, price_full=90, price_curr=90)
    product_old = Product('foo', 123, quantity=2, price_full=80, price_curr=70)
    publisher.post_multiple(
        events=[
            ProductUpdateEvent.PRODUCT_UPDATED,
            ProductUpdateEvent.PRICE_UPDATED,
            ProductUpdateEvent.STOCK_UPDATED,
        ],
        product_new=product_new,
        product_old=product_old,
        arg='test'
    )
    await asyncio.sleep(0.1)  # let the event loop run
    context = ProductUpdateContext(
        {
            'arg': 'test',
            'product_new': product_new,
            'product_old': product_old,
            'location_id': 0,
            'location_name': ''
        }
    )
    handler_1.assert_called_once_with(context)
    handler_2.assert_called_once_with(context)
    handler_3.assert_called_once_with(context)
    handler_4.assert_not_called()
