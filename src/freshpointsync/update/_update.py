import asyncio
import functools
import inspect
import logging
import sys
from dataclasses import dataclass
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Set,
    TypedDict,
    TypeGuard,
    TypeVar,
    Union,
    get_type_hints,
    overload,
)

from freshpointparser.models import BaseItem, BasePage
from freshpointparser.models.types import DiffType, ModelDiff, ModelDiffMapping

from .._callable_runner import CallableRunner, is_run_safe

if sys.version_info >= (3, 10):
    from typing import TypeAlias, TypeGuard
else:
    from typing_extensions import TypeAlias, TypeGuard

if sys.version_info >= (3, 11):
    from typing import Unpack
else:
    from typing_extensions import Unpack


logger = logging.getLogger('freshpointsync.update')


_NO_DEFAULT = object()
"""Sentinel value for the ``default`` argument of ``getattr()``."""


def is_async_consumer(
    consumer: object,
) -> TypeGuard[Callable[..., Awaitable[Any]]]:
    while isinstance(consumer, functools.partial):
        consumer = consumer.func
    logger.info('Validating consumer "%r"', consumer)
    try:
        is_async = inspect.iscoroutinefunction(consumer)
        if not is_async:
            call_method = getattr(consumer, '__call__', None)  # noqa: B004
            if call_method is not None:
                is_async = inspect.iscoroutinefunction(call_method)
        logger.info('Is asynchronous: %s', is_async)
        return is_async
    except Exception as e:
        logger.warning('Failed to validate consumer %r: %s', consumer, e)
        return False


def is_valid_consumer(consumer: object) -> TypeGuard[Callable[[Any], Any]]:
    """True if the object can be called with exactly one argument."""
    while isinstance(consumer, functools.partial):
        consumer = consumer.func
    logger.info('Validating consumer "%r"', consumer)

    if not callable(consumer):
        logger.info('Not callable: %r', consumer)
        return False
    logger.info('Is callable')

    try:
        signature = inspect.signature(consumer)
        try:
            # Try binding one positional argument
            signature.bind(object())
            logger.info('Accepts one argument')
            return True
        except TypeError as e:
            logger.info('Does not accept one argument: %s', e)
            return False
    except (ValueError, TypeError) as e:
        logger.warning('Cannot inspect signature for %r: %s', consumer, e)
        return False


def is_valid_handler(handler: object) -> bool:
    return is_valid_consumer(handler)


def is_valid_filter(filter_: object) -> bool:
    if not is_valid_consumer(filter_):
        return False

    try:
        globalns = vars(sys.modules[filter_.__module__])
        type_hints = get_type_hints(filter_, globalns=globalns)
        return_type = type_hints.get('return', None)

        if return_type is None:
            logger.warning(
                'Consumer %r has no return type annotation. '
                'Assuming it returns a boolean.',
                filter_,
            )
            return True

        if return_type is bool:
            logger.info('Returns bool')
            return True

        logger.info('Return type is not bool: %r', return_type)
        return False

    except Exception as e:
        logger.warning('Failed to get return type for %r: %s', filter_, e)
        return False


T = TypeVar('T')
TItem = TypeVar('TItem', bound=BaseItem)
TPage = TypeVar('TPage', bound=BasePage)


@dataclass(frozen=True)
class ItemUpdateContext(Generic[TItem]):
    item_new: Optional[TItem]
    item_old: Optional[TItem]
    item_diff: ModelDiff
    context: dict[str, Any]

    @property
    def is_item_created(self) -> bool:
        """Check if the item was created."""
        return self.item_diff['type'] == DiffType.CREATED

    @property
    def is_item_deleted(self) -> bool:
        """Check if the item was deleted."""
        return self.item_diff['type'] == DiffType.DELETED

    @property
    def is_item_updated(self) -> bool:
        """Check if the item was updated."""
        return self.item_diff['type'] == DiffType.UPDATED

    def get_item_attr_diff_type(self, attr: str) -> Optional[DiffType]:
        """Check if a specific attribute of the item was updated."""
        return self.item_diff['diff'].get(attr, {}).get('type', None)

    @overload
    def get_item_attr(self, attr: str) -> Any: ...

    @overload
    def get_item_attr(self, attr: str, default: T) -> Union[Any, T]: ...

    def get_item_attr(self, attr: str, default: T = _NO_DEFAULT) -> Union[Any, T]:
        """Retrieve a specific attribute from the item state data."""
        if self.item_new:
            value = getattr(self.item_new, attr, _NO_DEFAULT)
            if value is not _NO_DEFAULT:
                return value
        if self.item_old:
            value = getattr(self.item_old, attr, _NO_DEFAULT)
            if value is not _NO_DEFAULT:
                return value
        if default is not _NO_DEFAULT:
            return default
        raise AttributeError(
            f'Attribute "{attr}" was not found neither in the new item of type '
            f'"{type(self.item_new).__name__}" nor in the old item of type '
            f'"{type(self.item_old).__name__}".'
        )


@dataclass(frozen=True)
class PageUpdateContext(Generic[TPage]):
    page_new: Optional[TPage]
    page_old: Optional[TPage]
    page_diff: ModelDiffMapping
    context: dict[str, Any]


