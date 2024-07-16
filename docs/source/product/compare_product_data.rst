===========================
Comparing Product Snapshots
===========================

Product listings can change frequently due to price adjustments, stock updates,
or other modifications. You can track these changes by comparing ``Product``
snapshots of the same product at different points in time.

We start with two snapshots of the same product taken at different times.

.. code-block:: python

    from time import time
    from freshpointsync import Product

    # create the previous product snapshot (10 seconds ago)
    product_prev = Product(
        id_=99,
        name='Pappudio Croissant sýrový',
        category='Sendviče, wrapy, tortilly, bagety',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=4,
        price_curr=40.26,
        price_full=57.52,
        info='Obsah balení: 140g',  # shortened for brevity
        pic_url='',  # omitted for brevity
        location_id=296,
        location='Elektroline',
        timestamp=time() - 10  # timestamp ten seconds ago
    )

    # create the current product snapshot (current time)
    product_curr = Product(
        id_=99,
        name='Pappudio Croissant sýrový',
        category='Sendviče, wrapy, tortilly, bagety',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=0,
        price_curr=57.52,
        price_full=57.52,
        info='Obsah balení: 140g',  # shortened for brevity
        pic_url='',  # omitted for brevity
        location_id=296,
        location='Elektroline',
        timestamp=time()  # timestamp ten seconds ago
    )

In this example, we create two snapshots of the "Pappudio Croissant sýrový"
product. The previous snapshot has a quantity of 4 pieces and is on sale for
40.26 CZK, while the current snapshot is out of stock and costs 57.52 CZK.
The product ID, name, category, info, and location remain the same.

Comparing Product Timestamps
----------------------------
We can validate that the current product snapshot is newer than the previous
snapshot by comparing their timestamps using the ``is_newer_than`` method.

.. code-block:: python

    print(
        f'Product with timestamp: {product_curr.timestamp} is newer than '
        f'the previous product with timestamp: {product_prev.timestamp}: '
        f'{product_curr.is_newer_than(product_prev)}',
    )

Comparing Product Price
-----------------------
We can compare the prices of the two product snapshots to determine the direct
price change as well as gain comprehensive insights into the sale status of the
product. This information is available through the ``ProductPriceUpdateInfo``
object, which is returned by the ``compare_price`` method.

.. code-block:: python

    price_info = product_prev.compare_price(new=product_curr)
    print(
        f'Current price increase: {price_info.price_curr_increase:.2f} CZK\n'
        f'Sale ended: {price_info.sale_ended}'
    )

In this example, the current price of the product has increased by 17.26 CZK,
and the product is no longer on sale.

Comparing Product Quantity
--------------------------
We can analyze the stock changes with the ``ProductQuantityUpdateInfo`` object,
which is returned by the ``compare_quantity`` method. It provides information on
whether the product quantity has decreased, if the product is out of stock, etc.

.. code-block:: python

    quantity_info = product_prev.compare_quantity(new=product_curr)
    print(
        f'Quantity decrease: {quantity_info.stock_decrease} pieces\n'
        f'Is out of stock: {quantity_info.stock_depleted}'
    )

In this example, the quantity of the product has decreased by 4 pieces, and
the product is now out of stock.

Getting Full Product Diffence
-----------------------------
You can get the full product difference by calling the ``diff`` method of the
``Product`` class. This method compares the fields of this product with the
fields of another product instance to identify which fields differ between them.

.. code-block:: python

    diff = product_prev.diff(product_curr, exclude={'timestamp'})
    for field, diff_value in diff.items():
        print(f'{field}: {diff_value.value_self} -> {diff_value.value_other}')

Each key in the dictionary a string representing an attribute name, and the
value is a named tuple containing the differing values between the two products.
The named tuple has two fields: ``value_self`` and ``value_other``, which
represent the value of the attribute in the first and second product,
respectively.

.. tip::

    You can alter the returned dictionary by providing optional keyword
    arguments to the ``diff`` method. It accepts any arguments that the standard
    Pydantic ``model_dump`` method accepts. You can thus include and exclude
    certain fields from the comparison, pick the key format, and more.

Complete Example
----------------

.. code-block:: python

    from freshpointsync import Product
    from time import time

    # create the previous product snapshot (10 seconds ago)
    product_prev = Product(
        id_=99,
        name='Pappudio Croissant sýrový',
        category='Sendviče, wrapy, tortilly, bagety',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=4,
        price_curr=40.26,
        price_full=57.52,
        info='Obsah balení: 140g',  # shortened for brevity
        pic_url='',  # omitted for brevity
        location_id=296,
        location='Elektroline',
        timestamp=time() - 10  # timestamp ten seconds ago
    )

    # create the current product snapshot (current time)
    product_curr = Product(
        id_=99,
        name='Pappudio Croissant sýrový',
        category='Sendviče, wrapy, tortilly, bagety',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=0,
        price_curr=57.52,
        price_full=57.52,
        info='Obsah balení: 140g',  # shortened for brevity
        pic_url='',  # omitted for brevity
        location_id=296,
        location='Elektroline',
        timestamp=time()  # timestamp ten seconds ago
    )

    print(
        f'Product with timestamp: {product_curr.timestamp} is newer than '
        f'the previous product with timestamp: {product_prev.timestamp}: '
        f'{product_curr.is_newer_than(product_prev)}',
    )

    price_info = product_prev.compare_price(new=product_curr)
    print(
        f'Current price increase: {price_info.price_curr_increase:.2f} CZK\n'
        f'Sale ended: {price_info.sale_ended}'
    )

    quantity_info = product_prev.compare_quantity(new=product_curr)
    print(
        f'Quantity decrease: {quantity_info.stock_decrease} pieces\n'
        f'Is out of stock: {quantity_info.stock_depleted}'
    )

    diff = product_prev.diff(product_curr, exclude={'timestamp'})
    for field, diff_value in diff.items():
        print(f'{field}: {diff_value.value_self} -> {diff_value.value_other}')

