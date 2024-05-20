==============================
Subscribing to Product Updates
==============================

The ``ProductPage`` class allows you to subscribe to product updates and handle
them using custom handlers. Subscribing to updates enables you to define
specific actions that will be executed when certain update events occur.

This example demonstrates how to subscribe to product updates and handle them
using custom handlers. The script will run continuously until interrupted by
the user. Note that it may take some time for a product update to occur on
the tracked page.

Handling Product Updates
------------------------
First, define handlers for general product updates, price updates, and quantity
updates. A handler must be a synchronous or asynchronous callable that accepts
a single argument of type ``ProductUpdateContext``. The context contains
the old and new product data (if applicable), the type of event that
triggered the update, and custom user data in key-value pairs.

.. code-block:: python

    async def on_product_update(context: ProductUpdateContext) -> None:
        """Handle all product update events."""
        print(f'Product "{context.product_old.name}" was updated.')
        await asyncio.sleep(1)  # simulate a delay for some IO operation

    def on_product_price_update(context: ProductUpdateContext) -> None:
        """Handle all price update events."""
        price_curr = f'{context.product_new.price_curr:.2f} CZK'
        price_prev = f'{context.product_old.price_curr:.2f} CZK'
        print(
            f'Product "{context.product_old.name}" price update: '
            f'{price_prev} -> {price_curr}'
        )

    def on_product_quantity_update(context: ProductUpdateContext) -> None:
        """Handle all quantity update events."""
        quantity_curr = f'{context.product_new.quantity} items'
        quantity_prev = f'{context.product_old.quantity} items'
        print(
            f'Product "{context.product_old.name}" quantity update: '
            f'{quantity_prev} -> {quantity_curr}'
        )

The handlers in this example print the product name and the type of update
event that occurred. The ``on_product_update`` handler also simulates a delay
of one second, which cound correspond to some IO operation. These handlers
are aimed to run on a product update event, so both ``context.product_new`` and
``context.product_old`` are guaranteed to be present. Unfortunatelly, there is
no way to type-check this within the ``ProductUpdateContext`` class.

.. tip::

   If hanlders share data between each other or with other parts of
   the application, such as a shared state or a dump of the product data,
   make sure to use locks or other appropriate synchronization mechanisms
   to avoid race conditions.

Subscribing to Updates
----------------------
Then, create a new ``ProductPage`` instance for a specific location and update
the product listings. Learn more about creating ``ProductPage`` instances in
the :doc:`init_product_page` example. Subscribe to product update events and
handle them accordingly.

.. code-block:: python

    from freshpointsync import ProductPage, ProductUpdateEvent

    async def main():
        page = ProductPage(location_id=296)
        try:
            print('Fetching the initial product data...')
            await page.start_session()
            await page.update_silently()
            print('Subscribing to updates...')
            page.subscribe_for_update(
                handler=on_product_update,
                event=ProductUpdateEvent.PRODUCT_UPDATED,
                handler_done_callback=lambda f: print('Product update handled.')
            )
            page.subscribe_for_update(
                handler=on_product_price_update,
                event=ProductUpdateEvent.PRICE_UPDATED
            )
            page.subscribe_for_update(
                handler=on_product_quantity_update,
                event=ProductUpdateEvent.QUANTITY_UPDATED
            )
            print('Subscribed to updates. Press Ctrl+C to exit.')
            await page.update_forever(interval=5)
        except asyncio.CancelledError:
            print('Exiting...')
        except Exception as e:
            print(f'Error: {e}')
        finally:
            await page.close_session()
            await page.await_update_handlers()

    if __name__ == "__main__":
        asyncio.run(main())

In this example, the ``ProductPage`` instance is created, and product data is
fetched. The script subscribes to product update events and handles them using
the provided handlers. The application will run until interrupted by the user.
The handlers demonstrate how to handle product updates, price updates, and
quantity updates.

.. note::
   Neither synchronous nor asynchronous handlers block the event loop.
   However, using asynchronous handlers is advised for most use cases.

Complete Example
----------------

Here is the complete example for subscribing to product updates:

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage, ProductUpdateEvent
    from freshpointsync.update import ProductUpdateContext

    async def on_product_update(context: ProductUpdateContext) -> None:
        """Handle all product update events."""
        print(f'Product "{context.product_old.name}" was updated.')
        await asyncio.sleep(1)

    def on_product_price_update(context: ProductUpdateContext) -> None:
        """Handle all price update events."""
        price_curr = f'{context.product_new.price_curr:.2f} CZK'
        price_prev = f'{context.product_old.price_curr:.2f} CZK'
        print(
            f'Product "{context.product_old.name}" price update: '
            f'{price_prev} -> {price_curr}'
        )

    def on_product_quantity_update(context: ProductUpdateContext) -> None:
        """Handle all quantity update events."""
        quantity_curr = f'{context.product_new.quantity} items'
        quantity_prev = f'{context.product_old.quantity} items'
        print(
            f'Product "{context.product_old.name}" quantity update: '
            f'{quantity_prev} -> {quantity_curr}'
        )

    async def main():
        page = ProductPage(location_id=296)
        try:
            print('Fetching the initial product data...')
            await page.start_session()
            await page.update_silently()
            print('Subscribing to updates...')
            page.subscribe_for_update(
                handler=on_product_update,
                event=ProductUpdateEvent.PRODUCT_UPDATED,
                handler_done_callback=lambda f: print('Product update handled.')
            )
            page.subscribe_for_update(
                handler=on_product_price_update,
                event=ProductUpdateEvent.PRICE_UPDATED
            )
            page.subscribe_for_update(
                handler=on_product_quantity_update,
                event=ProductUpdateEvent.QUANTITY_UPDATED
            )
            print('Subscribed to updates. Press Ctrl+C to exit.')
            await page.update_forever(interval=2)
        except asyncio.CancelledError:
            print('Exiting...')
        except Exception as e:
            print(f'Error: {e}')
        finally:
            await page.close_session()
            await page.await_update_handlers()

    if __name__ == "__main__":
        asyncio.run(main())
