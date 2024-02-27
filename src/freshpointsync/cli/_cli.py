import argparse
import asyncio
import json
import os
# import logging
import typing


from rich.console import Console
from rich.padding import Padding
from rich.progress import Progress
from prompt_toolkit import PromptSession
from prompt_toolkit.patch_stdout import patch_stdout
from prompt_toolkit.lexers import PygmentsLexer
from prompt_toolkit.styles import merge_styles, Style
from prompt_toolkit.history import FileHistory
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.auto_suggest import AutoSuggestFromHistory
from prompt_toolkit.styles.pygments import style_from_pygments_cls

from pygments.styles.monokai import MonokaiStyle  # type: ignore
from pygments.lexers.shell import FishShellLexer  # type: ignore

from ._colors import HexColorPallete
from ._query_table import QueryResultTable, QueryNoResultTable
from ._completers import QueryCompleter
from ._parsers import QueryParser, get_constaints
from ..page import FreshPointProductPage


console = Console()


def get_history_file_path():
    return os.path.join(os.path.dirname(__file__), ".history")


def get_settings_file_path():
    return os.path.join(os.path.dirname(__file__), "settings.json")


async def refresh_page_visual(page: FreshPointProductPage) -> None:
    task = asyncio.create_task(page.update())
    with Progress(transient=True) as progress:
        progress_bar = progress.add_task(
            description=f"Fetching page: {page.url}...",
            total=100
            )
        while not task.done():
            progress.update(progress_bar, advance=4)
            await asyncio.sleep(0.1)
        if not progress.finished:
            progress.update(progress_bar, advance=100)
    await task


async def start_page_session(location_id: int) -> FreshPointProductPage:
    page = FreshPointProductPage(location_id)
    await page.start_session()
    await refresh_page_visual(page)
    asyncio.create_task(page.update_forever(5))
    return page


def build_query_table(
    page: FreshPointProductPage, query_args: argparse.Namespace
) -> typing.Union[QueryResultTable, QueryNoResultTable]:
    constaints = get_constaints(query_args)
    products = page.find_products(
        constraint=lambda p: all(constr(p) for constr in constaints)
        )
    if not products:
        return QueryNoResultTable()
    table = QueryResultTable()
    table.add_rows(products)
    return table


def process_query(
    page: FreshPointProductPage,
    parser: QueryParser,
    query_args: argparse.Namespace,
) -> None:
    table = build_query_table(page, query_args)
    console.print(Padding(table.table, 1))
    if query_args.default:
        parser.set_default_args(query_args)


async def cli_interactive(
    page: FreshPointProductPage,
) -> None:
    parser = QueryParser(
        add_arg_interactive=False,
        add_arg_location=False,
        )
    style = merge_styles(
        [
            style_from_pygments_cls(MonokaiStyle),
            Style.from_dict(
                {
                    'default':
                        HexColorPallete.WHITE.value,
                    'program_name':
                        f'{HexColorPallete.FRESHPOINT_MAIN.value} bold',
                    'at':
                        HexColorPallete.WHITE.value,
                    'location':
                        f'{HexColorPallete.YELLOW.value} bold',
                    'prompt_arrow':
                        HexColorPallete.WHITE.value,
                    'completion-menu.completion':
                        f'bg:{HexColorPallete.GRAY_DARK.value} '
                        f'fg:{HexColorPallete.GRAY.value}',
                    'completion-menu.completion.current':
                        f'bg:{HexColorPallete.WHITE.value} '
                        f'fg:{HexColorPallete.FRESHPOINT_MAIN.value}',
                    'scrollbar.background':
                        f'bg:{HexColorPallete.FRESHPOINT_DARK.value}',
                    'scrollbar.button':
                        f'bg:{HexColorPallete.GRAY.value}',
                }
            ),
        ]
    )
    prompt_text = FormattedText(
        [
            ('class:program_name', 'FreshPointSync'),
            ('class:at', '@'),
            ('class:location', page.location_name),
            ('class:prompt_arrow', '> '),
        ]
    )
    session: PromptSession = PromptSession(
        completer=QueryCompleter(page.products),
        lexer=PygmentsLexer(FishShellLexer),
        style=style,
        history=FileHistory(get_history_file_path()),
        auto_suggest=AutoSuggestFromHistory()
        )
    while True:
        # get the prompt response
        with patch_stdout():
            response = await session.prompt_async(prompt_text)
        # parse the response
        args = parser.parse_args_safe(
            QueryParser.split_args_str(response), exit_on_error=False
            )
        if args is None:
            continue
        process_query(page, parser, args)


class PageNotFoundException(Exception):
    pass


def get_last_location() -> typing.Optional[int]:
    path = get_settings_file_path()
    if not os.path.exists(path):
        return None
    with open(path, 'r', encoding='utf-8') as file:
        data = json.load(file)
    return data.get('last_location')


def set_last_location(location: typing.Optional[int]) -> None:
    path = get_settings_file_path()
    if os.path.exists(path):
        with open(path, 'r', encoding='utf-8') as file:
            data = json.load(file)
        data['last_location'] = location
        with open(path, 'w', encoding='utf-8') as file:
            json.dump(data, file)
    else:
        with open(path, 'w', encoding='utf-8') as file:
            json.dump({'last_location': location}, file)


async def main() -> None:
    try:
        parser = QueryParser(
            add_arg_location=True,
            add_arg_interactive=True,
            )
        args = parser.parse_args()
        location = args.location or get_last_location()
        if not location:
            message = 'Page location ID is not set.'
            raise PageNotFoundException(message)
        else:
            set_last_location(location)
        page = await start_page_session(location)
        if not page.location_name:
            message = f'Page {page.url} is not accessible.'
            raise PageNotFoundException(message)
        if args.interactive:
            await cli_interactive(page)
        else:
            process_query(page, parser, args)
    except (KeyboardInterrupt, asyncio.CancelledError):
        pass
    except PageNotFoundException as e:
        console.print(e)
    except Exception as e:
        console.print(f'Exception occured: {e}')
    finally:
        try:
            await page.close_session()
        except UnboundLocalError:
            pass
