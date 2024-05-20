===========================
Comparing Product Snapshots
===========================

This chapter demonstrates how to monitor changes in product data over time using
the ``Product`` class. By comparing snapshots of a product at different points
in time, you can analyze changes such as price and quantity updates. This will
help you understand how the ``Product`` class can be used to track and manage
product information effectively.

We start with two snapshots of the same product taken at different times.

.. code-block:: python

    from freshpointsync import Product
    from time import time

    # create the previous product snapshot (10 seconds ago)
    prod_prev = Product(
        id_=195,
        name='Harboe Cola',
        category='Nápoje',
        is_vegetarian=False,
        is_gluten_free=False,
        quantity=10,
        price_curr=25.5,
        price_full=30,
        pic_url='',
        location_id=296,
        location='Elektroline',
        timestamp=time() - 10  # timestamp ten seconds ago
    )

    # create the current product snapshot (current time)
    prod_curr = Product(
        id_=195,
        name='Harboe Cola',
        category='Nápoje',
        is_vegetarian=False,
        is_gluten_free=False,
        quantity=5,
        price_curr=30,
        price_full=30,
        pic_url='',
        location_id=296,
        location='Elektroline',
        timestamp=time()  # current timestamp
    )

In this example, the previous snapshot of the *Harboe Cola* beverage has
a quantity of 10 and is on sale for 25.5 CZK, while the current snapshot has
a quantity of 5 and costs 30 CZK. The product ID, name, category, and location
remain the same.

Comparing Product Timestamps
----------------------------
We can validate that the current product snapshot is newer than the previous
snapshot by comparing their timestamps using the ``is_newer_than`` method.

.. code-block:: python

    print(
        f'Product with timestamp: {prod_curr.timestamp} is newer than '
        f'the previous product with timestamp: {prod_prev.timestamp}: '
        f'{prod_curr.is_newer_than(prod_prev)}',
    )

Comparing Product Price
-----------------------
Directly comparing current prices of the two product snapshots might be
sufficient in some cases. However, more comprehensive insights can be gained,
such as whether the product has just gone on sale or if the sale rate has
changed. This information is available through the ``ProductPriceUpdateInfo``
object, which is returned by the ``compare_price`` method.

.. code-block:: python

    price_info = prod_prev.compare_price(new=prod_curr)
    print(
        f'Current price increase: {price_info.price_curr_increase} CZK\n'
        f'Sale ended: {price_info.sale_ended}'
    )

In this example, the current price of the product has increased by 4.5 CZK, and
the product is no longer on sale.

Comparing Product Quantity
--------------------------
We can also compare the stock count of the two product snapshots. Analyzing
the quantity changes with the `ProductQuantityUpdateInfo` object, which
is returned by the `compare_quantity` method, provides insights such as whether
the product has been restocked or is out of stock.

.. code-block:: python

    quantity_info = prod_prev.compare_quantity(new=prod_curr)
    print(
        f'Quantity decrease: {quantity_info.stock_decrease} pieces\n'
        f'Is out of stock: {quantity_info.stock_depleted}'
    )

In this example, the quantity of the product has decreased by 5 pieces, but
the product is not out of stock.

Complete Example
----------------

.. code-block:: python

    from freshpointsync import Product
    from time import time

    # create the previous product snapshot (10 seconds ago)
    prod_prev = Product(
        id_=195,
        name='Harboe Cola',
        category='Nápoje',
        is_vegetarian=False,
        is_gluten_free=False,
        quantity=10,
        price_curr=25.5,
        price_full=30,
        pic_url='',
        location_id=296,
        location='Elektroline',
        timestamp=time() - 10  # timestamp ten seconds ago
    )

    # create the current product snapshot (current time)
    prod_curr = Product(
        id_=195,
        name='Harboe Cola',
        category='Nápoje',
        is_vegetarian=False,
        is_gluten_free=False,
        quantity=5,
        price_curr=30,
        price_full=30,
        pic_url='',
        location_id=296,
        location='Elektroline',
        timestamp=time()  # current timestamp
    )

    # check if the current snapshot is newer
    print(
        f'Product with timestamp "{prod_curr.timestamp}" is newer than '
        f'the previous product with timestamp "{prod_prev.timestamp}": '
        f'{prod_curr.is_newer_than(prod_prev)}',
    )

    # check if the product is on sale
    print(f'Product "{prod_curr.name}" is on sale: {prod_curr.is_on_sale}')

    # compare prices
    price_info = prod_prev.compare_price(new=prod_curr)
    print(
        f'Current price increase: {price_info.price_curr_increase} CZK\n'
        f'Sale ended: {price_info.sale_ended}'
    )

    # compare quantities
    quantity_info = prod_prev.compare_quantity(new=prod_curr)
    print(
        f'Quantity decrease: {quantity_info.stock_decrease} pieces\n'
        f'Is out of stock: {quantity_info.stock_depleted}'
    )
