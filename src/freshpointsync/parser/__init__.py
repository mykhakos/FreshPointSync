"""`freshpointsync.parser` package provides means for parsing HTML contents of
FreshPoint webpages and extracting product data. It is a part of the low-level
API.
"""

from ._parser import (
    ProductFinder,
    ProductPageHTMLParser,
    hash_text,
    logger,
    normalize_text,
    parse_page_contents,
)

__all__ = [
    'ProductFinder',
    'ProductPageHTMLParser',
    'hash_text',
    'logger',
    'normalize_text',
    'parse_page_contents',
]
