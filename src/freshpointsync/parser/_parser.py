import bs4
import html
import re
import typing

from unidecode import unidecode

from ..product._product import Product


def normalize_text(text: typing.Any) -> str:
    return unidecode(str(text).strip().casefold())


class ProductHTMLParser:
    """
    A parser class for extracting product information from HTML tags.

    This class provides static methods to parse various attributes of a product
    from its HTML representation. It's designed to work with BeautifulSoup
    `Tag` objects, extracting data such as product name, ID number, pricing,
    availability, etc.
    """

    @staticmethod
    def _extract_single_tag(result: bs4.ResultSet) -> bs4.Tag:
        """
        Get a single Tag in a ResultSet.

        Args:
            result (bs4.ResultSet): A ResultSet expected to contain
            exactly one Tag.

        Returns:
            bs4.Tag: The Tag object contained in the provided ResultSet.

        Raises:
            ValueError: If `result` does not contain exactly one Tag.
        """
        if len(result) == 0:
            raise ValueError(
                'Parsing Error: The ResultSet is empty. '
                'Expected one element to extract the text from.'
                )
        if len(result) != 1:
            raise ValueError(
                f'Parsing Error: The ResultSet contains {len(result)} '
                'elements. Expected only one element for text extraction.'
                )
        if not isinstance(result[0], bs4.Tag):
            raise ValueError(
                'Parsing Error: The element in the ResultSet '
                'is not a Tag object. Unable to extract text.'
                )
        return result[0]

    @staticmethod
    def _get_attr_value(attr_name: str, product_data: bs4.Tag) -> str:
        """
        Retrieve the value of a specified attribute from a Tag.

        Args:
            attr_name (str): The name of the attribute to retrieve.
            product_data (bs4.Tag): The BeautifulSoup Tag to extract
            the attribute from.

        Returns:
            str: The value of the specified attribute.

        Raises:
            KeyError: If the attribute is missing.
            ValueError: If the attribute is not a string.
        """
        try:
            attr = product_data[attr_name]
        except KeyError as err:
            raise KeyError(
                f'Product attributes do not contain keyword "{attr_name}".'
            ) from err
        if not isinstance(attr, str):
            raise ValueError(
                f'Unexpected "{attr_name}" attribute parsing results: '
                f'attribute value is expected to be a string '
                f'(got type "{type(attr).__name__}").'
                )
        return attr.strip()

    @classmethod
    def find_name(cls, product_data: bs4.Tag) -> str:
        """Extracts and returns the product name from the given Tag."""
        return html.unescape(cls._get_attr_value('data-name', product_data))

    @classmethod
    def find_id(cls, product_data: bs4.Tag) -> int:
        """Extracts and returns the product ID number from the given Tag."""
        return int(cls._get_attr_value('data-id', product_data))

    @classmethod
    def find_is_vegetarian(cls, product_data: bs4.Tag) -> bool:
        """Determines and returns whether the product is vegetarian."""
        return cls._get_attr_value('data-veggie', product_data) == '1'

    @classmethod
    def find_is_gluten_free(cls, product_data: bs4.Tag) -> bool:
        """Determines and returns whether the product is gluten-free."""
        return cls._get_attr_value('data-glutenfree', product_data) == '1'

    @classmethod
    def find_pic_url(cls, product_data: bs4.Tag) -> str:
        """Extracts and returns the URL of the product's picture."""
        return cls._get_attr_value('data-photourl', product_data)

    @classmethod
    def find_category(cls, product_data: bs4.Tag) -> str:
        """Extracts and returns the product category, or None if not found."""
        if product_data.parent is None:
            id_number = cls.find_id(product_data)
            raise AttributeError(
                f'Unable to extract product category name for product '
                f'"{id_number}" from the provided html data '
                f'(parent data is missing).'
                )
        category = product_data.parent.find_all(
            name='h2',
            string=lambda text: text
            )
        try:
            return cls._extract_single_tag(category).text.strip()
        except Exception as exp:
            id_number = cls.find_id(product_data)
            raise ValueError(
                f'Unable to extract product category name for product '
                f'"{id_number}" from the provided html data ({exp}).'
                ) from exp

    @classmethod
    def find_count(cls, product_data: bs4.Tag) -> int:
        """Determines and returns the count of available products."""
        if 'sold-out' in product_data.attrs.get('class', {}):
            return 0
        result = product_data.find_all(
            name='span',
            string=(
                lambda text: bool(
                    text and
                    re.match(
                        pattern=r"^((posledni)|(\d+))\s(kus|kusy|kusu)!?$",
                        string=normalize_text(text)
                        )
                    )
                )
            )
        if not result:  # products that are sold out do not have the count text
            return 0    # (should be caught by the "sold-out" check above)
        count = normalize_text(cls._extract_single_tag(result).text)
        if 'posledn' in count:  # check if is the last item
            return 1
        try:
            return int(count.split()[0])  # extr. from "2 kusy", "5 kusu", etc.
        except ValueError as err:
            raise ValueError(
                f'Parsing Error: Unable to convert product count to integer '
                f'({err})'
                ) from err

    @classmethod
    def _convert_price(cls, price: str, product_data: bs4.Tag) -> float:
        try:
            return float(price)
        except ValueError as err:
            id_number = cls.find_id(product_data)
            raise ValueError(
                f'Parsing Error: Unable to convert product "id={id_number}" '
                f'price to float ({err}).'
                ) from err

    @classmethod
    def find_price(cls, product_data: bs4.Tag) -> tuple[float, float]:
        """Extracts and returns the full and current price of the product."""
        result = product_data.find_all(
            name='span',
            string=(
                lambda text: bool(
                    text and
                    re.match(
                        pattern=r"^\d+\.\d+$",
                        string=normalize_text(text)
                        )
                    )
                )
            )
        if len(result) == 1:
            price_full_str = result[0].text
            price_full = cls._convert_price(price_full_str, product_data)
            return price_full, price_full
        elif len(result) == 2:
            price_full_str = result[0].text
            price_curr_str = result[1].text
            price_full = cls._convert_price(price_full_str, product_data)
            price_curr = cls._convert_price(price_curr_str, product_data)
            if price_curr > price_full:
                raise ValueError(
                    f'Unexpected product price parsing results: '
                    f'current price "{price_curr}" is greater than '
                    f'the regular full price "{price_full}".'
                    )
            # elif price_curr < price_full:  # "data-isPromo" is unreliable
            #     if cls._get_attr_value('data-ispromo', product_data) != '1':
            #         raise ValueError(
            #             f'Unexpected product price parsing results: '
            #             f'current price "{price_curr}" is different from '
            #             f'the regular full price "{price_full}", '
            #             f'but the "isPromo" flag is not set.'
            #             )
            return price_full, price_curr
        raise ValueError(
            f'Parsing Error: Unexpected number of elements in the product '
            f'price parsing ResultSet (expected 1 or 2, got {len(result)}).'
            )


