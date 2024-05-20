API Reference
=============

API reference for the ``freshpointsync`` library.

The API is designed to provide both high-level interfaces for fetching and
updating FreshPoint product data, as well as low-level interfaces that perform
specific tasks, such as fetching a webpage or parsing HTML content.

Below is a list of the high-level classes and functions that are available
straigh from ``freshpointsync``.

- :class:`freshpointsync.ProductPage`
- :class:`freshpointsync.ProductPageData`
- :class:`freshpointsync.ProductPageHub`
- :class:`freshpointsync.ProductPageHubData`
- :class:`freshpointsync.Product`
- :class:`freshpointsync.ProductUpdateEvent`
- :func:`freshpointsync.is_valid_handler`


``freshpointsync.client``
-------------------------

   The client package provides classes for fetching HTML content from a specific
   FreshPoint webpage. It is a part of the low-level API.

   .. automodule:: freshpointsync.client

``freshpointsync.page``
-----------------------

   The page package provides classes for interacting with a FreshPoint webpage.
   Classes from this module are composed of classes from the client, parser,
   product, and update packages. They form the high-level API.

   .. automodule:: freshpointsync.page

``freshpointsync.parser``
-------------------------

   The parser module provides classes for parsing HTML content and extracting
   product data in the form of Pydantic models. It is a part of the low-level
   API.

   .. automodule:: freshpointsync.parser

``freshpointsync.product``
--------------------------

   The product module provides a Pydantic model for representing FreshPoint
   product data. It is a part of the high-level API. It also provides classes
   for storing product data change analysis results, which can be accessed from
   the low-level API.

   .. automodule:: freshpointsync.product

``freshpointsync.update``
-------------------------

   The update module provides classes for updating and managing changes in
   FreshPoint product data. It is a part of the low-level API.

   .. automodule:: freshpointsync.update
