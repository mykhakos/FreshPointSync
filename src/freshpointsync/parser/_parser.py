import bs4
import hashlib
import html
import logging
import re
import typing

from functools import cached_property
from unidecode import unidecode

from ..product._product import Product


logger = logging.getLogger("freshpointsync.parser")


def normalize_text(text: typing.Any) -> str:
    """Normalize the given text by removing diacritics, leading/trailing
    whitespace, and converting it to lowercase. Non-string values are
    converted to strings. `None` values are converted to empty strings.

    Args:
        text (typing.Any): The text to be normalized.

    Returns:
        str: The normalized text.
    """
    if text is None:
        return ""
    return unidecode(str(text).strip()).casefold()


def hash_text(text: str) -> str:
    """Calculate the SHA-256 hash of the given text.

    Args:
        text (str): The text to be hashed.

    Returns:
        str: The SHA-256 hash of the input text in hexadecimal format.
    """
    return hashlib.sha256(text.encode('utf-8')).hexdigest()


T = typing.TypeVar('T')


class ProductHTMLParser:
    """A parser utility for extracting product information from HTML tags.

    This class provides static methods to parse various attributes of a product
    from its HTML representation. It's designed to work with BeautifulSoup
    `Tag` objects, extracting data such as product name, ID number, pricing,
    availability, etc.
    """

    @staticmethod
    def _extract_single_tag(resultset: bs4.ResultSet) -> bs4.Tag:
        """Get a single Tag in a ResultSet.

        Args:
            resultset (bs4.ResultSet): A `bs4.ResultSet` object
                expected to contain exactly one `bs4.Tag` object.

        Returns:
            bs4.Tag: The Tag contained in the provided `resultset`.

        Raises:
            ValueError: If `resultset` does not contain exactly one Tag.
            TypeError: If the extracted element is not a `bs4.Tag` object.
        """
        if len(resultset) == 0:
            raise ValueError(
                'ResultSet is empty (expected one Tag element).'
                )
        if len(resultset) != 1:
            raise ValueError(
                f'Unexpected number of elements in the ResultSet'
                f'(expected 1, got {len(resultset)}).'
                )
        if not isinstance(resultset[0], bs4.Tag):
            raise TypeError(
                f'The element in the ResultSet is not a Tag object. '
                f'(got type "{type(resultset[0]).__name__}").'
                )
        return resultset[0]

    @staticmethod
    def _get_attr_value(attr_name: str, tag: bs4.Tag) -> str:
        """Get the value of a specified attribute from a Tag.

        Args:
            attr_name (str): The name of the attribute to retrieve.
            tag (bs4.Tag): The Tag to extract the attribute from.

        Returns:
            str: The value of the specified attribute.

        Raises:
            KeyError: If the attribute is missing.
            ValueError: If the attribute is not a string.
        """
        try:
            attr = tag[attr_name]
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
        """Extract the product name from the given product data."""
        return html.unescape(cls._get_attr_value('data-name', product_data))

    @classmethod
    def find_id(cls, product_data: bs4.Tag) -> int:
        """Extract the product ID number from the given product data."""
        return int(cls._get_attr_value('data-id', product_data))

    @classmethod
    def find_is_vegetarian(cls, product_data: bs4.Tag) -> bool:
        """Determine whether the product is vegetarian
        from the given product data.
        """
        return cls._get_attr_value('data-veggie', product_data) == '1'

    @classmethod
    def find_is_gluten_free(cls, product_data: bs4.Tag) -> bool:
        """Determine whether the product is gluten-free
        from the given product data.
        """
        return cls._get_attr_value('data-glutenfree', product_data) == '1'

    @classmethod
    def find_pic_url(cls, product_data: bs4.Tag) -> str:
        """Extract the URL of the product's picture
        from the given product data.
        """
        return cls._get_attr_value('data-photourl', product_data)

    @classmethod
    def find_category(cls, product_data: bs4.Tag) -> str:
        """Extract the product category from the given product data."""
        if product_data.parent is None:
            raise AttributeError(
                f'Unable to extract product category name for product '
                f'"id={cls._find_id_safe(product_data)}" from the provided '
                f'html data (parent data is missing).'
                )
        category = product_data.parent.find_all(
            name='h2',
            string=lambda text: text
            )
        try:
            return cls._extract_single_tag(category).text.strip()
        except Exception as exp:
            raise ValueError(
                f'Unable to extract product category name for product '
                f'"id={cls._find_id_safe(product_data)}" from the provided '
                f'html data ({exp}).'
                ) from exp

    @classmethod
    def _find_id_safe(cls, product_data: bs4.Tag) -> str:
        """Extract the product ID number from the given product data. If the ID
        is not found, catch the raised exception and return a placeholder.
        """
        try:
            return str(cls.find_id(product_data))
        except Exception as e:
            logger.warning(
                f'Unable to extract product ID from the provided html data '
                f'({e}).'
                )
            return '?'

    @classmethod
    def _run_converter(
        cls, converter: typing.Callable[[], T], product_data: bs4.Tag
    ) -> T:
        """Run the given converter function and return the converted value.

        Args:
            converter (typing.Callable[[], T]): The converter function
                to be executed.
            product_data (bs4.Tag): The product data to be passed to
                the converter function.

        Returns:
            T: The converted value.

        Raises:
            ValueError: If an error occurs during the conversion process.
        """
        try:
            return converter()
        except Exception as exc:
            raise ValueError(
                f'Unable to convert a parsed value for the product '
                f'"id={cls._find_id_safe(product_data)}".'
                ) from exc

    @classmethod
    def find_quantity(cls, product_data: bs4.Tag) -> int:
        """Extract the quantity of the product from the given product data."""
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
        if not result:  # sold out products don't have the quantity text
            return 0    # (should be caught by the "sold-out" check above)
        quantity = normalize_text(cls._extract_single_tag(result).text)
        if 'posledn' in quantity:  # products that have only 1 item in stock
            return 1               # have "posledni" in the quantity text
        return cls._run_converter(
            lambda: int(quantity.split()[0]),  # regular ("2 kusy", "5 kusu")
            product_data
            )

    @classmethod
    def find_price(cls, product_data: bs4.Tag) -> tuple[float, float]:
        """Extract the full and current price of the product
        from the given product data.
        """
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
            price_full = cls._run_converter(
                lambda: float(result[0].text), product_data  # price_full_str
                )
            return price_full, price_full
        elif len(result) == 2:
            price_full = cls._run_converter(
                lambda: float(result[0].text), product_data  # price_full_str
                )
            price_curr = cls._run_converter(
                lambda: float(result[1].text), product_data  # price_curr_str
                )
            if price_curr > price_full:
                id_ = cls._find_id_safe(product_data)
                raise ValueError(
                    f'Unexpected product "id={id_}" parsing results: '
                    f'current price "{price_curr}" is greater than '
                    f'the regular full price "{price_full}".'
                    )
            # elif price_curr < price_full:  # "data-isPromo" is unreliable
            #     id_ = cls._find_id_safe(product_data)
            #     if cls._get_attr_value('data-ispromo', product_data) != '1':
            #         raise ValueError(
            #             f'Unexpected product "id={id_}" parsing results: '
            #             f'current price "{price_curr}" is different from '
            #             f'the regular full price "{price_full}", '
            #             f'but the "isPromo" flag is not set.'
            #             )
            return price_full, price_curr
        raise ValueError(
            f'Unexpected number of elements in the ResultSet'
            f'(expected 1 or 2, got {len(result)}).'
            )


