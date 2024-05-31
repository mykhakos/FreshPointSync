=================================================================
FreshPointSync: Data Parser and Syncer for FreshPoint.cz Webpages
=================================================================

Welcome to FreshPointSync, your go-to asynchronous tool for extracting and 
tracking data from *my.freshpoint.cz* product webpages.

`FreshPoint <https://freshpoint.cz/>`__ is a Czech service providing vending
machines with healthy snacks, lunches, and desserts for companies.
Unfortunately, the company does not offer any public API for accessing product
data, such as availability and prices. FreshPointSync is here to help.

Key Features
------------

⚡ **Asynchronous I/O**. FreshPointSync uses ``asyncio`` and ``aiohttp`` for
efficient web requests, optimal performance, and responsiveness.

🥄 **Robust HTML Scraping**. FreshPointSync utilizes ``beautifulsoup4`` for 
comprehensive product information extraction from the webpage HTML content.

📊 **Advanced Data Modeling and Analysis**. FreshPointSync employs ``pydantic`` 
for modeling, analyzing, and serializing extracted data.

🔔 **Event-Driven Handlers**. FreshPointSync implements the *observer pattern* 
to register handlers for specific events, such as product availability changes.

🔍 **Detailed Logging and Error Handling**. FreshPointSync ensures reliability 
and ease of debugging with ``logging`` and safe runners to handle unexpected
exceptions.

🛠️ **Clean and Readable Code**. FreshPointSync adheres to *PEP 8* standards and 
utilizes *type hints*, ensuring the code is clear, concise, and easy to work 
with.

📜 **Comprehensive Documentation**. FreshPointSync offers extensive in-code
documentation as well as an official user guide and tutorials hosted on the
`Read the Docs <https://freshpointsync.readthedocs.io/en/latest/>`__ platform.

Installation
------------

FreshPointSync supports Python 3.8 and higher. Official library releases can be
found on `📦 PyPI <https://pypi.org/project/freshpointsync/>`__. To install
the latest stable version of FreshPointSync, use the following CLI command:

.. code-block:: console

   $ pip install freshpointsync

To install the latest development version directly from the project's
`📁 GitHub repository <https://github.com/mykhakos/FreshPointSync>`__, use
the following CLI command:

.. code-block:: console

   $ pip install git+https://github.com/mykhakos/FreshPointSync

You can also install optional development dependencies using the following CLI
commands:

- For building documentation:

.. code-block:: console

   $ pip install freshpointsync[docs]

- For running tests:

.. code-block:: console

   $ pip install freshpointsync[tests]

Minimal Example
---------------

The following example demonstrates how to fetch data from a FreshPoint webpage 
based on its specific location ID and print the location name, overall product
count, and the number of available products.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    LOCATION_ID = 296  # from https://my.freshpoint.cz/device/product-list/296

    async def main() -> None:
        async with ProductPage(location_id=LOCATION_ID) as page:
            await page.update()
            products = page.find_products()
            products_available = [p for p in products if p.is_available]
            print(
                f'Location name: {page.data.location}\n'
                f'Product count: {len(products)} '
                f'({len(products_available)} in stock)'
            )

    if __name__ == '__main__':
        asyncio.run(main())

Reporting Issues and Contributing
---------------------------------

FreshPointSync is an open-source project in its early development stages. If you
encounter any issues or have suggestions for improvements, please report them on
the `GitHub Issue tracker <https://github.com/mykhakos/FreshPointSync/issues>`__.

Contributions to FreshPointSync are also welcome! If you would like
to contribute, please fork the repository, implement your changes, and open
a Pull Request with a detailed description of your work on the
`GitHub Pull Request page <https://github.com/mykhakos/FreshPointSync/pulls>`__.

License
-------

FreshPointSync is distributed under the MIT License.
