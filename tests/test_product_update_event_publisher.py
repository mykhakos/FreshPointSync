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


def handler_callback(fut):
    pass


def test_subscribe_sync(sync_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(event, sync_handler)
    assert event not in publisher.async_subscribers
    handler_data = publisher.sync_subscribers[event][0]
    assert sync_handler == handler_data.handler
    assert handler_data.exec_params.call_safe is True
    assert handler_data.exec_params.done_callback is None
    sync_handler.assert_not_called()


def test_subscribe_async(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(event, async_handler)
    assert event not in publisher.sync_subscribers
    handler_data = publisher.async_subscribers[event][0]
    assert async_handler == handler_data.handler
    assert handler_data.exec_params.call_safe is True
    assert handler_data.exec_params.done_callback is None
    async_handler.assert_not_called()


def test_subscribe_with_params(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(
        event,
        async_handler,
        call_safe=False,
        handler_done_callback=handler_callback
        )
    assert event not in publisher.sync_subscribers
    handler_data = publisher.async_subscribers[event][0]
    assert async_handler == handler_data.handler
    assert handler_data.exec_params.call_safe is False
    assert handler_data.exec_params.done_callback is handler_callback
    async_handler.assert_not_called()


def test_subscribe_same_twice(async_handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    subscribers = publisher.async_subscribers[ProductUpdateEvent.PRODUCT_ADDED]
    assert len([s for s in subscribers if s.handler is async_handler]) == 1


def test_is_subscribed(sync_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    assert publisher.is_subscribed(event) is False
    publisher.subscribe(event, sync_handler)
    assert publisher.is_subscribed(event) is True


def test_unsubscribe_subscribed(async_handler):
    publisher = ProductUpdateEventPublisher()
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers
    assert publisher.is_subscribed(ProductUpdateEvent.PRODUCT_ADDED) is False
    publisher.subscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    assert publisher.is_subscribed(ProductUpdateEvent.PRODUCT_ADDED) is True
    publisher.unsubscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    assert publisher.is_subscribed(ProductUpdateEvent.PRODUCT_ADDED) is False


def test_unsubscribe_unsubscribed(async_handler):
    publisher = ProductUpdateEventPublisher()
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers
    assert publisher.is_subscribed(ProductUpdateEvent.PRODUCT_ADDED) is False
    publisher.unsubscribe(ProductUpdateEvent.PRODUCT_ADDED, async_handler)
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers
    assert publisher.is_subscribed(ProductUpdateEvent.PRODUCT_ADDED) is False


def test_unsubscribe_all():
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(event, new_async_handler())
    publisher.subscribe(event, new_async_handler())
    publisher.subscribe(event, new_sync_handler())
    publisher.subscribe(event, new_sync_handler())
    assert publisher.is_subscribed(event) is True
    publisher.unsubscribe(event, None)
    assert publisher.is_subscribed(event) is False


def test_unsubscribe_all_empty():
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    assert publisher.is_subscribed(event) is False
    publisher.unsubscribe(event, None)
    assert publisher.is_subscribed(event) is False


@pytest.mark.asyncio
async def test_subscribe_and_post_and_unsubscribe(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(event, async_handler)
    product_new = Product('foo', 123)
    product_old = None
    publisher.post(event, product_new, product_old)
    async_handler.assert_called_once()
    async_handler.reset_mock()
    publisher.unsubscribe(event, async_handler)
    publisher.post(event, product_new, product_old)
    async_handler.assert_not_called()


@pytest.mark.asyncio
async def test_post_no_bscriptions():
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