class ProductPageHTMLParser:
    """
    A parser class for processing HTML contents of a FreshPoint product page.

    This class uses BeautifulSoup to parse HTML content and extract data
    related to the products listed on the page. The parser can search for
    products by either name, ID, or both.
    """
    def __init__(
        self,
        page_data: str,
        page_id: typing.Optional[int] = None
    ) -> None:
        """
        Initialize the parser with HTML contents of a product page.

        Args:
            page_data (str | None): HTML contents of the product page.
            If None, initializes with empty contents.
        """
        self._bs4_parser = bs4.BeautifulSoup(page_data, 'lxml')
        self._page_id = page_id
        self._location_name: typing.Optional[str] = None
        self._products: typing.Optional[tuple[Product, ...]] = None

    @property
    def page_id(self) -> int:
        if self._page_id is not None:
            return self._page_id
        script_tag = self._bs4_parser.find(
            'script', text=re.compile('deviceId')
            )
        if script_tag:
            script_text = script_tag.get_text()
            match = re.search(r'deviceId\s*=\s*"(.*?)"', script_text)
            if not match:
                raise ValueError(
                    'Unable to parse page id ("deviceId" parameter '
                    'within the "script" tag was not matched).'
                    )
            try:
                self._page_id = int(match.group(1))
            except Exception as e:
                raise ValueError(f'Unable to parse page id ({e}).') from e
            return self._page_id
        raise ValueError(
            'Unable to parse page id '
            '("script" tag with "deviceId" parameter was not found).'
            )

    @property
    def location_name(self) -> str:
        if self._location_name is not None:
            return self._location_name
        title_tag = self._bs4_parser.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            try:
                self._location_name = title_text.split('|')[0].strip()
            except Exception as e:
                raise ValueError(f'Unable to parse location name: {e}') from e
            return self._location_name
        raise ValueError(
            'Unable to parse location name ("title" tag  was not found).'
            )

    @property
    def products(self) -> tuple[Product, ...]:
        if self._products is not None:
            return self._products
        self._products = self.find_products()
        return self._products

    def _find_product_data(
        self,
        name: typing.Optional[str],
        id: typing.Optional[int]
    ) -> bs4.ResultSet:
        """
        A helper method to find raw HTML data for products matching
        the specified name or ID. Can filter products by both attributes
        simultaneously.

        Args:
            name (str | None): The name of the product to search for. If None,
            ignores the name attribute in filtering.
            id (int | None): The ID of the product to search for. If None,
            ignores the ID attribute in filtering.

        Returns:
            bs4.ResultSet: A BeautifulSoup ResultSet containing
            the found product elements' data.
        """
        attrs = {'class': lambda value: value and 'product' in value}
        if name is not None:
            attrs['data-name'] = lambda value: (
                value and (normalize_text(name) in normalize_text(value))
                )
        if id is not None:
            attrs['data-id'] = lambda value: (
                value and (str(id) == normalize_text(value))
                )
        return self._bs4_parser.find_all('div', attrs=attrs)

    def _parse_product_data(self, product_data: bs4.Tag) -> Product:
        """
        Parses the product data and returns a `Product` instance.

        Args:
            product_data (bs4.Tag): The BeautifulSoup Tag containing
            the product data.

        Returns:
            Product: An instance of the `Product` class with the parsed data.
        """
        price_full, price_curr = ProductHTMLParser.find_price(product_data)
        return Product(
            product_id=ProductHTMLParser.find_id(product_data),
            name=ProductHTMLParser.find_name(product_data),
            category=ProductHTMLParser.find_category(product_data),
            is_vegetarian=ProductHTMLParser.find_is_vegetarian(product_data),
            is_gluten_free=ProductHTMLParser.find_is_gluten_free(product_data),
            quantity=ProductHTMLParser.find_count(product_data),
            price_curr=price_curr,
            price_full=price_full,
            pic_url=ProductHTMLParser.find_pic_url(product_data),
            location_id=self.page_id,
            location_name=self.location_name
            )

    def find_product(
        self,
        name: typing.Optional[str] = None,
        id: typing.Optional[int] = None
    ) -> Product:
        """
        Find a single product based on the specified name and/or ID.
        The name can match partially; the ID must be an exact match.

        Args:
            name (str | None): The name of the product to filter by. Note that
            product names are normalized to lowercase ASCII characters for
            matching, allowing for partial and case-insensitive matches.
            If None, name filtering is not applied.
            id (int | None): The ID of the product to filter by. The ID match
            is exact. If None, ID filtering is not applied.

        Returns:
            Product: A `Product` object with the parsed product data.

        Raises:
            ValueError: If the product with the specified name and/or ID
            is not found or if multiple products match the criteria
            (i.e., the result is not unique).
        """
        product_data = self._find_product_data(name, id)
        if len(product_data) == 0:
            name = name if name else 'any'
            id_str = str(id) if id is not None else 'any'
            raise ValueError(
                f'Product with attributes "name={name}", "id={id_str}" '
                f'was not found.'
                )
        if len(product_data) != 1:
            name = name if name else 'any'
            id_str = str(id) if id is not None else 'any'
            raise ValueError(
                f'Product with attributes "name={name}", "id={id_str}" '
                f'is not unique.'
                )
        return self._parse_product_data(product_data[0])

    def find_products(
        self,
        name: typing.Optional[str] = None
    ) -> tuple[Product, ...]:
        """
        Find a list of products. If a name is specified, returns only products
        where the specified name matches (or partially matches) the product
        name. Otherwise, all products on the page are returned.

        Args:
            name (str | None): The name of the product to filter by. Note that
            product names are normalized to lowercase ASCII characters for
            matching, allowing for partial and case-insensitive matches.
            If None, retrieves all products.

        Returns:
            tuple[Product]: A tuple of `Product` objects with the parsed
            product data.
        """
        product_data = self._find_product_data(name, None)
        products = (self._parse_product_data(data) for data in product_data)
        return tuple(products)


