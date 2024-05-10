"""This example demonstrates how to access the product data and
analyze changes in it."""

from freshpointsync import Product
from time import time


# create two snapshots of the same product to compare them
prod_prev = Product(
    id_=1,
    name='Harboe Cola',
    category='Nápoje',
    quantity=10,
    price_curr=25.5,
    price_full=30,
    timestamp=time() - 10  # timestamp ten seconds ago
    )
"""The previous state of the product from the last update 10 seconds ago.
Product quantity is 10. It is on sale for 25.5 CZK (current price) instead of
30 CZK (full price).
"""

prod_curr = Product(
    id_=1,
    name='Harboe Cola',
    category='Nápoje',
    quantity=5,
    price_curr=30,
    price_full=30,
    timestamp=time()  # current timestamp
    )
"""The current state of the product from the latest update.
Product quantity is 5. It is not on sale and costs 30 CZK.
"""

# determine if the product is currently on sale based on the prices
# ('is_on_sale' is a computed property of the Product class)
print(
    f'Product "{prod_curr.name}" is on sale: {prod_curr.is_on_sale}',
    end='\n\n'
    )  # False


# determine if the product is newer than the previous state
print(
    f'Product with timestamp: {prod_curr.timestamp} is newer than '
    f'the previous product with timestamp: {prod_prev.timestamp}: '
    f'{prod_curr.is_newer_than(prod_prev)}',
    end='\n\n'
    )  # True

# compare the prices of the products with ProductPriceUpdateInfo
price_info = prod_prev.compare_price(new=prod_curr)
print(
    f'Current price increase: {price_info.price_curr_increase} CZK\n'
    f'Sale ended: {price_info.sale_ended}',
    end='\n\n'
)

# compare the quantities of the products with ProductQuantityUpdateInfo
quantity_info = prod_prev.compare_quantity(new=prod_curr)
print(
    f'Quantity decrease: {quantity_info.stock_decrease} pieces\n'
    f'Is out of stock: {quantity_info.stock_depleted}'
)
