===================================
Subscribing to Product Page Updates
===================================

Product page data can be updated using the update methods of the ``ProductPage``
class, namely ``update``, ``update_forever``, and ``init_update_task``. It is
also possible to fetch the data without updating the inner state of the product
page instance using the ``fetch`` method.

You can subscribe to product updates by registering custom handlers for specific
``ProductUpdateEvent`` events with the ``subscribe_for_update`` method. It is
possible to unsubscribe from updates by calling the ``unsubscribe_from_update``
method.

Product Page Update Methods
---------------------------

There are several ways to fetch and update the product page data.

``fetch``
~~~~~~~~~

The ``fetch`` method of the ``ProductPage`` class is used to fetch and return
the product page data. It *does not modify* the inner page data of the instance.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    async def main():
        async with ProductPage(location_id=296) as page:
            assert not page.data.products  # 1. page data is empty
            products = await page.fetch()  # 2. fetch the products
            assert products                # 3. products have been fetched
            assert not page.data.products  # 4. page data remains empty

    if __name__ == "__main__":
        asyncio.run(main())

In this example, the ``fetch`` method is used to fetch the product page data.
The method returns a list of products but does not modify the ``data`` attribute
of the ``ProductPage`` instance.

.. note::

   Providing an invalid location ID will result in an empty list of products.

``update``
~~~~~~~~~~

The ``update`` methods of the ``ProductPage`` class updates the page data with
the latest information from the product page. Its ``silent`` parameter can
enable and disable triggering of update handlers during the update process,
and its ``await_handlers`` parameter can enable and disable waiting for the
handlers to finish in case they have been executed.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    async def main():
        async with ProductPage(location_id=296) as page:
            assert not page.data.products   # 1. page data is empty
            await page.update(silent=True)  # 2. update the products
            assert page.data.products       # 3. page data has been updated

    if __name__ == "__main__":
        asyncio.run(main())

In this example, the ``update`` method is used to fetch and update the product
page data. The update is performed silently, meaning that no registered update
handlers would be triggered. The new data is stored in the ``data`` attribute of
the ``ProductPage`` instance.

``update_forever`` and ``init_update_task``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``update_forever`` method of the ``ProductPage`` class is a wrapper around
``update`` that runs indefinitely. It continuously polls the product page at
regular intervals and updates the data accordingly.

.. note::

    Every update operation means a new HTTP request to the product page. Make
    sure to set a reasonable update interval to avoid overloading the server.

The ``init_update_task`` method is a simple convenience wrapper around
``update_forever`` that creates a new asyncio task for the update process.
This task can be later gracefully cancelled using
the ``cancel_update_forever_task`` method.

.. tip::

    The ``update_forever`` method is useful for long-running applications that
    require real-time updates of the product page data. It is usually the last
    method called in the script, since awaiting it will block the event loop.

    The ``init_update_task`` method is useful for running the update process in
    the background while the main application logic is executed. Calling this
    method does not block the event loop, but the created task must be cancelled
    manually eventually.

Subscribing to Product Updates
------------------------------

The ``ProductPage`` class allows you to subscribe to product updates and handle
them using custom handlers. Subscribing to updates enables you to define
specific actions that will be executed when certain update events occur.

Update Events
~~~~~~~~~~~~~

The range of supported update events is defined by the ``ProductUpdateEvent``
enum. The following events are available:

====================  ==========================================================
Update Event          Description
====================  ==========================================================
``PRODUCT_ADDED``     A new product has been listed on the product page.
``PRODUCT_UPDATED``   An existing product has been updated in any way.
``QUANTITY_UPDATED``  The number of items in stock for a product has been updated.
``PRICE_UPDATED``     The full price and/or current price of a product have been
                      updated.
``OTHER_UPDATED``     An update to a product's metadata, such as its
                      illustration picture.
``PRODUCT_REMOVED``   A product has been removed from the product page.
====================  ==========================================================

Update Handlers
~~~~~~~~~~~~~~~

A handler must be a synchronous callable or an asynchronous coroutine that
accepts a single argument of type ``ProductUpdateContext``. The context contains
the old and the new product data, if applicable for the update event, and
the type of event that triggered the update. It can also be used to pass
arbitrary data to the handlers. To do so, set the desired data as a key-value
pair in the ``context`` mapping of the ``ProductPage`` instance.

.. code-block:: python

    async def on_product_update(context: ProductUpdateContext) -> None:
        """Handle all product update events."""
        product_name = context.product_new.name
        if product_name in context.get('favorite_products', []):
            print(f'Your favorite product "{product_name}" was updated!')
        else:
            print(f'Product "{product_name}" was updated.')
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

The handlers in this example print the product name and the type of update event
that occurred. The ``on_product_update`` handler also simulates a delay of one
second, which could correspond to some IO operation.

.. note::

    The handlers in the example are aimed to run on a product *update* event,
    so both ``context.product_new`` and ``context.product_old`` are guaranteed
    to be present. Unfortunately, there is no way to type-check this within 
    the ``ProductUpdateContext`` class. You may check for the presence of these
    attributes in your handlers with a simple ``if`` statement or ``assert`` or
    suppress the type-checking warning with ``# type: ignore``.

    Context of a *create* event will contain only the new product data, while
    the context of a *delete* event will contain only the old product data.

If a handler is asynchronous, it inherently does not block the event loop. If,
however, a handler is synchronous, it can be executed directly in a blocking
manner or in a separate thread in a non-blocking manner. By default, synchronous
handlers are executed in a blocking manner to prevent potential race conditions.

.. tip::

    If you decide to run synchronous handlers in a non-blocking manner, make
    sure that the handlers do not share any data between each other or with
    other parts of the application. If they do, use locks or other
    synchronization mechanisms to avoid race conditions.

