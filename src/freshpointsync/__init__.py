r"""`freshpointsync` library main entry point.

Welcome to FreshPointSync, your go-to asynchronous tool for extracting and
tracking data from my.freshpoint.cz product webpages.

Start by creating a `ProductPage` instance with a location ID and calling
`update()` to fetch the data from the webpage. The `data` attribute of the
`ProductPage` instance will contain the extracted data.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    LOCATION_ID = 296  # from https://my.freshpoint.cz/device/product-list/296


    async def main() -> None:
        async with ProductPage(location_id=LOCATION_ID) as page:
            await page.update()
            products_available = [
                product
                for product in page.data.products.values()
                if product.is_available
            ]
            print(
                f'Location name: {page.data.location}\n'
                f'Product count: {len(page.data.products)} '
                f'({len(products_available)} in stock)'
            )


    if __name__ == '__main__':
        asyncio.run(main())

Explore `freshpointsync` documentation for more details and examples.
"""

from . import client, page, parser, product, update
from ._logging import logger
from .page import (
    ProductPage,
    ProductPageData,
    ProductPageHub,
    ProductPageHubData,
)
from .product import Product
from .update import ProductUpdateEvent, is_valid_handler

__all__ = [
    'Product',
    'ProductPage',
    'ProductPageData',
    'ProductPageHub',
    'ProductPageHubData',
    'ProductUpdateEvent',
    'client',
    'is_valid_handler',
    'logger',
    'page',
    'parser',
    'product',
    'update',
]
