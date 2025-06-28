"""`freshpoint.page` package provides means for interacting with FreshPoint
webpages on the product level.

Classes from this package are key components of the high-level API and are
are also available in the top-level `freshpointsync` package for easier access.
"""

from ._page import (
    ProductPageClient,
    # ProductPageHub,
    logger,
)

__all__ = [
    'FetchInfo',
    'ProductPageClient',
    'ProductPageData',
    'ProductPageHub',
    'ProductPageHubData',
    'logger',
]
