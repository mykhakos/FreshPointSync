====================================
Subscribing to Product Pages Updates
====================================

The ``ProductPageHub`` class update and subscription logic is consistent with
the ``ProductPage`` class. The main difference is that the hub manages multiple
product pages simultaneously and performs bulk operations. The logic is thus
covered here just briefly. For a detailed explanation, please refer to
:ref:`Subscribing to Product Page Updates <product-page-subscribing-to-product-page-updates>`.

Update and Subscription Logic
-----------------------------

``ProductPageHub`` provides the ``update``, ``update_silently``,
``update_forever``, and ``init_update_task`` methods to fetch and update data
for all managed product pages. Similarly, subscription to product updates
is handled using the ``subscribe_for_update`` method.

.. note::

    The ``ProductPageHub`` class does not provide the ``fetch`` method. To fetch
    page data without updating it, access the page directly using the hub's
    ``pages`` attribute. You can invoke other page methods directly, too.

Managing the Update Context
---------------------------

``ProductPageHub`` allows you to set and delete context key-value pairs for all
managed pages using the ``set_context`` and ``del_context`` methods,
respectively. This ensures that context data is consistently applied across all
pages managed by the hub.

Setting Context
~~~~~~~~~~~~~~~

Use the ``set_context`` method to add context data that will be accessible to
all product pages in the hub.

.. code-block:: python

    hub.set_context('key', 'value')

Deleting Context
~~~~~~~~~~~~~~~~

Use the ``del_context`` method to remove context data from all product pages in
the hub.

.. code-block:: python

    hub.del_context('key')

.. note::

    ``del_context`` does not raise an error if the key does not exist in the
    context.

Complete Example
----------------

Below is an example demonstrating how to use the ``ProductPageHub`` to manage
multiple product pages, subscribe to updates, and handle them using custom
handlers.

.. code-block:: python

    async def on_product_update(context: ProductUpdateContext) -> None:
        """Handle all product update events."""
        if not context.product_new or not context.product_old:
            raise ValueError('Product data is missing!')
        if context.product_name in context.get('favorite_products', []):
            text_product = f'Your favorite product "{context.product_name}"'
        else:
            text_product = f'Product "{context.product_name}"'
        text_timestamp = datetime.fromtimestamp(context.product_new.timestamp)
        diff = context.product_old.diff(context.product_new, exclude={'timestamp'})
        text_diff = 'Product changes:\n' + '\n'.join(
            f'- {key}: {value.value_self} -> {value.value_other}'
            for key, value in diff.items()
        )
        print(
            f'[{text_timestamp}]\n{text_product} was updated at location '
            f'"{context.location}" (ID: {context.location_id})!\n{text_diff}\n'
        )

    async def main() -> None:

        total_updates = 0

        def callback_update_total_updates(fut) -> None:
            nonlocal total_updates
            total_updates += 1

        time_start = datetime.now()
        hub = ProductPageHub(enable_multiprocessing=True)
        hub.set_context(
            'favorite_products',
            [
                'Harboe Cola',
                'Club Sendvič',
                'Dezert Tiramisu do kelímku',
            ]
        )
        try:
            print('Fetching the initial product data...')
            await hub.start_session()
            await hub.scan(stop=600)
            print('Subscribing to updates...')
            time_start = datetime.now()
            hub.subscribe_for_update(
                handler=on_product_update,
                event=ProductUpdateEvent.PRODUCT_UPDATED,
                handler_done_callback=callback_update_total_updates,
            )
            print('Subscribed to updates. Press Ctrl+C to exit.')
            await hub.update_forever(interval=10)
        except asyncio.CancelledError:
            print('Exiting...')
        except Exception as e:
            print(f'Error: {e}')
        finally:
            print(
                f'Total number of updates from {time_start} to {datetime.now()}: '
                f'{total_updates}.'
                )
            await hub.close_session()
            await hub.await_update_handlers()

    if __name__ == "__main__":
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass

The example above demonstrates how to create a ``ProductPageHub``, set context
data, subscribe to product update events, and handle these events using a custom
handler. The handler prints the time of the update, the product name, the
location, and the changes made to the product. The application will run
continuously until interrupted by the user. The total number of updates is
printed when the application exits.

.. note::

    Every update operation means so many HTTP requests to the server how many
    product pages are managed by the hub. Make sure to set a reasonable update
    interval to avoid overloading the server.
