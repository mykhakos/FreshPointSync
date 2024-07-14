==============================
Managing Product Page Sessions
==============================

The ``ProductPage`` class acts as a high-level client for interacting with
a product page. There are several ways to create and manage ``ProductPage``
instances, depending on the use case.

Creating Product Pages
----------------------

Instantiating ``ProductPage`` does not automatically establish a client session.
The session is started and closed explicitly using the ``start_session`` and
``close_session`` methods, respectively. The page data is fetched using
the ``update`` method.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    LOCATION_ID = 296

    async def main() -> None:
        page = ProductPage(location_id=LOCATION_ID)
        try:
            await page.start_session()
            print(f'Fetching data for location ID {page.data.location_id}...')
            await page.update()
            print(f'Location Name: {page.data.location}')
        finally:
            await page.close_session()

    if __name__ == '__main__':
        asyncio.run(main())

In the example above, a new ``ProductPage`` instance is created with the
location ID 296. The session is started, the page data is fetched, and the
location name is printed. Lastly, the session is closed in the ``finally``
block to ensure the disconnect.

.. note::

    If you specify a non-existent location ID, the page data will remain empty
    after the update.

Leveraging the Asynchronous Context Manager
-------------------------------------------

``ProductPage`` implements the asynchronous context manager protocol. This
means that you can use the ``async with`` statement to manage the session
lifecycle automatically, without the need to call ``start_session`` and
``close_session`` explicitly or use the ``try-finally`` block.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    LOCATION_ID = 296

    async def main() -> None:
        async with ProductPage(location_id=LOCATION_ID) as page:
            print(f'Fetching data for location ID {page.data.location_id}...')
            await page.update()
            print(f'Location Name: {page.data.location}')

    if __name__ == '__main__':
        asyncio.run(main())

The example above is equivalent to the previous one. The ``ProductPage``
instance is created, the session is started, the page data is fetched, and the
location name is printed. The session is closed automatically when the context
manager exits.

.. tip::

    Opting for manual session management or using the context manager depends on
    the use case and the desired level of control over the object lifecycle.

    While the ``async with`` statement is more concise and convenient for
    simple one-time use cases, manual session management may be more suitable
    in more complex scenarios, such as when you need to reuse the object
    multiple times or store it as a class attribute.

Serializing Page Data
---------------------
The product page data is represented by a ``ProductPageData`` object, which is
a Pydantic model. It is stored in the ``data`` attribute of the ``ProductPage``
instance. The page data is empty upon initialization and is updated when
an update method is called. However, you can provide the initial data for this
attribute when creating a new page instance by passing a ``ProductPageData``
object to the ``data`` parameter of the ``ProductPage`` constructor. It is also
possible to serialize the data and store it between application sessions.

.. note::

    Pydantic models allow to include and exclude fields from serialization by
    providing the ``include`` and ``exclude`` parameters to the ``model_dump``
    and ``model_dump_json`` methods. By default, all fields are included.

    But what if you want to include or exclude specific fields of a nested
    model? For example, The ``products`` field of the ``ProductPageData`` model
    is a dictionary of product IDs and ``Product`` models. If you want to
    exclude the ``info`` and ``pic_url`` fields of every ``Product`` model in
    that dictionary, you can use the following syntax:

    .. code-block:: python

        data = page.data.model_dump(
            exclude={'products': {'__all__': {'info',  'pic_url'}}}
        )

Let's implement a script that periodically fetches the page data and prints
if the page has changed since the last update to demonstrate the serialization
and deserialization of the page data.

.. code-block:: python

    import asyncio
    from pathlib import Path
    from freshpointsync import ProductPage, ProductPageData

    LOCATION_ID = 296
    CACHE_FILENAME = f'pageData_{LOCATION_ID}.json'

    def load_from_file(file_path: str) -> ProductPageData:
        print(f"Loading data from cache file '{file_path}'...")
        with open(file_path, 'r', encoding='utf-8') as f:
            return ProductPageData.model_validate_json(f.read())

    def dump_to_file(data: ProductPageData, file_path: str) -> None:
        print(f"Dumping data to cache file '{file_path}'...")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data.model_dump_json(indent=4, by_alias=True))

    async def main() -> None:
        cache_file = Path(CACHE_FILENAME)
        if cache_file.exists():
            data = load_from_file(CACHE_FILENAME)
            async with ProductPage(data=data) as page:
                print(f'Updating data for location ID {page.data.location_id}...')
                await page.update()
                if page.data.html_hash != data.html_hash:
                    print('Product page has changed since the last update.')
                else:
                    print('Product page has not changed since the last update.')
                dump_to_file(page.data, CACHE_FILENAME)
        else:
            async with ProductPage(location_id=LOCATION_ID) as page:
                print(f'Fetching data for location ID {page.data.location_id}...')
                await page.update()
                dump_to_file(page.data, CACHE_FILENAME)
            print('[tip] Run the script again to check for updates.')

    if __name__ == '__main__':
        asyncio.run(main())

In the example above, a ``ProductPageData`` object for location ID 296 is
created from the serialized data stored in a cache file ``pageData_296.json``.
A new ``ProductPage`` instance is created with this data. The page data is then
updated, and the script prints whether the page has changed since the last
update based on the value of MD5 hash of the page HTML contents. Finally,
the updated data is serialized and stored back to the file.

.. tip::
    It is possible to create an empty ``ProductPageData`` object. The only
    required field is the ``location_id``. Instantiating a ``ProductPage`` with
    this object would be equivalent to directly passing the location ID to the
    constructor.