class ProductPageHTMLParser:
    """
    A parser for processing HTML contents of a FreshPoint.cz web page.

    This class uses BeautifulSoup to parse HTML contents and extract data
    related to the products listed on the page. The parser can search for
    products by either name, ID, or both.
    """
    def __init__(self, page_html: str) -> None:
        """Initialize the parser with HTML contents of a product page.

        Args:
            page_html (str): HTML contents of the product page.
        """
        logger.info('Parsing page data...')
        self._bs4_parser = bs4.BeautifulSoup(page_html, 'lxml')

    @cached_property
    def page_id(self) -> int:
        """Page ID (extracted from
        the page HTML <script/> tag with the "deviceId" text).
        """
        script_tag = self._bs4_parser.find(
            'script', string=re.compile('deviceId')
            )
        if script_tag:
            script_text = script_tag.get_text()
            match = re.search(r'deviceId\s*=\s*"(.*?)"', script_text)
            if not match:
                raise ValueError(
                    'Unable to parse page ID ("deviceId" text '
                    'within the <script/> tag was not matched).'
                    )
            try:
                self._page_id = int(match.group(1))
            except Exception as e:
                raise ValueError('Unable to parse page ID.') from e
            return self._page_id
        raise ValueError(
            'Unable to parse page ID '
            '(<script/> tag with "deviceId" text was not found).'
            )

    @cached_property
    def location_name(self) -> str:
        """The name of the location (extracted from
        the page HTML <title/> tag).
        """
        title_tag = self._bs4_parser.find('title')
        if title_tag:
            title_text = title_tag.get_text()
            try:
                location_name = title_text.split('|')[0].strip()
            except Exception as e:
                raise ValueError('Unable to parse location name.') from e
            return location_name
        raise ValueError(
            'Unable to parse location name (<title/> tag  was not found).'
            )

    @cached_property
    def products(self) -> tuple[Product, ...]:
        """A tuple of `Product` instances parsed from the page HTML."""
        return self.find_products()

    def _find_product_data(
        self,
        name: typing.Optional[str],
        id: typing.Optional[int]
    ) -> bs4.ResultSet:
        """A helper method to find raw HTML data for products matching
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
        logger.debug(
            'Searching for products with attributes "name=%s", "id=%s"...',
            name if name else 'any',
            str(id) if id is not None else 'any'
            )
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
        """A helper method to parse the product data to a `Product` object.

        Args:
            product_data (bs4.Tag): The Tag containing the product data.

        Returns:
            Product: An instance of the `Product` class
            containitng the parsed data.
        """
        logger.debug(
            'Parsing product data for product with attributes "id=%s"...',
            ProductHTMLParser._find_id_safe(product_data)
            )
        price_full, price_curr = ProductHTMLParser.find_price(product_data)
        return Product(
            id_=ProductHTMLParser.find_id(product_data),
            name=ProductHTMLParser.find_name(product_data),
            category=ProductHTMLParser.find_category(product_data),
            is_vegetarian=ProductHTMLParser.find_is_vegetarian(product_data),
            is_gluten_free=ProductHTMLParser.find_is_gluten_free(product_data),
            quantity=ProductHTMLParser.find_quantity(product_data),
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
        """Find a single product based on the specified name and/or ID.

        Args:
            name (str | None): The name of the product to filter by. Note that
                product names are normalized to lowercase ASCII characters for
                matching, allowing for partial and case-insensitive matches.
                If None, name filtering is not applied.
            id (int | None): The ID of the product to filter by. The ID match
                is exact. If None, ID filtering is not applied.

        Returns:
            Product: A `Product` object with the specified name and/or ID.

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
        Find a list of products based on the specified name. If the name
        is not specified, all products on the page are returned.

        Args:
            name (str | None): The name of the product to filter by. Note that
                product names are normalized to lowercase ASCII characters for
                matching, allowing for partial and case-insensitive matches.
                If None, retrieves all products.

        Returns:
            tuple[Product]: `Product` objects with the specified name.
        """
        product_data = self._find_product_data(name, None)
        products = (self._parse_product_data(data) for data in product_data)
        return tuple(products)


class ProductFinder:
    """A utility for searching and filtering products based on certain
    attributes and constraints. This class provides static methods to find
    either a single product or a list of products from an collection of
    `Product` instances.
    """

    @classmethod
    def product_matches(
        cls,
        product: Product,
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes: typing.Any
    ) -> bool:
        """Check if a product matches the given attributes and an optional
        constraint.

        Args:
            product (Product): The product to check.
            constraint (Optional[Callable[[Product], bool]]):
                An optional function that takes a `Product` instance as input
                and returns a boolean indicating whether a certain constraint
                is met for this instance.
            **attributes (Any):
                Arbitrary keyword arguments representing the product
                attributes and properties and their expected values for
                the product to match.

        Returns:
            bool:
                True if the product matches the given attributes and
                constraint, False otherwise.
        """
        if constraint and not constraint(product):
            return False
        return all(
            getattr(product, key) == value for key, value in attributes.items()
            )

    @classmethod
    def find_product(
        cls,
        products: typing.Iterable[Product],
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes: typing.Any
    ) -> typing.Optional[Product]:
        """
        Find a single product in an iterable of products that matches
        the given attributes and an optional constraint.

        Args:
            products (Iterable[Product]):
                An iterable collection of `Product` instances.
            constraint (Optional[Callable[[Product], bool]]):
                An optional function that takes a `Product` instance as input
                and returns a boolean indicating whether a certain constraint
                is met for this instance.
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
            if cls.product_matches(product, constraint, **attributes):
                return product
        return None

    @classmethod
    def find_products(
        cls,
        products: typing.Iterable[Product],
        constraint: typing.Optional[typing.Callable[[Product], bool]] = None,
        **attributes
    ) -> list[Product]:
        """
        Find all products in an iterable of products that match
        the given attributes and an optional constraint.

        Args:
            products (Iterable[Product]):
                An iterable collection of `Product` instances.
            constraint (Optional[Callable[[Product], bool]]):
                An optional function that takes a `Product` instance as input
                and returns a boolean indicating whether a certain constraint
                is met for this instance.
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
            if cls.product_matches(product, constraint, **attributes):
                found_products.append(product)
        return found_products
