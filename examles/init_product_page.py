"""This example demonstrates how to create and manage a ProductPage instance
with the 'async with' statement, without it, and from serialized data.
"""

from freshpointsync import ProductPage, ProductPageData


LOCATION_ID = 296
"""The number in the end of the URL of the Freshpoint.cz location page"""


async def init_page_with() -> None:
    """Create a ProductPage instance with the 'async with' statement.
    This is suitable for direct use in an async function.
    The client session is established and closed automatically.
    """
    async with ProductPage(location_id=LOCATION_ID) as page:
        print(f'Product count before update: {len(page.data.products)}')
        # update product listings without triggering an update event
        await page.update_silently()
        print(f'Product count after update: {len(page.data.products)}')


async def init_page_alt() -> None:
    """Create and manage ProductPage instance manually.
    This is suitable for manual object handling,
    e.g. as a class attribute or a global variable.
    """
    page = ProductPage(location_id=LOCATION_ID)
    try:
        await page.start_session()
        await page.update_silently()
        print(f'Page location name: {page.data.location_name}')
    finally:
        await page.close_session()
        await page.cancel_update_forever()


async def init_page_from_data() -> None:
    """Create a ProductPage instance from serialized data.
    This is useful for loading a page from a serialized cache data,
    for example, when the page contents is checked periodically.
    """
    data = ProductPageData.model_validate(
        {
            'location_id': LOCATION_ID,
            'products': {
                1: {
                    'id': 1,
                    'name': 'Harboe Cola',
                    'category': 'Nápoje',
                    'quantity': 10,
                    'price_curr': 25.5,
                    'price_full': 30
                }
            }
        }
    )
    async with ProductPage(data=data) as page:
        print(f'Page location ID: {page.data.location_id}')
    new_data = page.data.model_dump_json()  # new data can be serialized
    assert isinstance(new_data, str)


async def main():
    await init_page_with()
    await init_page_alt()
    await init_page_from_data()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