``subscribe_for_update`` and ``unsubscribe_from_update``
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~

The ``subscribe_for_update`` method of the ``ProductPage`` class is used to
subscribe to product update events. It takes the following arguments:

- ``handler``: A callable that will be executed when the event occurs.
- ``event``: The type of event to subscribe to. If event is ``None``,
  the handler will be executed for all events.
- ``call_safe``: A boolean flag that determines whether exceptions raised by
  the handler should be caught or propagated.
- ``call_blocking``: A boolean flag that determines whether *synchronous*
  handlers should be executed directly, blocking the event loop, or ran in a
  separate thread or process, allowing the event loop to continue running.
- ``handler_done_callback``: An optional synchronous function that will be
  executed when the handler has finished processing the event. It must accept
  a single argument - the completed future object of the handler.

.. code-block:: python

    page.subscribe_for_update(
        handler=on_product_update,
        event=ProductUpdateEvent.PRODUCT_UPDATED,
        handler_done_callback=lambda f: print('Product update handled\n.')
    )

In the code snippet above, the ``on_product_update`` handler is subscribed to
the ``PRODUCT_UPDATED`` event. The handler is asynchronous, so it will not block
the event loop, and setting ``call_blocking`` has no effect. ``call_safe`` is
set to ``True`` by default. A ``lambda`` function is used as the handler done
callback. It will print a message when the handler has finished processing the
event. Note that the handler done callback must be synchronous and accept
a single argument - the completed future object of the handler.

.. note::

    If a product update is eligible for multiple events, all handlers subscribed
    to these events will be executed. ``PRODUCT_UPDATED`` is a special generic
    event that is triggered for all types of product updates. For example, if a
    product's price has been updated, both ``PRODUCT_UPDATED`` and
    ``PRICE_UPDATED`` event handlers will be executed.

The ``unsubscribe_from_update`` method is used to unsubscribe a handler from
product update events. It takes the following arguments:

- ``handler``: The handler to be unsubscribed from the event(s).
  If ``None``, all handlers for the event are unsubscribed.

- ``event``: The type of product update event(s) to unsubscribe from.
  If ``None``, the handler will be unsubscribed from all events.

.. code-block:: python

    page.unsubscribe_from_update(
        handler=on_product_update,
        event=ProductUpdateEvent.PRODUCT_UPDATED
    )

In the code snippet above, the ``on_product_update`` handler is unsubscribed
from the ``PRODUCT_UPDATED`` event. The handler will no longer be executed when
a product update occurs.

Complete Example
----------------

The example below demonstrates how to subscribe to product updates and handle
them using custom handlers. The script will run continuously until interrupted
by the user. Note that it may take some time for a product update to occur on
the tracked page.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage, ProductUpdateEvent
    from freshpointsync.update import ProductUpdateContext

    async def on_product_update(context: ProductUpdateContext) -> None:
        """Handle all product update events."""
        if context.product_name in context.get('favorite_products', []):
            print(f'Your favorite product "{context.product_name}" was updated!')
        else:
            print(f'Product "{context.product_name}" was updated.')
        await asyncio.sleep(1)  # simulate a delay for some IO operation

    def on_product_price_update(context: ProductUpdateContext) -> None:
        """Handle all price update events."""
        price_curr = f'{context.product_new.price_curr:.2f} CZK'
        price_prev = f'{context.product_old.price_curr:.2f} CZK'
        print(
            f'Product "{context.product_name}" price update: '
            f'{price_prev} -> {price_curr}'
        )

    def on_product_quantity_update(context: ProductUpdateContext) -> None:
        """Handle all quantity update events."""
        quantity_curr = f'{context.product_new.quantity} items'
        quantity_prev = f'{context.product_old.quantity} items'
        print(
            f'Product "{context.product_name}" quantity update: '
            f'{quantity_prev} -> {quantity_curr}'
        )

    async def main():
        page = ProductPage(location_id=296)
        page.context['favorite_products'] = [
            'Harboe Cola',
            'Club Sendvič',
            'Dezert Tiramisu do kelímku',
        ]
        try:
            print('Fetching the initial product data...')
            await page.start_session()
            await page.update(silent=True)
            print('Subscribing to updates...')
            page.subscribe_for_update(
                handler=on_product_update,
                event=ProductUpdateEvent.PRODUCT_UPDATED,
                handler_done_callback=lambda _: print('Product update handled\n.')
            )
            page.subscribe_for_update(
                handler=on_product_price_update,
                event=ProductUpdateEvent.PRICE_UPDATED,
                call_blocking=False,
            )
            page.subscribe_for_update(
                handler=on_product_quantity_update,
                event=ProductUpdateEvent.QUANTITY_UPDATED,
                call_blocking=False
            )
            print('Subscribed to updates. Press Ctrl+C to exit.')
            await page.update_forever(interval=10)
        except asyncio.CancelledError:
            print('Exiting...')
        except Exception as e:
            print(f'Error: {e}')
        finally:
            await page.close_session()
            await page.await_update_handlers()

    if __name__ == "__main__":
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass

The example above demonstrates how to create a ``ProductPage`` instance, set
context data, subscribe to product update events, and handle these events using
custom handlers. The ``on_product_update`` handler is subscribed to the
``PRODUCT_UPDATED`` event and prints a message when a product update occurs.
It also has a one-second delay to simulate an IO operation and a bound callback
function. The ``on_product_price_update`` and ``on_product_quantity_update``
handlers are subscribed to the ``PRICE_UPDATED`` and ``QUANTITY_UPDATED``
events, respectively. They print specific information about the product price
and quantity updates. The application will run continuously until interrupted by
the user.