Serializing Product Snapshots
=============================

As mentioned previously, product snapshots, being Pydantic models, can be easily
serialized and deserialized. This is useful for storing snapshots in a database,
or for sending them over the network.

Serializing a Product Snapshot
------------------------------

To serialize a snapshot, you can use the ``model_dump`` and ``model_dump_json``
methods of the ``Product`` class.

Let's reuse the ``product`` object we created in the previous section:

.. code-block:: python

    from freshpointsync import Product

    product = Product(
        id_=99,
        name='Pappudio Croissant sýrový',
        category='Sendviče, wrapy, tortilly, bagety',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=4,
        price_curr=40.26,
        price_full=57.52,
        pic_url='',  # omitted for brevity
        location_id=296,
        location='Elektroline',
    )

To serialize the snapshot to a JSON string, you can use the ``model_dump_json``
method:

.. code-block:: python

    product_ser = product.model_dump_json(
        indent=4,              # 4 spaces indentation in the JSON output
        by_alias=True,         # use camelCase field names
        exclude={'timestamp'}  # exclude the 'timestamp' field
        )
    print(product_ser)

This will output the following JSON string:

.. code-block:: json

    {
        "id": 99,
        "name": "Pappudio Croissant sýrový",
        "category": "Sendviče, wrapy, tortilly, bagety",
        "isVegetarian": true,
        "isGlutenFree": false,
        "quantity": 4,
        "priceCurr": 40.26,
        "priceFull": 57.52,
        "picUrl": "",
        "locationId": 296,
        "location": "Elektroline"
    }

The indentation is set to 4 spaces, the ``timestamp`` field is excluded from the
output, and other field names are converted to camelCase. The latter is because
the ``Product`` model is configured to use camelCase field name aliases. If you
want to use the original field names, you can set the ``by_alias`` parameter to
``False``. Note that the model can be instantiated with the field names in any
of the two cases.

Deserializing a Product Snapshot
--------------------------------

To deserialize a snapshot from a dictionary or a JSON string, you can use the
``model_validate`` and ``model_validate_json`` methods of the ``Product`` class,
respectively.

Let's create a ``Product`` object from the JSON string we serialized in the
previous section:

.. code-block:: python

    product_deser = Product.model_validate_json(product_ser)
    print(repr(product_deser))

The product snapshot is now restored. We can verify that, excluding the
``timestamp`` field, the deserialized object is equal to the original object:

.. code-block:: python

    assert not product.diff(other=product_deser, exclude={'timestamp'})

.. tip::

    Refer to the ``pydantic`` documentation for more information on the
    serialization and deserialization of Pydantic models.


Complete Example
----------------

.. code-block:: python

    from freshpointsync import Product

    # create a product snapshot
    product = Product(
        id_=99,
        name='Pappudio Croissant sýrový',
        category='Sendviče, wrapy, tortilly, bagety',
        is_vegetarian=True,
        is_gluten_free=False,
        quantity=4,
        price_curr=40.26,
        price_full=57.52,
        pic_url='',  # omitted for brevity
        location_id=296,
        location='Elektroline'
    )

    # serialize the snapshot to a JSON string
    product_ser = product.model_dump_json(
        indent=4, by_alias=True, exclude={'timestamp'}
        )
    print(product_ser)

    # deserialize the snapshot from the JSON string
    product_deser = Product.model_validate_json(product_ser)
    print(repr(product_deser))

    # verify that the deserialized object is equal to the original object
    assert not product.diff(other=product_deser, exclude={'timestamp'})

