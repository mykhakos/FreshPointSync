"""`freshpoint.product` package provides a product model for representing
FreshPoint product data. It also provides classes for storing product data
change analysis results, which are are part of the low-level API.

The `Product` model is a part of the high-level API and can be accessed from
the top-level `freshpointsync` package.
"""

from ._product import (
    DEFAULT_PIC_URL,
    DiffValueTuple,
    Product,
    ProductPriceUpdateInfo,
    ProductQuantityUpdateInfo,
)

__all__ = [
    'DEFAULT_PIC_URL',
    'DiffValueTuple',
    'Product',
    'ProductPriceUpdateInfo',
    'ProductQuantityUpdateInfo',
]
