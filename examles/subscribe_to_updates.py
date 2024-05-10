"""This example demonstrates how to subscribe to product updates.
Note that this example is a small continuous application that will run
until it is interrupted by the user. It may take some time for
a product update to occur on the tracked page.
"""

import asyncio
import time

from freshpointsync import ProductPage, ProductUpdateEvent
from freshpointsync.update import ProductUpdateContext


LOCATION_ID = 296
"""The number in the end of the URL of the Freshpoint.cz location page"""


async def on_product_update(context: ProductUpdateContext) -> None:
    """Handle all product update events with an asynchronous function."""
    assert context.product_new is not None  # should not be None
    assert context.product_old is not None  # for the UPDATE event
    # example of a custom context data use-case:
    # measure the elapsed time since the last update
    time_last_update = context.get('last_update')  # get the last update time
    if time_last_update is not None:
        time_elapsed = time.time() - time_last_update
        print(f'Time since the last update: {time_elapsed:.2f} seconds')
    page = context.get('page')  # access the page instance from the context
    if page is not None:
        # setting this directly in the passed context is not possible
        page.context['last_update'] = time.time()  # set the last update time
    print(
        f'Sending a notification about the product '
        f'"{context.product_old.name}" update...'
        )
    await asyncio.sleep(1)  # simulate a delay for some asynchronous operation


def on_product_price_update(context: ProductUpdateContext) -> None:
    """Handle all price update events."""
    assert context.product_new is not None  # should not be None
    assert context.product_old is not None  # for the UPDATE event
    price_curr = f'{context.product_new.price_curr:.2f} CZK'
    price_prev = f'{context.product_old.price_curr:.2f} CZK'
    print(
        f'Product "{context.product_old.name}" price update: '
        f'{price_prev} -> {price_curr}'
        )


def on_product_quantity_update(context: ProductUpdateContext) -> None:
    """Handle all quantity update events."""
    assert context.product_new is not None  # should not be None
    assert context.product_old is not None  # for the UPDATE event
    quantity_curr = f'{context.product_new.quantity} items'
    quantity_prev = f'{context.product_old.quantity} items'
    print(
        f'Product "{context.product_old.name}" quantity update: '
        f'{quantity_prev} -> {quantity_curr}'
        )


async def main():
    page = ProductPage(location_id=LOCATION_ID)
    try:
        print('Fetching the initial product data...')
        await page.start_session()
        # update product listings without triggering an update event
        await page.update_silently()
        # subscribe to product update events.
        print('Subscribing to updates...')
        # set custom context data for the update handlers. The context is
        # a dictionary that can be used to store any data that should be
        # accessible to the handlers. It is a clean way to pass data between
        # the handlers and the main application logic.
        page.context['page'] = page  # reference to the page instance
        page.context['last_update'] = time.time()
        # add the update handlers. The handler should expect one argument,
        # the update context.
        # The handlers are triggered in the order they were added, but they
        # effectively run in parallel. It is recommended to make the handlers
        # independent of each other.
        # Asynchronous handlers are executed in the main event loop.
        # Synchronous handlers are executed in a separate thread, so
        # the event loop is not blocked (note that this may lead to
        # race conditions in some cases. For example, if the handler
        # writes to a shared resource, like a file, it should be protected
        # by a lock. Or simply use an asynchronous handler.)
        # An optional 'handler_done_callback' is called after the handler
        # is done executing.
        page.subscribe_for_update(
            handler=on_product_update,  # asynchronous handler
            event=ProductUpdateEvent.PRODUCT_UPDATED,
            handler_done_callback=lambda f: print('Notification sent.')
            )
        page.subscribe_for_update(
            handler=on_product_price_update,  # synchronous handler
            event=ProductUpdateEvent.PRICE_UPDATED
            )
        page.subscribe_for_update(
            handler=on_product_quantity_update,  # synchronous handler
            event=ProductUpdateEvent.QUANTITY_UPDATED
            )
        print('Subscribed to updates. Press Ctrl+C to exit.')
        await page.update_forever(interval=2)  # update every 2 seconds
        # alternatively, use 'page.create_update_forever_task()' to run
        # the update in the background or 'await page.update()' to run
        # the update once
        # page.create_update_forever_task()
        # await page.update()
    except asyncio.CancelledError:
        print('Exiting...')
    except Exception as e:
        print(f'Error: {e}')
    finally:
        await page.close_session()
        # would be necessary for 'page.create_update_forever_task()'
        # await page.cancel_update_forever()
        await page.await_update_handlers()  # or cancel


if __name__ == "__main__":
    asyncio.run(main())