class ProductFinder:
    """
    A utility for searching and filtering products based on certain attributes
    and constraints. This class provides static methods to find either
    a single product or a list of products from an iterable collection of
    `Product` instances.
    """

    @staticmethod
    def find_product(
        products: typing.Iterable[Product],
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes: typing.Any
    ) -> typing.Optional[Product]:
        """
        Searches for a single product in an iterable of products that matches
        the given attributes and an optional constraint.

        Args:
            products (Iterable[Product]):
                An iterable collection of `Product` instances.
            constraint (Optional[Callable[[Product], bool]]):
                An optional function that takes a `Product` instance as input
                and returns a boolean indicating whether a certain constraint
                is met. The product must satisfy this constraint to be
                considered a match.
            **attributes (Any):
                Arbitrary keyword arguments representing the product
                attributes and properties and their expected values for
                the product to match.

        Returns:
            Optional[Product]:
                The first product in the iterable that matches the given
                attributes and constraint, or None if no such product is found.
        """
        for product in products:
            if constraint and not constraint(product):
                continue
            if all(
                getattr(product, key) == value
                for key, value in attributes.items()
            ):
                return product
        return None

    @staticmethod
    def find_products(
        products: typing.Iterable[Product],
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes
    ) -> list[Product]:
        """
        Searches for all products in an iterable of products that match
        the given attributes and an optional constraint.

        Args:
            products (Iterable[Product]):
                An iterable collection of `Product` instances.
            constraint (Optional[Callable[[Product], bool]]):
                An optional function that takes a `Product` instance as input
                and returns a boolean indicating whether a certain constraint
                is met. A product must satisfy this constraint to be
                considered a match.
            **attributes (Any):
                Arbitrary keyword arguments representing the product
                attributes and properties and their expected values for
                the products to match.

        Returns:
            list[Product]:
                A list of all products in the iterable that match the given
                attributes and constraint.
        """
        found_products = []
        for product in products:
            if constraint and not constraint(product):
                continue
            if all(
                getattr(product, key, None) == value
                for key, value in attributes.items()
            ):
                found_products.append(product)
        return found_products
