import asyncio
import pytest

from unittest.mock import create_autospec

from freshpointsync.product import Product
from freshpointsync.update import (
    ProductCacheUpdater,
    ProductUpdateEvent,
    ProductUpdateEventPublisher
)


class Handlers:
    """
    Provides a set of handlers for testing purposes.
    """
    def __init__(self):
        self.handler_add = create_autospec(self.handler)
        self.handler_delete = create_autospec(self.handler)
        self.handler_update = create_autospec(self.handler)
        self.handler_update_quantity = create_autospec(self.handler)
        self.handler_update_price = create_autospec(self.handler)

    def handler(self, context) -> None:
        pass


@pytest.fixture
def cache_updater_with_handlers() -> tuple[ProductCacheUpdater, Handlers]:
    """
    Provides a `ProductCacheUpdater` instance with two products in cache
    and mock handlers subscribed to events. The handlers are also returned.
    """
    products = {
        1: Product(
            product_id=1,
            name="Product 1",
            quantity=10,
            price_full=10.0,
            price_curr=8.0,
            pic_url="pic1.jpg"
            ),
        2: Product(
            product_id=2,
            name="Product 2",
            quantity=5,
            price_full=5.0,
            price_curr=4.0,
            pic_url="pic2.jpg"
            ),
        }
    publisher = ProductUpdateEventPublisher()
    handlers = Handlers()
    publisher.subscribe(
        ProductUpdateEvent.PRODUCT_ADDED, handlers.handler_add
        )
    publisher.subscribe(
        ProductUpdateEvent.PRODUCT_REMOVED, handlers.handler_delete
        )
    publisher.subscribe(
        ProductUpdateEvent.PRODUCT_UPDATED, handlers.handler_update
        )
    publisher.subscribe(
        ProductUpdateEvent.QUANTITY_UPDATED, handlers.handler_update_quantity
        )
    publisher.subscribe(
        ProductUpdateEvent.PRICE_UPDATED, handlers.handler_update_price
        )
    return ProductCacheUpdater(products, publisher), handlers


@pytest.fixture
def product_batch():
    return [
        Product(
            product_id=1,
            name="Product 1",
            quantity=15,
            price_full=10.0,
            price_curr=8.0,
            pic_url="pic1.jpg"
            ),
        Product(
            product_id=2,
            name="Product 2",
            quantity=5,
            price_full=5.0,
            price_curr=3.0,
            pic_url="pic2.jpg"
            ),
        Product(
            product_id=4,
            name="Product 4",
            quantity=7,
            price_full=7.0,
            price_curr=6.0,
            pic_url="pic4.jpg"
            ),
        ]


@pytest.mark.asyncio  # async because we need to initialize the event loop
async def test_create_product(cache_updater_with_handlers):
    product = Product(
        product_id=3,
        name="Product 3",
        quantity=20,
        price_full=15.0,
        price_curr=12.0,
        pic_url="pic3.jpg"
        )
    updater, handlers = cache_updater_with_handlers
    updater.create_product(product)
    await asyncio.sleep(0.1)  # allow time for the event to be processed
    assert updater.products[3] == product
    handlers.handler_add.assert_called_once()


@pytest.mark.asyncio
async def test_delete_product(cache_updater_with_handlers):
    updater, handlers = cache_updater_with_handlers
    product = updater.products[1]
    updater.delete_product(product)
    await asyncio.sleep(0.1)  # allow time for the event to be processed
    assert 1 not in updater.products
    handlers.handler_delete.assert_called_once()


@pytest.mark.asyncio
async def test_update_product(cache_updater_with_handlers):
    updater, handlers = cache_updater_with_handlers
    product = Product(
        product_id=2,
        name="Product 2",
        quantity=8,
        price_full=5.0,
        price_curr=4.0,
        pic_url="pic2.jpg"
        )
    product_cached = updater.products[2]  # 2 is the product_id
    updater.update_product(product, product_cached)
    await asyncio.sleep(0.1)  # allow time for the event to be processed
    assert updater.products[2] == product
    handlers.handler_update.assert_called_once()
    handlers.handler_update_quantity.assert_called_once()
    handlers.handler_update_price.assert_not_called()


@pytest.mark.asyncio
async def test_update(cache_updater_with_handlers, product_batch):
    updater, handlers = cache_updater_with_handlers
    await updater.update(product_batch, await_handlers=True)
    assert len(updater.products) == 3
    assert updater.products[1].quantity == 15
    assert updater.products[2].quantity == 5
    assert updater.products[2].price_curr == 3.0
    assert updater.products[4] == product_batch[2]  # new product
    handlers.handler_add.assert_called_once()
    handlers.handler_delete.assert_not_called()
    handlers.handler_update.assert_called()
    handlers.handler_update_quantity.assert_called()
    handlers.handler_update_price.assert_called_once()


@pytest.mark.asyncio
async def test_update_silently(cache_updater_with_handlers, product_batch):
    updater, handlers = cache_updater_with_handlers
    updater.update_silently(product_batch)
    await asyncio.sleep(0.1)  # allow time for the event to be processed
    assert len(updater.products) == 3
    assert updater.products[1].quantity == 15
    assert updater.products[2].quantity == 5
    assert updater.products[2].price_curr == 3.0
    assert updater.products[4] == product_batch[2]  # new product
    handlers.handler_add.assert_not_called()
    handlers.handler_delete.assert_not_called()
    handlers.handler_update.assert_not_called()
    handlers.handler_update_quantity.assert_not_called()
    handlers.handler_update_price.assert_not_called()
