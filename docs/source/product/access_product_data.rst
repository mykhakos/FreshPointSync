=========================
Working with Product Data
=========================

The `Product` class is a Pydantic model. This means that it acts similar to
a data class, but it also provides validation and serialization capabilities.

We begin by creating a snapshot of a product's data, representing the state of
the product at a certain point in time.

.. note::

    In a real-world scenario, this snapshot would usually be obtained from
    the parsed product data from the website. We will learn how to create
    a `ProductPage` object and search for products on the product page later
    in the :doc:`../product_page/index` chapter. For this example, we create
    the `Product` object manually to have something to work with.

.. code-block:: python

    from freshpointsync import Product
    from time import time

    prod = Product(
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
        location_name='Elektroline',
        timestamp=time()
    )

The product above is a snapshot of the *Harboe Cola* beverage data. The quantity
of the product is 10 pieces. It is not listed as vegetarian or gluten free.
The product is located in the *Elektroline* location. The current price of
the product is 25.5 CZK, and the regular price is 30 CZK.

.. tip::

    Try to create a snapshot of a different product with different properties.
    Refer to `pydantic` documentation for more information on how to
    instantiate a model.

Reading Product Name, Category, and Location
--------------------------------------------
The name and the category of the product and the location where the product is
located can be accessed using the `name`, `category`, and `location` attributes,
respectively. These attributes contain the original data as provided by the
website. Additionally, the `name_lowercase_ascii`, `category_lowercase_ascii`,
and `location_lowercase_ascii` properties provide the lowercase ASCII versions
of the above attributes. This can be useful for case-insensitive and partial
comparison and searching.

.. code-block:: python

    print(f'Name: {prod.name}')
    print(f'Name (lowercase ASCII): {prod.name_lowercase_ascii}')

.. tip::

    Try to access the category of the product using the `category` attribute
    and the `category_lowercase_ascii` property.

Accessing Product Price
-----------------------
There are two `Product` attributes that represent the price of the product:
`price_curr` and `price_full`. `price_curr` represents the current price of
the product, while `price_full` represents its regular price. If the current
price of the product is less than its regular price, the product is considered
to be on sale. The `is_on_sale` property can be used to determine this.
The rate of the discount can be obtained from the `discount_rate` property.
Typically, the current price should not be greater than the regular price.

.. code-block:: python

    print(f'Current price: {prod.price_curr} CZK')
    print(f'Regular price: {prod.price_full} CZK')

Accessing Product Quantity
--------------------------
The `quantity` attribute represents the quantity of the product in stock.
If the quantity is zero, the product is considered to be out of stock. This
information is available in the `is_sold_out` and `is_available` properties.

.. code-block:: python

    print(f'Quantity in stock: {prod.quantity} pieces')

.. note::

    Product `attributes` are the data fields that are part of the model's
    schema, such as `name`, `price_curr`, `quantity`, etc. These attributes
    are provided as arguments when creating the `Product` object. They are
    read-write and can be accessed and modified directly. On the other hand,
    product `properties`, such as `name_lowercase_ascii`, `is_on_sale`,
    `is_sold_out`, etc., are simple convenience wrappers around the regular
    attributes. They are read-only values that are calculated on-the-fly.
    They are not part of the model's schema.

Complete Example
----------------

.. code-block:: python

    from freshpointsync import Product
    from time import time

    prod = Product(
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
        timestamp=time()
    )

    print(f'Name: {prod.name}')
    print(f'Name (lowercase ASCII): {prod.name_lowercase_ascii}')
    print(f'Current price: {prod.price_curr} CZK')
    print(f'Regular price: {prod.price_full} CZK')
    print(f'Quantity in stock: {prod.quantity} pieces')
