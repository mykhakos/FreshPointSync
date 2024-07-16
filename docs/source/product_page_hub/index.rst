Using Product Page Hubs
=======================

The ``ProductPageHub`` class acts as a high-level manager for interacting with
multiple product pages simultaneously. While each page retains its own state and
can be accessed individually, all pages share a single client session and
a common task runner for efficient data updates.

API of ``ProductPageHub`` is similar to the one of the ``ProductPage`` class.
Studying the :ref:`latter <product-page-intro>` is recommended before proceeding
with the hub.

.. toctree::
   :maxdepth: 2
   :caption: Contents:

   init_hub
   update_and_subscribe