"""`freshpointsync.client` package provides means for fetching HTML content of
Freshpoint webpages. It is a part of the low-level API.
"""

from ._client import PageHTMLClient, logger

__all__ = [
    'PageHTMLClient',
    'logger',
]
