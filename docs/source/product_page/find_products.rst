==================================
Finding Products on a Product Page
==================================

Products on a product page can be searched for using the ``find_product`` and
``find_products`` methods of the ``ProductPage`` class. These methods allow
you to filter products based on their attributes, properties, and custom
constraints.

The two methods differ in the number of products they return. ``find_product``
returns the first product that matches the specified criteria, or ``None`` if
no product is found. ``find_products`` returns a list of all products that match
the specified criteria.

Assuming we have a ``ProductPage`` instance named ``page``, let's explore how
to search for products using the ``find_product`` and ``find_products`` methods.

Searching Using Attributes and Properties
-----------------------------------------

Searching for a product with its attributes and properties is straightforward.
You can specify the attributes and properties you want to search for as keyword
arguments in the method call.

For example, to search for a product by its name, specify the ``name`` argument
in a ``find_product`` method call:

.. code-block:: python

    cola = page.find_product(name='Harboe Cola')
    if cola is None:
        print('Harboe Cola not found.')
    else:
        print(f'Harboe Cola quantity is {cola.quantity}.')

This code snippet searches for a product named "Harboe Cola" and prints its
quantity if the product is found.

Or if, for example, you want to find all desserts that are currently available,
you can specify the ``category`` and the ``is_available`` arguments
simultaneously in a single call to the ``find_products`` method:

.. code-block:: python

    desserts = page.find_products(category='Dezerty, snídaně', is_available=True)
    print(f'{len(desserts)} desserts are currently available.')

This code snippet searches for all products in the "Dezerty, snídaně" category
with  quantity greater than zero and prints the number of products found.

.. warning::

    Matching ``Product`` attributes and properties requires an exact match.
    This means that the search is case-sensitive and diacritics-sensitive.
    For example, searching for ``name='harboe cola'`` or ``name='Cola'``
    will not match a product named "Harboe Cola".

Complete Example
~~~~~~~~~~~~~~~~

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    async def main():
        async with ProductPage(location_id=296) as page:
            await page.update(silent=True)

            cola = page.find_product(name='Harboe Cola')
            if cola is None:
                print('Harboe Cola not found.')
            else:
                print(f'Harboe Cola quantity is {cola.quantity}.')

            desserts = page.find_products(
                category='Dezerty, snídaně', is_available=True
                )
            print(f'{len(desserts)} desserts are currently available.')

    if __name__ == '__main__':
        asyncio.run(main())

Searching using Custom Constraints
----------------------------------

In case your search query is more complex, you can pass a callable object to
the ``constraint`` parameter of any of the search methods. The callable
object should accept a single argument, which is a ``Product`` instance, and
return a boolean value indicating whether the product matches the criteria.

.. code-block:: python

    products = page.find_products(
        constraint=lambda product: (
            'sendvice' in product.category_lowercase_ascii and
            product.is_available and
            product.price_curr < 100
        )
    )
    if products:
        print('Sendvices available for less than 100 CZK:')
        for product in products:
            print(f'- {product.name} ({product.price_curr} CZK)')
    else:
        print('No sendvices available for less than 100 CZK.')

In the example above, a ``lambda`` function is used to search for all products,
the category of which contains the word "sendvice" that are available and cost
less than 100 CZK. The matching is case-insensitive and ignores diacritics.

.. tip::

    While using ``lambda`` functions is a common approach, you can also define
    a regular function and pass it to the ``constraint`` parameter. The only
    requirement is that the function should accept a single argument and return
    a boolean value.

Complete Example
~~~~~~~~~~~~~~~~

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    async def main():
        async with ProductPage(location_id=296) as page:
            await page.update(silent=True)

            products = page.find_products(
                constraint=lambda product: (
                    'sendvice' in product.category_lowercase_ascii and
                    product.is_available and
                    product.price_curr < 100
                )
            )
            if products:
                print('Sendvices available for less than 100 CZK:')
                for product in products:
                    print(f'- {product.name} ({product.price_curr} CZK)')
            else:
                print('No sendvices are available for less than 100 CZK.')

    if __name__ == '__main__':
        asyncio.run(main())

Case Study: Creating a Simple REPL Application
----------------------------------------------

Let's create a simple REPL application that finds a product by its name and
prints its availability.

.. code-block:: python

    import asyncio
    import time
    from freshpointsync import ProductPage

    LOCATION_ID = 296

    def print_product_info(page: ProductPage, product_name: str) -> None:
        product = page.find_product(
            constraint=lambda p: product_name.casefold() in p.name_lowercase_ascii
            )  # case-insensitive search for a partial match
        if product:
            print(f'Product "{product.name}" quantity: {product.quantity} pcs.')
        else:
            print(f'Product "{product_name}" not found on the page.')

    def get_user_input() -> str:
        return input('Enter product name (or "exit" to quit): ')

    async def prompt_forever(page: ProductPage, max_update_interval: float) -> None:
        await page.update(silent=True)
        timer = time.time()
        while True:
            product_name = get_user_input()
            if product_name == 'exit':
                break
            if time.time() - timer > max_update_interval:
                await page.update(silent=True)
                timer = time.time()
            print_product_info(page, product_name)

    async def main() -> None:
        page = ProductPage(location_id=LOCATION_ID)
        try:
            await page.start_session()
        except Exception as e:
            print(f'An error occurred while starting the session: {e}')
            return
        try:
            await prompt_forever(page, max_update_interval=10.0)
        except EOFError:
            print()  # print '\n' to handle Ctrl+C with no input (EOF)
        except Exception as e:
            print(f'An unexpected error occurred: {e}')
        finally:
            print('Exiting...')
            await page.close_session()

    if __name__ == '__main__':
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            pass

In the example above, a ``ProductPage`` instance is created in the ``main``
function. The session is started and the initial data is fetched. The script
then enters an infinite loop under a ``try-finally`` block. The loop prompts
the user for a product name and prints the product quantity. The session is
closed when the user exits the loop.
