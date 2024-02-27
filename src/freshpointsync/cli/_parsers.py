import argparse
import json
import operator
import os
import sys
import re
import shlex
import typing

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


class QueryParserDefaultNamespace:
    def __init__(
        self, values: typing.Optional[typing.Mapping[str, typing.Any]] = None
    ) -> None:
        self._values = dict(values) if values else {}

    @classmethod
    def from_file(cls, filepath: str) -> 'QueryParserDefaultNamespace':
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as file:
                data = json.load(file)
            return cls(data)
        else:
            with open(filepath, 'w', encoding='utf-8') as file:
                json.dump({}, file)
            return cls({})

    def get(self) -> argparse.Namespace:
        return argparse.Namespace(**self._values)

    def set(self, args: dict[str, typing.Any]) -> None:
        for key, value in args.items():
            self._values[key] = value

    def to_dict(self) -> dict[str, typing.Any]:
        return dict(self._values)

    def to_file(self, filepath: str) -> None:
        with open(filepath, 'w', encoding='utf-8') as file:
            json.dump(self._values, file, indent=4)


class QueryParserHelpFormatter(argparse.HelpFormatter):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs, max_help_position=48)


class QueryParser(argparse.ArgumentParser):
    DEFAULT_QUERY_FILE_PATH = (
        os.path.join(os.path.dirname(__file__), "default_query.json")
        )

    def __init__(
        self,
        add_arg_location: bool = True,
        add_arg_interactive: bool = True,
        **kwargs
    ) -> None:
        path = self.DEFAULT_QUERY_FILE_PATH
        self._default_args = QueryParserDefaultNamespace.from_file(path)
        kwargs = self._format_kwargs(kwargs)
        super().__init__(**kwargs)
        self._set_args(add_arg_location, add_arg_interactive)
        self._add_arg_location = add_arg_location
        self._add_arg_interactive = add_arg_interactive

    @classmethod
    def _format_kwargs(cls, kwargs: dict) -> dict:
        if 'description' not in kwargs:
            description = "CLI parser for positional and optional arguments."
            kwargs['description'] = description
        if 'formatter_class' not in kwargs:
            formatter_class = QueryParserHelpFormatter
            kwargs['formatter_class'] = formatter_class
        return kwargs

    def _set_args(
        self,
        add_arg_location: bool = True,
        add_arg_interactive: bool = True
    ) -> None:
        group_name = self.add_mutually_exclusive_group()
        group_name.add_argument(
            'positional_name',
            nargs='?',
            help="Product name"
            )
        if add_arg_location:
            group_location = self.add_mutually_exclusive_group()
            group_location.add_argument(
                'positional_location',
                nargs='?',
                type=positive_int,
                help="Product location (page ID)"
                )
        group_name.add_argument(
            '-n',
            '--name',
            help="Product name (alternative)"
            )
        if add_arg_location:
            group_location.add_argument(
                '-l',
                '--location',
                type=positive_int,
                help="Product location (page ID) (alternative)"
                )
        self.add_argument(
            '-c',
            '--category',
            help="Product category"
            )
        self.add_argument(
            '-q',
            '--quantity',
            type=count,
            help="Product availability (in pieces)"
            )
        self.add_argument(
            '-p',
            '--price',
            type=price,
            help="Product price"
            )
        self.add_argument(
            '-a',
            '--available',
            action='store_true',
            help="Product is currently in stock"
            )
        self.add_argument(
            '-s',
            '--sale',
            action='store_true',
            help="Product is on sale"
            )
        self.add_argument(
            '-g',
            '--glutenfree',
            action='store_true',
            help="Product is gluten free"
            )
        self.add_argument(
            '-v',
            '--vegetarian',
            action='store_true',
            help="Product is vegetarian"
            )
        self.add_argument(
            '-d',
            '--default',
            action='store_true',
            help=(
                "Set a default query (triggered when the program "
                "is invoked with no arguments)"
                )
            )
        if add_arg_interactive:
            self.add_argument(
                '-i',
                '--interactive',
                action='store_true',
                help="Start an interactive session"
                )

    @property
    def default_args(self) -> argparse.Namespace:
        return self._default_args.get()

    def set_default_args(self, args: argparse.Namespace) -> None:
        args_dict = vars(args)
        if self._add_arg_location is False and 'location' in args_dict:
            del args_dict['location']
        if self._add_arg_interactive is False and 'interactive' in args_dict:
            del args_dict['interactive']
        self._default_args.set(args_dict)
        self._default_args.to_file(self.DEFAULT_QUERY_FILE_PATH)

    @property
    def optional_arg_names(self) -> list[tuple[str, str]]:
        optional_args = []
        for action in self._actions:
            if action.option_strings:
                short, full = action.option_strings
                optional_args.append((short, full))
        return optional_args

    @staticmethod
    def split_args_str(args: str) -> list[str]:
        try:
            return shlex.split(args)
        except ValueError:
            try:
                return shlex.split(f'{args}"')
            except ValueError:
                try:
                    return shlex.split(f'{args}\'')
                except Exception:  # should not happen
                    return []

    def parse_args_safe(
        self,
        args: typing.Optional[typing.Sequence[str]] = None,
        exit_on_error: bool = False
    ) -> typing.Optional[argparse.Namespace]:
        try:
            if args is None:
                if len(sys.argv) < 2:
                    return self.default_args
                return super().parse_args()
            elif not args:
                return self.default_args
            return super().parse_args(args)
        except SystemExit as err:
            if exit_on_error:
                raise err
            else:
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
