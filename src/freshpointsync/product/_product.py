import time
import typing

from dataclasses import dataclass, field, asdict
from functools import cached_property
from unidecode import unidecode


def collect_props(
    obj_type: typing.Type[object], include_private: bool = False
) -> tuple[str, ...]:
    """
    Collect names of the methods of the given object type decorated with
    `@property` and `@cached_property`.

    Args:
        obj_type (typing.Type[object]):
        The type of object to collect properties from.
        include_private (bool):
        If True, includes private properties. Defaults to False.

    Returns:
        tuple[str, ...]: A tuple containing the names of the properties.

    """
    return tuple(
        prop for prop in dir(obj_type)
        if isinstance(getattr(obj_type, prop), (property, cached_property)) and
        (include_private or not prop.startswith('_'))
        )


def get_default_pic_url() -> str:
    """
    Returns the default picture URL for a product.
    The URL points to an image hosted on the FreshPoint server.
    """
    return (
        r"https://images.weserv.nl/?url=http://freshpoint.freshserver.cz/"
        r"backend/web/media/photo/1_f587dd3fa21b22.jpg"
        )


PRICE_NOT_SET = -1
"""Sentinel value to flag that the price argument has not been provided."""


@dataclass(frozen=True)
class Product:
    """
    Represents a FreshPoint.cz web page product with various attributes.

    Args:
        product_id (int):
            Unique identifier or the product.
        name (str):
            Name of the product. Defaults to an empty string value.
        category (str):
            Category of the product. Defaults to an empty string value.
        is_vegetarian (bool):
            Indicates whether the product is vegetarian. Defaults to False.
        is_gluten_free (bool):
            Indicates whether the product is gluten-free. Defaults to False.
        quantity (int):
            Quantity of product items in stock. Defaults to 0.
        price_full (float):
            Full price of the product. If not provided, matches the current
            selling price if the latter is provided or is set to 0 otherwise.
        price_curr (float):
            Current selling price. If not provided, matches the full price
            if the latter is provided or is set to 0 otherwise.
        pic_url (str):
            URL of the product image. Default URL is used if not provided.
        location_id (int):
            Unique identifier or the product page URL. Defaults to 0.
        location_name (str):
            Name of the product location. Defaults to an empty string value.
        timestamp (int):
            Timestamp of the product creation, auto-generated.
    """
    product_id: int
    """Unique identifier or the product."""
    name: str = field(default='')
    """Name of the product."""
    category: str = field(default='')
    """Category of the product."""
    is_vegetarian: bool = field(default=False)
    """Indicates if the product is vegetarian."""
    is_gluten_free: bool = field(default=False)
    """Indicates if the product is gluten-free."""
    quantity: int = field(default=0)
    """Quantity of product items in stock."""
    price_full: float = field(default=PRICE_NOT_SET)
    """Full price of the product."""
    price_curr: float = field(default=PRICE_NOT_SET)
    """Current selling price of the product."""
    pic_url: str = field(default_factory=get_default_pic_url, repr=False)
    """URL of the product image."""
    location_id: int = field(default=0)
    """Unique identifier of the product page URL."""
    location_name: str = field(default='')
    """Name of the product location."""
    timestamp: float = field(
        default_factory=time.time, init=False, repr=False, compare=False
        )
    """Timestamp of the product creation, auto-generated."""

    def __post_init__(self):
        # use object.__setattr__ to bypass the frozen restriction
        if (
            self.price_full == PRICE_NOT_SET and
            self.price_curr == PRICE_NOT_SET
        ):
            object.__setattr__(self, 'price_full', 0.0)
            object.__setattr__(self, 'price_curr', 0.0)
        elif self.price_curr == PRICE_NOT_SET:
            object.__setattr__(self, 'price_curr', self.price_full)
        elif self.price_full == PRICE_NOT_SET:
            object.__setattr__(self, 'price_full', self.price_curr)

    @cached_property
    def _props(self) -> tuple[str, ...]:
        """
        Names of the methods of the object type decorated with
        `@property` and `@cached_property`.
        """
        return collect_props(type(self), include_private=False)

    @cached_property
    def name_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the product name."""
        return unidecode(self.name.strip()).casefold()

    @cached_property
    def category_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the product category."""
        return unidecode(self.category.strip()).casefold()

    @cached_property
    def discount_rate(self) -> float:
        """
        Discount rate (<0; 1>) of the product, calculated based on
        the difference between the full price and the current selling price.
        """
        if self.price_full == 0 or self.price_full < self.price_curr:
            return 0
        return round((self.price_full - self.price_curr) / self.price_full, 2)

    @cached_property
    def is_on_sale(self) -> bool:
        """
        A product is considered on sale if its current selling price is lower
        than its full price.
        """
        return self.price_curr < self.price_full

    @cached_property
    def is_available(self) -> bool:
        """
        A product is considered available if its quantity is greater than zero.
        """
        return self.quantity != 0

    @cached_property
    def is_sold_out(self) -> bool:
        """
        A product is considered available if its quantity equals zero.
        """
        return self.quantity == 0

    @cached_property
    def is_last_piece(self) -> bool:
        """
        A product is considered available if its quantity equals one.
        """
        return self.quantity == 1

    def as_dict(
        self, include_timestamp: bool = False, include_properties: bool = False
    ) -> dict[str, typing.Any]:
        """
        Get a dictionary representation of the product instance.

        With `include_timestamp=True` and `include_properties=False`,
        the behavior of this method mimics that of `dataclasses.asdict()`,
        except private attributes (prefixed with an underscore '_') are
        excluded from the resulting dictionary.

        Args:
            include_timestamp (bool):
                If True, the creation timestamp is included.
                Defaults to False.
            include_properties (bool):
                If True, computed property values are included.
                Defaults to False.

        Returns:
            dict[str, typing.Any]:
                A dictionary representing the product instance. Dictionary keys
                correspond to the names of public attributes and, optionally,
                computed properties. Dictionary values are the corresponding
                attribute and property values.
        """
        self_asdict = asdict(self)
        if not include_timestamp:
            del self_asdict['timestamp']
        if not include_properties:
            return self_asdict
        for prop in self._props:
            self_asdict[prop] = getattr(self, prop)
        return self_asdict

    def is_newer_than(self, other: 'Product') -> bool:
        """
        Determine if this product is newer that the given one by
        comparing their creation timestamps.

        Args:
            other (Product): The product to compare against.

        Returns:
            bool:
                `True` if this product is newer than the other product,
                `False` otherwise.
        """
        return self.timestamp > other.timestamp

    def diff(
        self, other: 'Product', include_properties: bool = True
    ) -> dict[str, tuple[typing.Any, typing.Any]]:
        """
        Compare this product with another to identify differences.
        Does not compare the creation timestamps.
        Optionally compares computed properties.

        Args:
            other (Product):
                The product to compare against.
            include_properties (bool):
                If True, includes property values in the comparison.

        Returns:
            dict[str, tuple[typing.Any, typing.Any]]:
                A dictionary with keys as attribute names and, optionally,
                property names. Dictionary values are tuples containing
                the differing values between this product and the other.
        """
        # get self's and other's data (attrs and props)
        self_asdict = self.as_dict(
            include_timestamp=False, include_properties=include_properties
            )
        other_asdict = other.as_dict(
            include_timestamp=False, include_properties=include_properties
            )
        # compare self to other
        diff: dict[str, tuple[typing.Any, typing.Any]] = {}
        for attr, value in self_asdict.items():
            other_value = other_asdict.get(attr)
            if value != other_value:
                diff[attr] = (value, other_value)
        # compare other to self (may be relevant for subclasses)
        if type(self) is type(other):
            return diff
        for attr, value in other_asdict.items():
            if attr not in self_asdict:
                diff[attr] = (None, value)
        return diff

    def compare_stock(self, new: 'Product') -> 'ProductStockUpdateInfo':
        """
        Compare the stock quantity of this product instance with the one of
        a newer instance of the same product.

        This comparison is meaningful primarily when the `new` argument
        represents the same product at a different state or time, such as
        after a stock update.

        Args:
            new (Product):
                The instance of the product to compare against. It should
                represent the same product at a different state or time.

        Returns:
            ProductStockUpdateInfo:
                An object containing information about changes in stock
                quantity of this product when compared to the provided product.
                It provides insights into changes in stock quantity, such as
                decreases, increases, depletion, or restocking.
        """
        if self.quantity > new.quantity:
            decrease = self.quantity - new.quantity
            increase = 0
            depleted = new.quantity == 0
            restocked = False
        elif self.quantity < new.quantity:
            decrease = 0
            increase = new.quantity - self.quantity
            depleted = False
            restocked = self.quantity == 0
        else:
            decrease = 0
            increase = 0
            depleted = False
            restocked = False
        return ProductStockUpdateInfo(decrease, increase, depleted, restocked)

    def compare_price(self, new: 'Product') -> 'ProductPriceUpdateInfo':
        """
        Compare the pricing details of this product instance with those of a
        newer instance of the same product.

        This comparison is meaningful primarily when the `new` argument
        represents the same product but in a different pricing state, such as
        after a price adjustment.

        Args:
            new (Product):
                The instance of the product to compare against. It should
                represent the same product at a different state or time.

        Returns:
            ProductPriceUpdateInfo:
                An object containing information about changes in pricing
                between this product and the provided product. It includes
                information on changes in full price, current price, discount
                rates, and flags indicating the start or end of a sale.
        """
        # Compare full prices
        if self.price_full > new.price_full:
            price_full_decrease = self.price_full - new.price_full
            price_full_increase = 0.0
        elif self.price_full < new.price_full:
            price_full_decrease = 0.0
            price_full_increase = new.price_full - self.price_full
        else:
            price_full_decrease = 0.0
            price_full_increase = 0.0
        # compare current prices
        if self.price_curr > new.price_curr:
            price_curr_decrease = self.price_curr - new.price_curr
            price_curr_increase = 0.0
        elif self.price_curr < new.price_curr:
            price_curr_decrease = 0.0
            price_curr_increase = new.price_curr - self.price_curr
        else:
            price_curr_decrease = 0.0
            price_curr_increase = 0.0
        # compare discount rates
        if self.discount_rate > new.discount_rate:
            discount_rate_decrease = self.discount_rate - new.discount_rate
            discount_rate_increase = 0.0
        elif self.discount_rate < new.discount_rate:
            discount_rate_decrease = 0.0
            discount_rate_increase = new.discount_rate - self.discount_rate
        else:
            discount_rate_decrease = 0.0
            discount_rate_increase = 0.0
        return ProductPriceUpdateInfo(
            price_full_decrease,
            price_full_increase,
            price_curr_decrease,
            price_curr_increase,
            discount_rate_decrease,
            discount_rate_increase,
            sale_started=(not self.is_on_sale and new.is_on_sale),
            sale_ended=(self.is_on_sale and not new.is_on_sale),
            )


