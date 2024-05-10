"""This example demonstrates the usage of the `find_product` and
the `find_products` methods of the `ProductPage` class to find
specific products on a FreshPoint location page based on various criteria.
"""

from freshpointsync import ProductPage


LOCATION_ID = 296
"""The number in the end of the URL of the Freshpoint.cz location page"""


async def main():
    # create a new ProductPage instance for a specific location
    async with ProductPage(location_id=LOCATION_ID) as page:
        # update product listings without triggering an update event
        await page.update_silently()

        # search for a specific product by name
        cola = page.find_product(name='Harboe Cola')  # attrib "name" must be
        if cola is None:                              # an exact match
            print("Harboe Cola not found.", end='\n\n')
        else:
            print(f'Harboe Cola count is {cola.quantity}.', end='\n\n')

        # search for specific products by category and quantity
        beverages_all = page.find_products(
            category='Nápoje'  # attrib "category" must be an exact match
            )
        beverages_out_of_stock = page.find_products(
            category='Nápoje', quantity=0
            )
        print(
            f'{len(beverages_out_of_stock)} of {len(beverages_all)} beverages '
            f'are out of stock.',
            end='\n\n'
            )

        # search for products with arbitrary conditions
        products_on_sale = page.find_products(
            constraint=lambda product: product.is_on_sale
            )
        print(
            f'{len(products_on_sale)} products are listed on sale.',
            end='\n\n'
            )

        # search for products with combined attribute matching and constraints
        products = page.find_products(
            constraint=lambda product: (
                'sendvice' in product.category_lowercase_ascii and
                product.is_available and
                product.price_curr < 100
                )
            )
        print('Sendvices available for less than 100 CZK:')
        for product in products:
            print(f'- {product.name} ({product.price_curr} CZK)')


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
