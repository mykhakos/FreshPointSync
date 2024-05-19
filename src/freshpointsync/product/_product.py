from __future__ import annotations

import time
import typing

from dataclasses import dataclass
from pydantic import (
    BaseModel, ConfigDict, Field, NonNegativeFloat, NonNegativeInt
)
from pydantic.alias_generators import to_camel
from unidecode import unidecode


DEFAULT_PIC_URL = (
    r"https://images.weserv.nl/?url=http://freshpoint.freshserver.cz/"
    r"backend/web/media/photo/1_f587dd3fa21b22.jpg"
)
"""Default picture URL for a product.
The URL points to an image hosted on the FreshPoint server.
"""


class Product(BaseModel):
    """Represents a FreshPoint.cz web page product with various attributes.

    Args:
        id_ (int):
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
        location (str):
            Name of the product location. Defaults to an empty string value.
        timestamp (int):
            Timestamp of the product instance initialization.
            Defaults to the time of instantiation.
    """
    model_config = ConfigDict(
        alias_generator=to_camel,
        populate_by_name=True,
        validate_assignment=True,
        )

    id_: int = Field(serialization_alias='id', validation_alias='id')
    """Unique identifier or the product."""
    name: str = Field(default='')
    """Name of the product."""
    category: str = Field(default='')
    """Category of the product."""
    is_vegetarian: bool = Field(default=False)
    """Indicates if the product is vegetarian."""
    is_gluten_free: bool = Field(default=False)
    """Indicates if the product is gluten-free."""
    quantity: NonNegativeInt = Field(default=0)
    """Quantity of product items in stock."""
    price_full: NonNegativeFloat = Field(default=0.0)
    """Full price of the product."""
    price_curr: NonNegativeFloat = Field(default=0.0)
    """Current selling price of the product."""
    pic_url: str = Field(default=DEFAULT_PIC_URL)
    """URL of the product image."""
    location_id: int = Field(default=0)
    """Unique identifier of the product page URL."""
    location: str = Field(default='')
    """Name of the product location."""
    timestamp: float = Field(default_factory=time.time)
    """Timestamp of the product creation."""

    def model_post_init(self, __context) -> None:
        fields_set = self.model_fields_set
        if 'price_full' not in fields_set and 'price_curr' not in fields_set:
            self.price_full = 0.0
            self.price_curr = 0.0
        elif 'price_full' not in fields_set and 'price_curr' in fields_set:
            self.price_full = self.price_curr
        elif 'price_curr' not in fields_set and 'price_full' in fields_set:
            self.price_curr = self.price_full

    @property
    def name_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the product name."""
        return unidecode(self.name.strip()).casefold()

    @property
    def category_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the product category."""
        return unidecode(self.category.strip()).casefold()

    @property
    def location_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the product location name."""
        return unidecode(self.location.strip()).casefold()

    @property
    def discount_rate(self) -> float:
        """Discount rate (<0; 1>) of the product, calculated based on
        the difference between the full price and the current selling price.
        """
        if self.price_full == 0 or self.price_full < self.price_curr:
            return 0
        return round((self.price_full - self.price_curr) / self.price_full, 2)

    @property
    def is_on_sale(self) -> bool:
        """A product is considered on sale if
        its current selling price is lower than its full price.
        """
        return self.price_curr < self.price_full

    @property
    def is_available(self) -> bool:
        """A product is considered available if
        its quantity is greater than zero.
        """
        return self.quantity != 0

    @property
    def is_sold_out(self) -> bool:
        """A product is considered available if its quantity equals zero."""
        return self.quantity == 0

    @property
    def is_last_piece(self) -> bool:
        """A product is considered available if its quantity equals one."""
        return self.quantity == 1

    def is_newer_than(self, other: Product) -> bool:
        """Determine if this product is newer that the given one by
        comparing their creation timestamps.

        Args:
            other (Product): The product to compare against.

        Returns:
            bool: True if this product is newer than the other product,
                False otherwise.
        """
        return self.timestamp > other.timestamp

    def diff(self, other: Product, **kwargs) -> dict[str, DiffValueTuple]:
        """Compare this product with another to identify differences,
        excluding the creation timestamps.

        Args:
            other (Product): The product to compare against.

        Returns:
            dict[str, DiffValue]: A dictionary with keys as attribute names and
                values as namedtuples containing the differing values between
                this product and the other product.
        """
        # get self's and other's data and remove the timestamps
        self_asdict = self.model_dump(**kwargs)
        other_asdict = other.model_dump(**kwargs)
        # compare self to other
        diff: dict[str, DiffValueTuple] = {}
        for attr, value in self_asdict.items():
            other_value = other_asdict.get(attr, None)
            if value != other_value:
                diff[attr] = DiffValueTuple(value, other_value)
        # compare other to self (may be relevant for subclasses)
        for attr, value in other_asdict.items():
            if attr not in self_asdict:
                diff[attr] = DiffValueTuple(None, value)
        return diff

    def compare_quantity(self, new: Product) -> ProductQuantityUpdateInfo:
        """Compare the stock quantity of this product instance with the one of
        a newer instance of the same product.

        This comparison is meaningful primarily when the `new` argument
        represents the same product at a different state or time, such as
        after a stock update.

        Args:
            new (Product): The instance of the product to compare against. It
                should represent the same product at a different state or time.

        Returns:
            ProductStockUpdateInfo: An object containing information about
                changes in stock quantity of this product when compared to
                the provided product. It provides insights into changes in
                stock quantity, such as decreases, increases, depletion, or
                restocking.
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
        return ProductQuantityUpdateInfo(
            decrease,
            increase,
            depleted,
            restocked
            )

    def compare_price(self, new: Product) -> ProductPriceUpdateInfo:
        """Compare the pricing details of this product instance with those of
        a newer instance of the same product.

        This comparison is meaningful primarily when the `new` argument
        represents the same product but in a different pricing state, such as
        after a price adjustment.

        Args:
            new (Product): The instance of the product to compare against. It
                should represent the same product at a different state or time.

        Returns:
            ProductPriceUpdateInfo: An object containing information about
                changes in pricing between this product and the provided
                product. It includes information on changes in full price,
                current price, discount rates, and flags indicating the start
                or end of a sale.
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


class DiffValueTuple(typing.NamedTuple):
    """Holds differing attribute values between two products."""
    value_self: typing.Any
    """Value of the attribute in the first product."""
    value_other: typing.Any
    """Value of the attribute in the second product."""


@dataclass(frozen=True)
class ProductQuantityUpdateInfo:
    """Summarizes the details of stock quantity changes in a product,
    as determined by comparing two instances of this product.
    """
    stock_decrease: int = 0
    """Decrease in stock quantity, representing how many items
    are fewer in the new product compared to the old product.
    A value of 0 implies no decrease.
    """
    stock_increase: int = 0
    """Increase in stock quantity, indicating how many items
    are more in the new product compared to the old product.
    A value of 0 implies no increase.
    """
    stock_depleted: bool = False
    """A flag indicating complete depletion of the product stock.
    True if the new product's stock quantity is zero while the old
    product's stock was greater than zero.
    """
    stock_restocked: bool = False
    """A flag indicating the product has been restocked.
    True if the new product's stock quantity is greater than zero
    while the old product's stock was zero.
    """


@dataclass(frozen=True)
class ProductPriceUpdateInfo:
    """Summarizes the details of pricing changes of a product,
    as determined by comparing two instances of this product.
    """
    price_full_decrease: float = 0.0
    """Decrease in the full price of the product, representing the difference
    between its old full price and its new full price.
    A value of 0.0 indicates no decrease.
    """
    price_full_increase: float = 0.0
    """Increase of the full price of the product, representing the difference
    between its new full price and its old full price.
    A value of 0.0 indicates no increase.
    """
    price_curr_decrease: float = 0.0
    """Decrease in the current selling price of the product, representing
    the difference between its old selling price and its new selling price.
    A value of 0.0 indicates no decrease.
    """
    price_curr_increase: float = 0.0
    """Increase in the current selling price of the product, representing
    the difference between its new selling price and its old selling price.
    A value of 0.0 indicates no increase.
    """
    discount_rate_decrease: float = 0.0
    """Decrease in the discount rate of the product, indicating the reduction
    of the discount rate in the new product compared to the old product.
    A value of 0.0 indicates that the discount rate has not decreased.
    """
    discount_rate_increase: float = 0.0
    """Increase in the discount rate of the product, indicating the increment
    of the discount rate in the new product compared to the old product.
    A value of 0.0 indicates that the discount rate has not increased.
    """
    sale_started: bool = False
    """A flag indicating whether a sale has started on the product.
    True if the new product is on sale and the old product was not.
    """
    sale_ended: bool = False
    """A flag indicating whether a sale has ended on the product.
    True if the new product is not on sale and the old product was.
    """
