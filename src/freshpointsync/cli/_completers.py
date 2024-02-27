import shlex
import typing

from prompt_toolkit.completion import (
    Completer, Completion, CompleteEvent
)
from prompt_toolkit.document import Document
from unidecode import unidecode

from ._parsers import QueryParser
from ..product import Product


def format_str(s: typing.Any) -> str:
    return unidecode(s).strip().casefold()


class QueryCompleter(Completer):

    def __init__(self, products: typing.Iterable[Product]) -> None:
        self.positional_name_encountered: bool = False
        self.product_names: dict[str, str] = {
            p.name_ascii: p.name for p in products
            }
        self.product_categories: dict[str, str] = {
            p.category_ascii: p.category for p in products
            }
        parser = QueryParser(add_arg_interactive=False, add_arg_location=False)
        self.commands: dict[str, str] = {
            short: full for short, full in parser.optional_arg_names
            }

    def yield_command(self, text: str):
        for short, full in self.commands.items():
            if text in short or text in full:
                start_position = -len(text)
                if text == full:
                    start_position = start_position - 1
                yield Completion(
                    full,
                    start_position=start_position,
                    display=full,
                    )

    def yield_name(self, text: str):
        for name_ascii in self.product_names:
            if text.strip('\'"') in name_ascii:
                name = self.product_names[name_ascii]
                yield Completion(
                    f'"{name}"',
                    start_position=-len(text),
                    display=name,
                    )

    def yield_category(self, text: str):
        for category_ascii in self.product_categories:
            if text.strip('\'"') in category_ascii:
                category = self.product_categories[category_ascii]
                yield Completion(
                    f'"{category}"',
                    start_position=-len(text),
                    display=category
                    )

    def yield_completions(self, text: str, text_prev: str = ''):
        if text_prev and text_prev.startswith('-'):
            if text_prev in ['-n', '--name']:
                yield from self.yield_name(text)
            elif text_prev in ['-c', '--category']:
                yield from self.yield_category(text)
        elif text.startswith('-'):
            yield from self.yield_command(text)
        else:
            if self.positional_name_encountered:
                return
            yield from self.yield_name(text)

    def parse_text(self, text: str) -> tuple[str, str]:
        if not text:
            return '', ''
        appended_quote = False
        text_formatted = format_str(text)
        try:
            args = shlex.split(text_formatted, posix=False)
        except ValueError:
            try:
                args = shlex.split(f'{text_formatted}"', posix=False)
                appended_quote = True
            except ValueError:
                try:
                    args = shlex.split(f'{text_formatted}\'', posix=False)
                    appended_quote = True
                except Exception:  # should not happen
                    args = ['', '']
        try:
            arg_last, arg_prev = args[-1], args[-2]
            self.positional_name_encountered = True
        except IndexError:
            arg_last, arg_prev = args[-1], ''
            if text.endswith(' '):
                self.positional_name_encountered = True
            else:
                self.positional_name_encountered = False
        if appended_quote:
            arg_last = arg_last[:-1]
        if text.endswith(' '):
            arg_last, arg_prev = '', arg_last
        return arg_last, arg_prev

    def get_completions(self, document: Document, event: CompleteEvent):
        arg_last, arg_prev = self.parse_text(document.text_before_cursor)
        yield from self.yield_completions(arg_last, arg_prev)