@dataclass(frozen=True)
class ProductStockUpdateInfo:
    """
    Summarizes the details of stock quantity changes in a product,
    as determined by comparing two instances of this product.
    """
    stock_decrease: int = 0
    """
    Decrease in stock quantity, representing how many items
    are fewer in the new product compared to the old product.
    A value of 0 implies no decrease.
    """
    stock_increase: int = 0
    """
    Increase in stock quantity, indicating how many items
    are more in the new product compared to the old product.
    A value of 0 implies no increase.
    """
    stock_depleted: bool = False
    """
    A flag indicating complete depletion of the product stock.
    True if the new product's stock quantity is zero while the old
    product's stock was greater than zero.
    """
    stock_restocked: bool = False
    """
    A flag indicating the product has been restocked.
    True if the new product's stock quantity is greater than zero
    while the old product's stock was zero.
    """

    def as_dict(self) -> dict[str, typing.Union[int, bool]]:
        """
        Convert the stock update information to a dictionary. The behavior
        of this method is equivalent that of `dataclasses.asdict()`.

        Returns:
            dict[str, typing.Union[int, bool]]:
                A dictionary representation of the stock update information,
                with keys as attribute names and their corresponding values.
        """
        return asdict(self)


@dataclass(frozen=True)
class ProductPriceUpdateInfo:
    """
    Summarizes the details of pricing changes of a product,
    as determined by comparing two instances of this product.
    """
    price_full_decrease: float = 0.0
    """
    Decrease in the full price of the product, representing the difference
    between its old full price and its new full price. A value of 0.0 indicates
    no decrease.
    """
    price_full_increase: float = 0.0
    """
    Increase of the full price of the product, representing the difference
    between its new full price and its old full price. A value of 0.0 indicates
    no increase.
    """
    price_curr_decrease: float = 0.0
    """
    Decrease in the current selling price of the product, representing
    the difference between its old selling price and its new selling price.
    A value of 0.0 indicates no decrease.
    """
    price_curr_increase: float = 0.0
    """
    Increase in the current selling price of the product, representing
    the difference between its new selling price and its old selling price.
    A value of 0.0 indicates no increase.
    """
    discount_rate_decrease: float = 0.0
    """
    Decrease in the discount rate of the product, indicating the reduction
    of the discount rate in the new product compared to the old product.
    A value of 0.0 indicates that the discount rate has not decreased.
    """
    discount_rate_increase: float = 0.0
    """
    Increase in the discount rate of the product, indicating the increment
    of the discount rate in the new product compared to the old product.
    A value of 0.0 indicates that the discount rate has not increased.
    """
    sale_started: bool = False
    """
    A flag indicating whether a sale has started on the product.
    True if the new product is on sale and the old product was not.
    """
    sale_ended: bool = False
    """
    A flag indicating whether a sale has ended on the product.
    True if the new product is not on sale and the old product was.
    """

    def as_dict(self) -> dict[str, typing.Union[float, bool]]:
        """
        Convert the pricing update information to a dictionary. The behavior
        of this method is equivalent that of `dataclasses.asdict()`.

        Returns:
            dict[str, typing.Union[float, bool]]:
                A dictionary representation of the pricing update information,
                with keys as attribute names and their corresponding values.
        """
        return asdict(self)
