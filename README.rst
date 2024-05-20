==============================================================
FreshPointSync: FreshPoint.cz web page data parser and syncer.
==============================================================

FreshPointSync delivers an efficient asynchronous interface designed for
extracting and tracking data from `FreshPoint <https://my.freshpoint.cz/>`__
product webpages.

| `📁 Source files <https://github.com/mykhakos/FreshPointSync>`__
| `⚠️ Issue tracker <https://github.com/mykhakos/FreshPointSync/issues>`__
| `📦 PyPI <https://pypi.org/project/freshpointsync/>`__
| `📜 Documentation <https://github.com/mykhakos/FreshPointSync>`__


Installation
------------

FreshPointSync supports Python 3.8 and higher. The library can be installed
using the following CLI command:

.. code-block:: console

   $ pip install freshpointsync


Minimal Example
---------------

The following example demonstrates how to fetch a FreshPoint webpage data
and analyze its contents:

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    async def main() -> None:
        async with ProductPage(location_id=296) as page:
            await page.update()
            products = page.find_products()
            print(
                f'Location name: {page.data.location}\n'
                f'Product count: {len(products)} '
                f'({len([p for p in products if p.is_available])} in stock)'
            )

    if __name__ == '__main__':
        asyncio.run(main())
