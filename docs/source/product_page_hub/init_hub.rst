==========================
Managing Product Page Hubs
==========================

API of the ``ProductPageHub`` is similar to the one of the ``ProductPage`` class.
It can be used as an asynchronous context manager, provides methods for updating
pages, subscribing to events in bulk, and data serialization.

Creating Product Page Hubs
--------------------------

Instantiating ``ProductPageHub`` does not automatically establish a client
session. The session management and data updates are explicitly handled through
provided methods.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPageHub

    async def main() -> None:
        print('Initializing hub session...')
        hub = ProductPageHub()
        try:
            await hub.start_session()
            print('Adding pages to the hub...')
            await hub.new_page(location_id=296)
        finally:
            print('Closing hub session...')
            await hub.close_session()

    if __name__ == '__main__':
        asyncio.run(main())

In the example above, a new ``ProductPageHub`` instance is created. The session
is started manually, and the page with ID 296 is added. Lastly, the session is
closed in the ``finally`` block to ensure proper cleanup.

The same can be achieved using the asynchronous context manager.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPageHub

    async def main() -> None:
        print('Initializing hub session...')
        async with ProductPageHub() as hub:
            await hub.start_session()
            print('Adding pages to the hub...')
            await hub.new_page(location_id=296)

    if __name__ == '__main__':
        asyncio.run(main())

The example above is equivalent to the previous one. The client session is
automatically created and subsequently closed when the context manager exits.

Registering Pages in the Hub
----------------------------

The hub can be populated with product pages. Once a page is added to the hub,
it receives a common client session and task runner. It is also subscribed to
the hub's events, and its ``context`` is populated with a common top-level
``hub`` context data.

.. note::
    If a certain key is present in both the hub and page context, the hub's
    value takes precedence and overwrites the page's value.

Creating New Pages
~~~~~~~~~~~~~~~~~~

A straightforward way to add a new page to the hub is by using the ``new_page``
method.

.. code-block:: python

    await hub.new_page(
        location_id=296,
        fetch_contents=True,
        trigger_handlers=False,
    )

The example above adds a new page with ID 296 to the hub. The page data is
automatically fetched. The common registered event handlers are not triggered.

Adding Existing Pages
---------------------

An existing page can be added to the hub by using the ``add_page`` method.

.. code-block:: python

    # ... assuming the page is already created

    await hub.add_page(
        page=page,
        update_contents = False,
        trigger_handlers = False,
    )

The example above adds an existing page to the hub. The page data is not
automatically updated. The common registered event handlers are not triggered.

Scanning for Pages
------------------

The hub can automatically search for pages within a specified location ID range.
The ``scan`` method is used for this purpose. The signature of the method is
similar to the built-in ``range`` function. However, the ``stop`` parameter is
inclusive.

.. code-block:: python

    await hub.scan(start=10, stop=20, step=2)

The example above scans for pages with IDs from 10 to 20. The step parameter
specifies the increment value between the IDs.

.. note::
    The ``scan`` method execution depends on the ID range and the chosen
    processing strategy. The larger the range, the longer the execution time.
    Scanning for a default range of 1 to 1000 with a step of 1 may take up to
    12 minutes.

Accessing Pages
---------------

The pages in the hub can be accessed using the ``pages`` attribute. This
attribute is a dictionary where the keys are the page IDs, and the values are
the corresponding page objects.

.. code-block:: python

    page = hub.pages.get(296)

The example above retrieves the page with ID 296 from the hub.

Removing Pages
--------------
A page can be removed from the hub by using the ``remove_page`` method.
A removed page receives a new client without an initialized session.

.. code-block:: python

    await hub.remove_page(page_id=296)

The example above removes the page with ID 296 from the hub.

Serializing Hub Data
--------------------

The hub data is represented by a ``ProductPageHubData`` object, which is
a Pydantic model. It can be serialized and stored between application sessions.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPageHub, ProductPageHubData

    CACHE_FILE = 'hubData.json'

    def dump_to_file(data: ProductPageHubData, file_path: str) -> None:
        print(f"Dumping data to cache file '{file_path}'...")
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write(data.model_dump_json(indent=4, by_alias=True))

    async def main() -> None:
        print('Initializing hub session...')
        async with ProductPageHub(enable_multiprocessing=True) as hub:
            print('Searching for pages in range 10 to 20...')
            await hub.scan(start=10, stop=20)
            print('Dumping hub data to file...')
            dump_to_file(hub.data, CACHE_FILE)

    if __name__ == '__main__':
        asyncio.run(main())

In the example above, the hub scans for pages with IDs from 10 to 20.
The resulting page data is dumped to a JSON file. The data can be loaded back
into the hub by providing a ``ProductPageHubData`` object to the constructor.

The ``enable_multiprocessing`` parameter in the ``ProductPageHub`` constructor
is used to enable multiprocessing for the hub. When enabled, the hub will use
multiple processes to parse the fetched product page data. On one hand, this
can significantly speed up the data retrieval process. On the other hand,
Python's ``multiprocessing`` module has some limitations and should be used
with caution. See `concurrent.futures <https://docs.python.org/3/library/
concurrent.futures.html#processpoolexecutor>`__ documentation for more
information.

.. note::
    The full dumped JSON data for every existing page may take up to 80 MB of
    disk space. You can exclude specific fields from serialization by providing
    the ``exclude`` parameter to the ``model_dump`` and ``model_dump_json``
    methods. For example, to exclude the product descriptions from the dumped
    data, you can use the following syntax:

    .. code-block:: python

        data = hub.data.model_dump(
            exclude={'pages': {'__all__': {'products': {'__all__': {'info'}}}}}
        )
