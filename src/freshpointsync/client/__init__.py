"""`freshpointsync.client` package provides means for fetching HTML content of
Freshpoint webpages. It is a part of the low-level API.
"""

from ._client import ProductDataFetchClient, logger

__all__ = ['ProductDataFetchClient', 'logger']