UpdateConsumerAsync: TypeAlias = Callable[[Any], Coroutine[Any, Any, T]]
UpdateConsumerSync: TypeAlias = Callable[[Any], T]
UpdateConsumer: TypeAlias = Union[UpdateConsumerAsync[T], UpdateConsumerSync[T]]

Filter = UpdateConsumer[bool]
Handler = UpdateConsumer[Any]


@dataclass
class UpdateConsumerMeta:
    is_async: bool
    run_safe: bool


class HandlerExecParams(TypedDict, total=False):
    run_once: bool
    """A flag indicating whether the handler should be discarded after its first
    execution.
    """
    await_for: bool
    """A flag indicating whether the handler should be awaited for after its
    execution.
    """


class UpdateConsumerRegistry:
    """Registry for update consumers (handlers and filters).

    This class manages subscriptions and unsubscriptions of handlers and filters,
    allowing them to be executed based on the update context.
    """

    def __init__(self) -> None:
        self._filters: Dict[Filter, UpdateConsumerMeta] = {}
        self._handlers: Dict[Handler, UpdateConsumerMeta] = {}
        self._handler_exec_params: Dict[Handler, HandlerExecParams] = {}
        self._handlers_to_filters: Dict[Handler, Set[Filter]] = {}

    @staticmethod
    def _get_consumers_meta(
        consumers: Union[UpdateConsumer, Iterable[UpdateConsumer], None],
    ) -> Dict[UpdateConsumer, UpdateConsumerMeta]:
        if not consumers:
            return {}
        if not isinstance(consumers, Iterable):
            consumers = (consumers,)
        return {
            consumer: UpdateConsumerMeta(
                is_async=is_async_consumer(consumer),
                run_safe=is_run_safe(consumer),  # type: ignore[arg-type]
            )
            for consumer in consumers
        }

    def subscribe(
        self,
        handler: Union[Handler, Iterable[Handler]],
        filter_: Union[Filter, Iterable[Filter], None] = None,
        **kwargs: Unpack[HandlerExecParams],
    ) -> None:
        handlers = self._get_consumers_meta(handler)
        if not handlers:  # nothing to subscribe
            return
        filters = self._get_consumers_meta(filter_)
        self._filters.update(filters)
        for hdlr, hdlr_meta in handlers.items():
            self._handlers[hdlr] = hdlr_meta
            hdlr_fltrs = self._handlers_to_filters.setdefault(hdlr, set())
            hdlr_fltrs.update(filters.keys())
            self._handler_exec_params[hdlr] = kwargs

    def unsubscribe(
        self,
        handler: Union[Handler, Iterable[Handler]],
    ) -> None:
        handlers = self._get_consumers_meta(handler)
        if not handlers:  # nothing to unsubscribe
            return
        for hdlr in handlers:
            self._handlers.pop(hdlr, None)
            self._handler_exec_params.pop(hdlr, None)
            self._handlers_to_filters.pop(hdlr, None)

        # remove filters that are not used by any handler
        fltrs_in_use = (  # flatten to a single set
            set().union(*self._handlers_to_filters.values())
            if self._handlers_to_filters
            else set()
        )
        for fltr in tuple(self._filters):  # copy to prevent mutation
            if fltr not in fltrs_in_use:
                self._filters.pop(fltr, None)


class UpdatePublisher:
    def __init__(
        self,
        registry: Optional[UpdateConsumerRegistry] = None,
        runner: Optional[CallableRunner] = None,
    ) -> None:
        self._registry = registry or UpdateConsumerRegistry()
        self._runner = runner or CallableRunner()

    async def post(self, update_context: object) -> None:
        fltr_futures: Dict[UpdateConsumer, asyncio.Future[Optional[bool]]] = {}
        fltr_results: Dict[UpdateConsumer, Optional[bool]] = {}
        for fltr, meta in self._registry._filters.items():
            fut = self._runner.run(
                fltr,
                update_context,
                run_async=meta.is_async,
                run_safe=meta.run_safe,
            )
            fltr_futures[fltr] = fut

        hdlr_futures_to_await: List[asyncio.Future[Any]] = []
        hdlrs_to_unsubscribe = set()
        for hdlr, meta in self._registry._handlers.items():
            fltrs_passed = True

            fltrs = self._registry._handlers_to_filters.get(hdlr, set())
            for fltr in fltrs:
                if fltr not in fltr_results:
                    fltr_results[fltr] = await fltr_futures.pop(fltr)
                if not fltr_results[fltr]:
                    fltrs_passed = False
                    break

            if fltrs_passed:
                hdlr_exec_params = self._registry._handler_exec_params[hdlr]
                hdlr_fut = self._runner.run(
                    hdlr,
                    update_context,
                    run_async=meta.is_async,
                    run_safe=meta.run_safe,
                )
                if hdlr_exec_params.get('await_for', False):
                    hdlr_futures_to_await.append(hdlr_fut)
                if hdlr_exec_params.get('run_once', False):
                    hdlrs_to_unsubscribe.add(hdlr)

        self._registry.unsubscribe(hdlrs_to_unsubscribe)

        try:
            await self._runner.await_(hdlr_futures_to_await)
        finally:
            await self._runner.cancel(fltr_futures.values())  # cancel unused filters
