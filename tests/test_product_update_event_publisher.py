import asyncio
import pytest

from unittest.mock import AsyncMock, Mock

from ._freshpoint_sync import (
    ProductUpdateEventPublisher, ProductUpdate, Product
)


def test_subscribe_async():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    assert handler in publisher.subscribers[ProductUpdate.PRODUCT_ADDED]
    handler.assert_not_called()


def test_subscribe_same_twice():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    subscribers = publisher.subscribers[ProductUpdate.PRODUCT_ADDED]
    assert subscribers.count(handler) == 1


def test_subscribe_sync():
    publisher = ProductUpdateEventPublisher()
    handler = Mock()
    with pytest.raises(TypeError):
        publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    assert ProductUpdate.PRODUCT_ADDED not in publisher.subscribers


def test_unsubscribe_subscribed():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    assert ProductUpdate.PRODUCT_ADDED not in publisher.subscribers
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    subscribers = publisher.subscribers[ProductUpdate.PRODUCT_ADDED]
    assert handler in subscribers
    publisher.unsubscribe(ProductUpdate.PRODUCT_ADDED, handler)
    assert handler not in subscribers


def test_unsubscribe_unsubscribed():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    assert ProductUpdate.PRODUCT_ADDED not in publisher.subscribers
    publisher.unsubscribe(ProductUpdate.PRODUCT_ADDED, handler)
    assert ProductUpdate.PRODUCT_ADDED not in publisher.subscribers


@pytest.mark.asyncio
async def test_post_no_sunscriptions():
    publisher = ProductUpdateEventPublisher()
    await publisher.post(ProductUpdate.PRODUCT_ADDED, None, None)


@pytest.mark.asyncio
async def test_subscribe_one_to_one_and_post_wrong():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    await publisher.post(ProductUpdate.PRODUCT_REMOVED, None, None)
    handler.assert_not_called()


@pytest.mark.asyncio
async def test_subscribe_one_to_one_and_post_once():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    product_new = Product('foo', 123)
    product_old = None
    await publisher.post(
        ProductUpdate.PRODUCT_ADDED, product_new, product_old, foo='bar'
        )
    handler.assert_called_once_with(
        {
            'product_state_new': product_new,
            'product_state_old': product_old,
            'foo': 'bar'
        }
    )


@pytest.mark.asyncio
async def test_subscribe_one_to_one_and_post_twice():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    product_new = Product('foo', 123)
    product_old = None
    await publisher.post(
        ProductUpdate.PRODUCT_ADDED, product_new, product_old, foo='bar'
        )
    await publisher.post(
        ProductUpdate.PRODUCT_ADDED, product_old, product_new, bar='foo'
        )
    assert handler.call_count == 2
    handler.assert_called_with(
        {
            'product_state_new': product_old,
            'product_state_old': product_new,
            'bar': 'foo'
        }
    )


@pytest.mark.asyncio
async def test_subscribe_one_to_multiple_and_post_each_once():
    publisher = ProductUpdateEventPublisher()
    handler = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_ADDED, handler)
    publisher.subscribe(ProductUpdate.PRODUCT_REMOVED, handler)
    product_new = Product('foo', 123)
    product_old = None
    async with asyncio.TaskGroup() as tg:
        task_create = publisher.post(
            ProductUpdate.PRODUCT_ADDED, product_new, product_old
            )
        task_delete = publisher.post(
            ProductUpdate.PRODUCT_REMOVED, product_old, product_new
            )
        tg.create_task(task_create)
        tg.create_task(task_delete)
    assert handler.call_count == 2


@pytest.mark.asyncio
async def test_subscribe_multiple_to_multiple_and_post_multiple():
    publisher = ProductUpdateEventPublisher()
    handler_1 = AsyncMock()
    handler_2 = AsyncMock()
    handler_3 = AsyncMock()
    handler_4 = AsyncMock()
    publisher.subscribe(ProductUpdate.PRODUCT_UPDATED, handler_1)
    publisher.subscribe(ProductUpdate.PRICE_UPDATED, handler_2)
    publisher.subscribe(ProductUpdate.STOCK_UPDATED, handler_3)
    publisher.subscribe(ProductUpdate.PIC_URL_UPDATED, handler_4)
    product_new = Product('foo', 123, count=1, price_full=90, price_curr=90)
    product_old = Product('foo', 123, count=2, price_full=80, price_curr=70)
    await publisher.post_multiple(
        events=[
            ProductUpdate.PRODUCT_UPDATED,
            ProductUpdate.PRICE_UPDATED,
            ProductUpdate.STOCK_UPDATED,
        ],
        product_state_new=product_new,
        product_state_old=product_old,
        arg='test'
    )
    handler_1.assert_called_once_with(
        {
            'product_state_new': product_new,
            'product_state_old': product_old,
            'arg': 'test'
        }
    )
    handler_2.assert_called_once_with(
        {
            'product_state_new': product_new,
            'product_state_old': product_old,
            'arg': 'test'
        }
    )
    handler_3.assert_called_once_with(
        {
            'product_state_new': product_new,
            'product_state_old': product_old,
            'arg': 'test'
        }
    )
    handler_4.assert_not_called()
