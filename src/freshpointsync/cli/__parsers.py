import argparse
import typing
import operator
import re
import shlex

from functools import lru_cache
from unidecode import unidecode

from ..product import Product


@lru_cache(maxsize=1024)
def format_str(s: typing.Any) -> str:
    return unidecode(s).strip().casefold()


class NumericParser:
    _pattern = re.compile(
        r"^\s*(<=|>=|<|=|==|>|!=)?\s*(\d+(\.\d*)?|\.\d+)\s*$"
        )
    _operators: dict[str, typing.Callable[[typing.Any, typing.Any], bool]] = {
        '<': operator.lt,
        '<=': operator.le,
        '==': operator.eq,
        '=': operator.eq,
        '!=': operator.ne,
        '>': operator.gt,
        '>=': operator.ge,
        }

    @classmethod
    def parse(
        cls, value: typing.Any, default_operator: str = '<'
    ) -> tuple[str, float]:
        match = cls._pattern.search(str(value))
        if match:
            operator_ = match.group(1)
            if not operator_:
                operator_ = default_operator
            number = match.group(2)
            return operator_, float(number)
        raise ValueError(f'Invalid parameter: "{value}"')

    @classmethod
    def add_operator(
        cls,
        operator_symbol: str,
        operator_: typing.Callable[[typing.Any, typing.Any], bool]
    ) -> None:
        cls._operators[operator_symbol] = operator_

    @classmethod
    def get_operator(
        cls, operator_symbol: str
    ) -> typing.Callable[[typing.Any, typing.Any], bool]:
        try:
            return cls._operators[operator_symbol]
        except KeyError:
            raise KeyError(f'Invalid operator: "{operator_symbol}"')


def positive_int(value: typing.Any) -> int:
    if not str(value).isdigit():
        raise ValueError(f'Value "{value}" is not a positive interger')
    value_int = int(value)
    if value_int <= 0:
        raise ValueError(f'Value "{value}" is not a positive interger')
    return value_int


def price(
    value: typing.Any
) -> tuple[typing.Callable[[typing.Any, typing.Any], bool], float]:
    operator, number = NumericParser.parse(value, default_operator='<=')
    return NumericParser.get_operator(operator), number


def count(
    value: typing.Any
) -> tuple[typing.Callable[[typing.Any, typing.Any], bool], float]:
    operator, number = NumericParser.parse(value, default_operator='>=')
    number_int = int(number)
    if number != number_int:
        raise ValueError(f'Value "{value}" is not a positive interger')
    return NumericParser.get_operator(operator), number_int


class CustomHelpFormatter(argparse.HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, max_help_position=48)


def get_arg_parser(
    add_location_arg: bool = True,
    add_interactive_arg: bool = True
) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="CLI parser for positional and optional arguments.",
        formatter_class=CustomHelpFormatter,
        )
    if add_location_arg:
        group_location = parser.add_mutually_exclusive_group()
        group_location.add_argument(
            'positional_location',
            nargs='?',
            type=positive_int,
            help="Product location (page ID)"
            )
        group_location.add_argument(
            '-l',
            '--location',
            type=positive_int,
            help="Product location (page ID) (alternative)"
            )
    group_name = parser.add_mutually_exclusive_group()
    group_name.add_argument(
        'positional_name',
        nargs='?',
        help="Product name"
        )
    group_name.add_argument(
        '-n',
        '--name',
        help="Product name (alternative)"
        )
    parser.add_argument(
        '-c',
        '--category',
        help="Product category"
        )
    parser.add_argument(
        '-q',
        '--quantity',
        type=count,
        help="Product availability (in pieces)"
        )
    parser.add_argument(
        '-p',
        '--price',
        type=price,
        help="Product price"
        )
    parser.add_argument(
        '-a',
        '--available',
        action='store_true',
        help="Product is currently in stock"
        )
    parser.add_argument(
        '-s',
        '--sale',
        action='store_true',
        help="Product is on sale"
        )
    parser.add_argument(
        '-g',
        '--glutenfree',
        action='store_true',
        help="Product is gluten free"
        )
    parser.add_argument(
        '-v',
        '--vegetarian',
        action='store_true',
        help="Product is vegetarian"
        )
    parser.add_argument(
        '-d',
        '--default',
        action='store_true',
        help=(
            "Set a default query (triggered when the program is invoked with "
            "no arguments)"
            )
        )
    if add_interactive_arg:
        parser.add_argument(
            '-i',
            '--interactive',
            action='store_true',
            help="Start an interactive session"
            )
    return parser


def get_opt_args(parser: argparse.ArgumentParser) -> list[tuple[str, str]]:
    opt_args = []
    for action in parser._actions:
        if action.option_strings:
            short, full = action.option_strings
            opt_args.append((short, full))
    return opt_args


def parse_args(
    parser: argparse.ArgumentParser, args: typing.Optional[str] = None
) -> typing.Optional[argparse.Namespace]:
    try:
        if args is None:
            return parser.parse_args()
        return parser.parse_args(shlex.split(args))
    except SystemExit:
        raise
        return None


def get_constaints(
    args: argparse.Namespace
) -> list[typing.Callable[[Product], bool]]:
    constaints: list[typing.Callable[[Product], bool]] = []
    if args.positional_name or args.name:
        name = args.positional_name or args.name
        constaints.append(lambda p: format_str(name) in p.name_ascii)
    if args.category:
        category = args.category
        constaints.append(lambda p: format_str(category) in p.category_ascii)
    if args.quantity:
        quantity_operator, quantity = args.quantity
        constaints.append(lambda p: quantity_operator(p.count, quantity))
    if args.price:
        price_operator, price = args.price
        constaints.append(lambda p: price_operator(p.price_curr, price))
    if args.available:
        constaints.append(lambda p: p.is_available)
    if args.sale:
        constaints.append(lambda p: p.is_on_sale)
    if args.glutenfree:
        constaints.append(lambda p: p.is_gluten_free)
    if args.vegetarian:
        constaints.append(lambda p: p.is_vegetarian)
    return constaints
