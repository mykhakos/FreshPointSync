import datetime

from rich.table import Table, box
from rich.text import Text
from rich.style import Style
from rich.padding import Padding

from ._colors import HexColorPallete
from ..product import Product


class QueryResultTable:

    def __init__(self) -> None:
        self.table = self._construct()

    @staticmethod
    def _construct() -> Table:
        now = datetime.datetime.now().strftime("%Y/%m/%d, %H:%M:%S")
        table = Table(
            title=f'Query results {now}',
            show_header=True,
            header_style="bold white",
            expand=True,
            )
        table.add_column("Name", ratio=4)
        table.add_column("Category", ratio=2)
        table.add_column("Price", ratio=1)
        table.add_column("Quantity", ratio=1)
        table.box = box.ASCII2
        return table

    @property
    def is_empty(self) -> bool:
        return self.table.row_count == 0

    @staticmethod
    def format_name(product: Product) -> Text:
        if product.is_sold_out:
            style = Style(color=HexColorPallete.GRAY_DARK.value)
        elif product.is_last_piece:
            style = Style(color=HexColorPallete.WHITE.value)
        else:
            style = Style(color=HexColorPallete.WHITE.value)
        return Text(product.name, style=style)

    @staticmethod
    def format_category(product: Product) -> Text:
        style = Style(color=HexColorPallete.WHITE.value)
        return Text(product.category, style=style)

    @staticmethod
    def format_price(product: Product) -> Text:
        if product.is_on_sale:
            discount = int(round(product.discount_rate * 100))
            text = f'{product.price_curr:.02f} CZK (-{discount}%)'
            style = Style(color=HexColorPallete.FRESHPOINT_VIBRANT.value)
        else:
            text = f'{product.price_curr:.02f} CZK'
            style = Style(color=HexColorPallete.WHITE.value)
        return Text(text, style=style)

    @staticmethod
    def format_quantity(product: Product) -> Text:
        if product.is_sold_out:
            style = Style(color=HexColorPallete.RED.value)
        elif product.is_last_piece:
            style = Style(color=HexColorPallete.YELLOW.value)
        else:
            style = Style(color=HexColorPallete.FRESHPOINT_VIBRANT.value)
        return Text(str(product.count), style=style)

    def add_row(self, product: Product, end_section: bool = False) -> None:
        padding = (0, 0, 0, 0) if end_section else (0, 0, 1, 0)  # t, r, b, l
        self.table.add_row(
            Padding(self.format_name(product), padding),
            Padding(self.format_category(product), padding),
            Padding(self.format_price(product), padding),
            Padding(self.format_quantity(product), padding),
            end_section=end_section,
            )

    def add_rows(self, products: list[Product]) -> None:
        if not products:
            return
        end_section = False
        for i, product in enumerate(products[:-1]):
            product_next = products[i + 1]
            end_section = (product.category != product_next.category)
            self.add_row(product, end_section)
        self.add_row(product=products[-1], end_section=True)


class QueryNoResultTable:
    def __init__(self) -> None:
        self.table = self._construct()

    @staticmethod
    def _construct() -> Table:
        now = datetime.datetime.now().strftime("%Y/%m/%d, %H:%M:%S")
        table = Table(
            title=f'Query results {now}',
            show_header=False,
            expand=True,
            )
        text = Text(
            'No products found. Please try a different query.',
            style=Style(color=HexColorPallete.RED.value),
            justify="center"
            )
        table.add_row(text)
        table.box = box.ASCII2
        return table
