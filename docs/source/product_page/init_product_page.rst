==========================
Fetching Product Page Data
==========================

This chapter explains how to create and manage ``ProductPage`` instances using
the ``async with`` statement as well as manual instance management.
Additionally, it demonstrates how to initialize a ``ProductPage`` instance with
previously serialized data.

Using the ``async with`` statement
----------------------------------
Creating a ``ProductPage`` instance using the ``async with`` statement
leverages the context manager capabilities of the class. This approach is
suitable for direct use of the object in an asynchronous function. It handles
the client session establishment and closure and awaits for the update handlers
automatically (more on the latter later).

This method is recommended for simple one-time use cases. For example, if you
implement a script that fetches the page data, prints the parsed page location,
and exits.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    LOCATION_ID = 296  # unique location ID for a Freshpoint.cz location

    async def main() -> None:
        async with ProductPage(location_id=LOCATION_ID) as page:
            print(f'Fetching data for location ID: {page.data.location_id}...')
            await page.update_silently()
            print(f'Page location name: {page.data.location_name}')

    if __name__ == '__main__':
        asyncio.run(main())

In the example above, the ``ProductPage`` instance is created. It fetches
the data for the specified location ID and prints the location name.

.. note::

   If you specify a non-existent location ID, the page data will be empty.

Opting for Manual Instance Management
-------------------------------------
Manual creation and management of the ``ProductPage`` instance is suitable
when you need precise control over the object lifecycle, such as when using it
as a class attribute or a global variable. This way, you can create the
instance outside of the asynchronous context and manage the session and data
updates manually. However, it is also on you to ensure that the session is
closed properly.

.. tip::

   It is generally not advised to instantiate ``ProductPage`` every time you
   need to fetch the data during the application lifecycle. Instead, you should
   reuse the instance and update the data as needed.

Let's implement a simple REPL application that prints the product availability
on user input.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage

    def print_product_info(page: ProductPage, product_name: str) -> None:
        product = page.find_product(
            lambda p: product_name.casefold() in p.name_lowercase_ascii
            )  # case-insensitive search for a partial match
        if product:
            print(f'Product "{product.name}" quantity: {product.quantity} pcs.')
        else:
            print(f'Product "{product_name}" not found on the page.')

    def get_user_input() -> str:
        return input('Enter product name (or "exit" to quit): ')

    async def prompt_forever(page: ProductPage) -> None:
        while True:
            product_name = get_user_input()
            if product_name == 'exit':
                print('Exiting...')
                break
            await page.update_silently()
            print_product_info(page, product_name)

    async def main() -> None:
        page = ProductPage(location_id=296)
        try:
            await page.start_session()
        except Exception as e:
            print(f'An error occurred while starting the session: {e}')
            return
        try:
            await page.update_silently()
            await prompt_forever(page)
        except EOFError:
            pass  # handle Ctrl+C with no input (EOF)
        except Exception as e:
            print(f'An unexpected error occurred: {e}')
        finally:
            await page.close_session()

    if __name__ == '__main__':
        try:
            asyncio.run(main())
        except KeyboardInterrupt:
            print('\nExiting...')

In the example above, the ``ProductPage`` instance is created in the ``main``
function. The session is started and the initial data is fetched. The script
then enters an infinite loop under a ``try-finally`` block. The loop prompts
the user for a product name and prints the product quantity. The session is
closed when the user exits the loop. Using the ``try-finally`` block is crucial
to ensure that the session is closed properly, even if an exception occurs.

.. note::

   The page data is fetched using the ``update_silently`` method. This method
   fetches and updates the data without triggering the update handlers.
   If there are no update handlers hooked to the instance, the regular
   ``update`` method and ``update_silently`` are equivalent, with
   the latter being slightly more efficient in some cases.

Realistically, this example could still be implemented using the ``async with``
statement. However, this way the implementation is more explicit and easier
to understand and maintain. As your application grows, you may find this
approach more suitable.

Leveraging Serialized Data
--------------------------
The ``ProductPage`` class implements the ``data`` attribute of type
``ProductPageData`` in its body. The data under this attribute is empty upon
initialization and is updated with the ``update``, ``update_silently``, and
``update_forever`` methods. However, it is possible to provide the initial data
for this attribute when creating a new ``ProductPage`` instance by passing
a ``ProductPageData`` object to the ``data`` parameter of the ``ProductPage``
constructor. It is also possible to serialize the data to a JSON string and
store it between application sessions.

Let's implement a script that periodically fetches the page data and prints
if the page has changed since the last update.

.. code-block:: python

    import asyncio
    from freshpointsync import ProductPage, ProductPageData

    DATA = {
        "locationId": 296,
        "htmlHash": "946ab720ca287ca07f4258ad8f0138a4",
        "products": {
            "1419": {
                "id": 1419,
                "name": "BIO Zahradní limonáda bezový květ & meduňka 310 ml",
                "category": "Nápoje",
                "isVegetarian": False,
                "isGlutenFree": False,
                "quantity": 0,
                "priceFull": 36.72,
                "priceCurr": 36.72,
                "picUrl": "",
                "locationId": 296,
                "location": "Elektroline",
                "timestamp": 1715728503.222
            },
        }  # this is a simplified example of serialized page data
    
    def load_from_file(file_path: str) -> ProductPageData:
        with open(file_path, 'r') as f:
            data = f.read()
        return ProductPageData.model_validate_json(data)

    def dump_to_file(data: ProductPageData, file_path: str) -> None:
        with open(file_path, 'w') as f:
            f.write(data.model_dump_json(indent=4, by_alias=True))

    async def main() -> None:
        data = ProductPageData.model_validate(DATA)
        # data = load_from_file('pageData.json')  # uncomment to load from file
        async with ProductPage(data=data) as page:
            await page.update_silently()
            print(f'Location ID: {page.data.location_id}')
            print(f'Location name: {page.data.location}')
            if page.data.html_hash != data.html_hash:
                print('The page has changed since the last update.')
            else:
                print('The page has not changed since the last update.')
        # dump_to_file(page.data, 'pageData.json')  # uncomment to save the data
        
    if __name__ == '__main__':
        asyncio.run(main())

In the example above, a ``ProductPageData`` object is created from
the serialized data. A new ``ProductPage`` instance is created with this data.
The page data is then updated, and the script prints whether the page has
changed since the last update based on the value of MD5 hash of the page HTML
contents.

.. tip::

   If you run the script as is, it will always print that the page has changed.
   This is because the ``DATA`` dictionary is not representative of an actual
   Freshpoint.cz page contents. Try uncommenting the ``dump_to_file`` function
   call to save the page data to a file after the first run. Then, uncomment
   the ``load_from_file`` function call to load the data from the file and
   validate a new ``ProductPageData`` object with it. The hash comparison will
   then correctly determine if the page has changed since the last update.
