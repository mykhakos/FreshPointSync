================
Finding Products
================

There are two methods available for searching for products on a ``ProductPage``
instance: ``find_product`` and ``find_products``. The ``find_product`` method
returns the first product that matches the specified criteria, or ``None`` if
no product is found. The ``find_products`` method returns a list of all products
that match the specified criteria. Both methods match products based on their
attributes and properties as well as custom constraints.

First, create a new ``ProductPage`` instance for a specific location and update
the product listings. Learn more about creating ``ProductPage`` instances in
the :doc:`init_product_page` example.

.. code-block:: python

    from freshpointsync import ProductPage

    async def main():
        async with ProductPage(location_id=296) as page:
            await page.update_silently()

Searching using Attributes and Properties
-----------------------------------------

Searching for a product with its attributes and properties is straightforward.
For example, to search for a product by its name, use the ``name`` attribute:

.. code-block:: python

    cola = page.find_product(name='Harboe Cola')
    if cola is None:
        print('Harboe Cola not found.')
    else:
        print(f'Harboe Cola quantity is {cola.quantity}.')

This code searches for a product named "Harboe Cola" and prints its quantity if
the product is found.

Or if, for example, you want to find all desserts that are currently available,
you can use the ``category`` attribute and the ``is_available`` property:

.. code-block:: python

    desserts = page.find_products(category='Dezerty', is_available=True)
    print(f'{len(desserts)} desserts are currently available.')

This code searches for all products in the "Dezerty" category that are currently
available and prints the number of products found.

.. warning::

    Matching ``Product`` attributes and properties requires an exact match.
    This means that the search is case-sensitive and diacritics-sensitive.
    For example, searching for ``name='harboe cola'`` or ``name='Cola'``
    will not match a product named "Harboe Cola".

Searching using Custom Constraints
----------------------------------

In case your search query is more complex, you can pass a ``callable`` object
to the ``constraint`` parameter of any of the search methods. The callable
object should accept a single argument, which is a ``Product`` instance, and
return a boolean value indicating whether the product matches the criteria.

One common use case is to search for a product based on a part of its name:

.. code-block:: python

    products = page.find_products(
        constraint=lambda product: 'cola' in product.name_lowercase_ascii
    )
    print(f'{len(products)} products contain "cola" in their name.')

This code implements a ``lambda`` function that searches for all products that
contain the word "cola" in their name and prints the number of products found.
Such an approach allows for a case-insensitive search that ignores diacritics
and matches partial words.

.. tip::

    While using ``lambda`` functions is a common approach, you can also define
    a regular function and pass it to the ``constraint`` parameter. The only
    requirement is that the function should accept a single argument and return
    a boolean value.

Combining Multiple Criteria
---------------------------

It is possible to combine multiple criteria in a single search query. Study the
following code snippet:

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

In the example above, the code searches for products, the category of which
contains the word "sendvice", that are available, and cost less than 100 CZK.

Complete Example
----------------

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    async def main():
        async with ProductPage(location_id=296) as page:
            await page.update_silently()

            cola = page.find_product(name='Harboe Cola')
            if cola is None:
                print('Harboe Cola not found.')
            else:
                print(f'Harboe Cola quantity is {cola.quantity}.')

            desserts = page.find_products(category='Dezerty', is_available=True)
            print(f'{len(desserts)} desserts are currently available.')

            products = page.find_products(
                constraint=lambda product: 'cola' in product.name_lowercase_ascii
            )
            print(f'{len(products)} products contain "cola" in their name.')

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

    if __name__ == '__main__':
        asyncio.run(main())
