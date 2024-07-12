import asyncio
import sys
from inspect import Parameter, Signature
from typing import Literal, Union
from unittest.mock import AsyncMock, MagicMock

import pytest
from freshpointsync.product import Product
from freshpointsync.update import (
    ProductUpdateContext,
    ProductUpdateEvent,
    ProductUpdateEventPublisher,
)


def new_handler(
    type_: Literal['sync', 'async'],
) -> Union[AsyncMock, MagicMock]:
    if type_ == 'sync':
        handler = MagicMock()
    elif type_ == 'async':
        handler = AsyncMock()
    else:
        raise ValueError(f'Invalid handler type: {type_}')
    params = [Parameter('context', Parameter.POSITIONAL_OR_KEYWORD)]
    handler.__signature__ = Signature(
        parameters=params, return_annotation=None
    )
    return handler


@pytest.fixture(name='sync_handler', scope='function')
def fixture_sync_handler() -> MagicMock:
    return new_handler('sync')


@pytest.fixture(name='async_handler', scope='function')
def fixture_async_handler() -> AsyncMock:
    return new_handler('async')


def handler_callback(fut):
    pass


def test_subscribe_sync(sync_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(sync_handler, event)
    assert event not in publisher.async_subscribers
    handler_data = publisher.sync_subscribers[event][0]
    assert sync_handler == handler_data.handler
    assert handler_data.exec_params.run_safe is True
    assert handler_data.exec_params.done_callback is None
    sync_handler.assert_not_called()


@pytest.mark.skipif(
    sys.version_info < (3, 10),
    reason=(
        "'AsyncMock' is not recognized by 'inspect' as an asynchronous handler "
        'on Python 3.9 and earlier'
    ),
)
def test_subscribe_async(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(async_handler, event)
    assert event not in publisher.sync_subscribers
    handler_data = publisher.async_subscribers[event][0]
    assert async_handler == handler_data.handler
    assert handler_data.exec_params.run_safe is True
    assert handler_data.exec_params.done_callback is None
    async_handler.assert_not_called()


def test_subscribe_with_params(sync_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(
        sync_handler,
        event,
        run_safe=False,
        handler_done_callback=handler_callback,
    )
    assert event not in publisher.async_subscribers
    handler_data = publisher.sync_subscribers[event][0]
    assert sync_handler == handler_data.handler
    assert handler_data.exec_params.run_safe is False
    assert handler_data.exec_params.done_callback is handler_callback
    sync_handler.assert_not_called()


def test_subscribe_same_twice(sync_handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(sync_handler, ProductUpdateEvent.PRODUCT_ADDED)
    publisher.subscribe(sync_handler, ProductUpdateEvent.PRODUCT_ADDED)
    subscribers = publisher.sync_subscribers[ProductUpdateEvent.PRODUCT_ADDED]
    assert len([s for s in subscribers if s.handler is sync_handler]) == 1


def test_is_subscribed(sync_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    assert publisher.is_subscribed(event=event) is False
    publisher.subscribe(sync_handler, event)
    assert publisher.is_subscribed(event=event) is True


def test_unsubscribe_subscribed(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    assert event not in publisher.async_subscribers
    assert publisher.is_subscribed(event=event) is False
    publisher.subscribe(async_handler, ProductUpdateEvent.PRODUCT_ADDED)
    assert publisher.is_subscribed(event=event) is True
    publisher.unsubscribe(async_handler, ProductUpdateEvent.PRODUCT_ADDED)
    assert publisher.is_subscribed(event=event) is False


def test_unsubscribe_unsubscribed(async_handler):
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    assert event not in publisher.async_subscribers
    assert publisher.is_subscribed(event=event) is False
    publisher.unsubscribe(async_handler, ProductUpdateEvent.PRODUCT_ADDED)
    assert ProductUpdateEvent.PRODUCT_ADDED not in publisher.async_subscribers
    assert publisher.is_subscribed(event=event) is False


def test_unsubscribe_all():
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(new_handler('async'), event)
    publisher.subscribe(new_handler('async'), event)
    publisher.subscribe(new_handler('sync'), event)
    publisher.subscribe(new_handler('sync'), event)
    assert publisher.is_subscribed(event=event) is True
    publisher.unsubscribe(None, event)
    assert publisher.is_subscribed(event=event) is False


def test_unsubscribe_all_empty():
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    assert publisher.is_subscribed(event=event) is False
    publisher.unsubscribe(None, event)
    assert publisher.is_subscribed(event=event) is False


@pytest.mark.asyncio
async def test_subscribe_and_post_and_unsubscribe(async_handler):  # noqa: RUF029
    publisher = ProductUpdateEventPublisher()
    event = ProductUpdateEvent.PRODUCT_ADDED
    publisher.subscribe(async_handler, event)
    product_new = Product(id_=123, name='foo')
    product_old = None
    publisher.post(event, product_new, product_old)
    async_handler.assert_called_once()
    async_handler.reset_mock()
    publisher.unsubscribe(async_handler, event)
    publisher.post(event, product_new, product_old)
    async_handler.assert_not_called()


@pytest.mark.asyncio
async def test_post_no_subcriptions():  # noqa: RUF029
    publisher = ProductUpdateEventPublisher()
    publisher.post(ProductUpdateEvent.PRODUCT_ADDED, None, None)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'handler', [new_handler('async'), new_handler('sync')]
)
async def test_subscribe_one_to_one_and_post_other(handler):  # noqa: RUF029
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(handler, ProductUpdateEvent.PRODUCT_ADDED)
    publisher.post(ProductUpdateEvent.PRODUCT_REMOVED, None, None)
    handler.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'handler', [new_handler('async'), new_handler('sync')]
)
async def test_subscribe_one_to_one_and_post_once(handler):  # noqa: RUF029
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(handler, ProductUpdateEvent.PRODUCT_ADDED)
    product_new = Product(id_=123, name='foo')
    product_old = None
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_new, product_old, foo='bar'
    )
    context = ProductUpdateContext({
        'foo': 'bar',
        'event': ProductUpdateEvent.PRODUCT_ADDED,
        'product_new': product_new,
        'product_old': product_old,
    })
    handler.assert_called_once_with(context)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'handler', [new_handler('async'), new_handler('sync')]
)
async def test_subscribe_one_to_one_and_post_twice(handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(handler, ProductUpdateEvent.PRODUCT_ADDED)
    product_new = Product(id_=123, name='foo')
    product_old = None
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_new, product_old, foo='bar'
    )
    publisher.post(
        ProductUpdateEvent.PRODUCT_ADDED, product_old, product_new, bar='foo'
    )
    await asyncio.sleep(0.1)  # let the event loop run
    assert handler.call_count == 2
    last_context = ProductUpdateContext({
        'bar': 'foo',
        'event': ProductUpdateEvent.PRODUCT_ADDED,
        'product_new': None,
        'product_old': product_new,
    })
    handler.assert_called_with(last_context)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    'handler', [new_handler('async'), new_handler('sync')]
)
async def test_subscribe_one_to_multiple_and_post_each_once(handler):
    publisher = ProductUpdateEventPublisher()
    publisher.subscribe(handler, ProductUpdateEvent.PRODUCT_ADDED)
    publisher.subscribe(handler, ProductUpdateEvent.PRODUCT_REMOVED)
    product_new = Product(id_=123, name='foo')
    product_old = None
    publisher.post(ProductUpdateEvent.PRODUCT_ADDED, product_new, product_old)
    publisher.post(
        ProductUpdateEvent.PRODUCT_REMOVED, product_old, product_new
    )
    await asyncio.sleep(0.1)  # let the event loop run
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_subscribe_multiple_to_multiple_and_post_multiple():
    publisher = ProductUpdateEventPublisher()
    handler_1 = new_handler('async')
    handler_2 = new_handler('async')
    handler_3 = new_handler('async')
    handler_4 = new_handler('async')
    publisher.subscribe(handler_1, ProductUpdateEvent.PRODUCT_UPDATED)
    publisher.subscribe(handler_2, ProductUpdateEvent.PRICE_UPDATED)
    publisher.subscribe(handler_3, ProductUpdateEvent.QUANTITY_UPDATED)
    publisher.subscribe(handler_4, ProductUpdateEvent.OTHER_UPDATED)
    product_new = Product(
        id_=123, name='foo', quantity=1, price_full=90, price_curr=90
    )
    product_old = Product(
        id_=123, name='foo', quantity=2, price_full=80, price_curr=70
    )
    events = [
        ProductUpdateEvent.PRODUCT_UPDATED,
        ProductUpdateEvent.PRICE_UPDATED,
        ProductUpdateEvent.QUANTITY_UPDATED,
    ]
    for event in events:
        publisher.post(
            event=event,
            product_new=product_new,
            product_old=product_old,
            arg='test',
        )
    await asyncio.sleep(0.1)  # let the event loop run
    context_product_updated = ProductUpdateContext({
        'arg': 'test',
        'event': ProductUpdateEvent.PRODUCT_UPDATED,
        'product_new': product_new,
        'product_old': product_old,
    })
    context_price_updated = ProductUpdateContext({
        'arg': 'test',
        'event': ProductUpdateEvent.PRICE_UPDATED,
        'product_new': product_new,
        'product_old': product_old,
    })
    context_quantity_updated = ProductUpdateContext({
        'arg': 'test',
        'event': ProductUpdateEvent.QUANTITY_UPDATED,
        'product_new': product_new,
        'product_old': product_old,
    })
    handler_1.assert_called_once_with(context_product_updated)
    handler_2.assert_called_once_with(context_price_updated)
    handler_3.assert_called_once_with(context_quantity_updated)
    handler_4.assert_not_called()
