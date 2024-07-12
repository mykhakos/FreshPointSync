"""`freshpointsync.parser` package provides means for parsing HTML contents of
FreshPoint webpages and extracting product data. It is a part of the low-level
API.
"""

from ._parser import (
    ProductFinder,
    ProductPageHTMLParser,
    hash_text,
    normalize_text,
)

__all__ = [
    'ProductFinder',
    'ProductPageHTMLParser',
    'hash_text',
    'normalize_text',
]
