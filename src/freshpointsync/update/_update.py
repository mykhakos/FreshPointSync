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
    Dict,
    Generic,
    Iterable,
    List,
    Optional,
    Protocol,
    Set,
    TypedDict,
    TypeGuard,
    TypeVar,
    Union,
    overload,
)

from freshpointparser.models import BaseItem, BasePage
from freshpointparser.models.types import DiffType, ModelDiff, ModelDiffMapping

from .._callable_runner import AwaitableRunner
from .._marks import is_run_safe

if sys.version_info >= (3, 10):
    pass

if sys.version_info >= (3, 11):
    from typing import Unpack
else:
    from typing_extensions import Unpack


logger = logging.getLogger('freshpointsync.update')


_NO_DEFAULT = object()
"""Sentinel value for the ``default`` argument of ``getattr()``."""


# region UpdateContext

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


# endregion

# region UpdateConsumer and validation


T = TypeVar('T')
R = TypeVar('R')


class SupportsBool(Protocol):
    def __bool__(self) -> bool: ...


UpdateConsumer = Callable[[T], Awaitable[R]]
UpdateFilter = UpdateConsumer[T, SupportsBool]
UpdateHandler = UpdateConsumer[T, Any]


class InvalidConsumerError(TypeError):
    pass


class ConsumerValidationResult:
    def __init__(self, is_valid: bool, reason: Optional[str] = None) -> None:
        self.is_valid = is_valid
        self.reason = reason

    def __str__(self) -> str:
        if self.is_valid:
            return 'Valid consumer'
        return f'Invalid consumer: {self.reason}'

    def __bool__(self) -> bool:
        return self.is_valid


def get_consumer_name(consumer: UpdateConsumer) -> str:
    if hasattr(consumer, '__name__'):
        return consumer.__name__
    if hasattr(consumer, '__class__'):
        return consumer.__class__.__name__
    return repr(consumer)


def validate_consumer(consumer: object) -> ConsumerValidationResult:
    """True if the object can be called with exactly one argument."""
    while isinstance(consumer, functools.partial):
        consumer = consumer.func

    logger.info('Validating consumer "%r"', consumer)

    if not callable(consumer):
        return ConsumerValidationResult(
            False,
            reason=(
                f"Consumer '{consumer}' of type '{type(consumer).__name__}' "
                f'is not callable.'
            ),
        )

    if not inspect.iscoroutinefunction(consumer) and not inspect.iscoroutinefunction(
        getattr(consumer, '__call__', None)  # noqa: B004
    ):
        return ConsumerValidationResult(
            False,
            reason=f"Consumer '{consumer}' is not an async callable.",
        )

    if not hash(consumer):
        return ConsumerValidationResult(
            False,
            reason=f"Consumer '{consumer}' is not hashable.",
        )

    try:
        signature = inspect.signature(consumer)
    except Exception as exc:
        return ConsumerValidationResult(
            False,
            reason=f"Failed to inspect signature of consumer '{consumer}': {exc}",
        )

    try:
        signature.bind(object())  # bind one positional argument
        return ConsumerValidationResult(True)
    except TypeError as err:
        return ConsumerValidationResult(
            False,
            reason=(
                f"Consumer '{consumer}' cannot be called with one positional argument: "
                f'{err}'
            ),
        )


def is_valid_consumer(consumer: object) -> TypeGuard[UpdateConsumer]:
    return validate_consumer(consumer).is_valid


# endregion


@dataclass
class UpdateConsumerMeta:
    run_safe: Optional[bool]


class HandlerExecParams(TypedDict, total=False):
    run_once: bool
    """A flag indicating whether the handler should be discarded after its first
    execution.
    """
    await_for: bool
    """A flag indicating whether the handler should be awaited for after its
    execution.
    """


class UpdateConsumerRegistry(Generic[T]):
    """Registry for update consumers (handlers and filters).

    This class manages subscriptions and unsubscriptions of handlers and filters,
    allowing them to be executed based on the update context.
    """

    def __init__(self) -> None:
        self._filters: Dict[UpdateFilter[T], UpdateConsumerMeta] = {}
        self._handlers: Dict[UpdateHandler[T], UpdateConsumerMeta] = {}
        self._handler_exec_params: Dict[UpdateHandler[T], HandlerExecParams] = {}
        self._handlers_to_filters: Dict[UpdateHandler[T], Set[UpdateFilter[T]]] = {}

    @staticmethod
    def _format_consumers(
        consumers: Union[UpdateConsumer, Iterable[UpdateConsumer], None],
    ) -> Set[UpdateConsumer]:
        if not consumers:
            return set()
        if not isinstance(consumers, Iterable):
            consumers = (consumers,)
        return set(consumers)

    @staticmethod
    def _get_consumers_meta(
        consumers: Set[UpdateConsumer],
    ) -> Dict[UpdateConsumer, UpdateConsumerMeta]:
        return {
            consumer: UpdateConsumerMeta(run_safe=is_run_safe(consumer))
            for consumer in consumers
        }

    def subscribe(
        self,
        handler: Union[UpdateHandler[T], Iterable[UpdateHandler[T]]],
        filter_: Union[UpdateFilter[T], Iterable[UpdateFilter[T]], None] = None,
        **kwargs: Unpack[HandlerExecParams],
    ) -> None:
        handlers = self._format_consumers(handler)
        if not handlers:  # nothing to subscribe
            return
        filters = self._format_consumers(filter_)

        filters_meta = self._get_consumers_meta(filters)
        for fltr, fltr_meta in filters_meta.items():
            is_valid = validate_consumer(fltr)
            if not is_valid:
                fltr_name = get_consumer_name(fltr)
                raise InvalidConsumerError(
                    f"Cannot subscribe filter '{fltr_name}': {is_valid.reason}"
                )
            self._filters[fltr] = fltr_meta

        handlers_meta = self._get_consumers_meta(handlers)
        for hdlr, hdlr_meta in handlers_meta.items():
            is_valid = validate_consumer(hdlr)
            if not is_valid:
                hdlr_name = get_consumer_name(hdlr)
                raise InvalidConsumerError(
                    f"Cannot subscribe handler '{hdlr_name}': {is_valid.reason}"
                )
            self._handlers[hdlr] = hdlr_meta
            hdlr_fltrs = self._handlers_to_filters.setdefault(hdlr, set())
            hdlr_fltrs.update(filters_meta.keys())
            self._handler_exec_params[hdlr] = kwargs

    def unsubscribe(
        self,
        handler: Union[UpdateHandler[T], Iterable[UpdateHandler[T]]],
    ) -> None:
        handlers = self._format_consumers(handler)
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


class UpdatePublisher(Generic[T]):
    def __init__(
        self,
        registry: Optional[UpdateConsumerRegistry[T]] = None,
        runner: Optional[AwaitableRunner] = None,
    ) -> None:
        self._registry = registry or UpdateConsumerRegistry[T]()
        self._runner = runner or AwaitableRunner()

    async def post(self, update_context: T) -> None:
        fltr_tasks: Dict[UpdateFilter, asyncio.Task[Optional[SupportsBool]]] = {}
        fltr_results: Dict[UpdateFilter, Optional[SupportsBool]] = {}
        for fltr, meta in self._registry._filters.items():
            task = self._runner.run(fltr(update_context), run_safe=meta.run_safe)
            fltr_tasks[fltr] = task

        hdlr_tasks_to_await: List[asyncio.Task[Any]] = []
        hdlrs_to_unsubscribe = set()
        for hdlr, meta in self._registry._handlers.items():
            fltrs_passed = True

            fltrs = self._registry._handlers_to_filters.get(hdlr, set())
            for fltr in fltrs:
                if fltr not in fltr_results:
                    fltr_results[fltr] = await fltr_tasks.pop(fltr)
                if not fltr_results[fltr]:
                    fltrs_passed = False
                    break

            if fltrs_passed:
                hdlr_exec_params = self._registry._handler_exec_params[hdlr]
                task = self._runner.run(hdlr(update_context), run_safe=meta.run_safe)
                if hdlr_exec_params.get('await_for', False):
                    hdlr_tasks_to_await.append(task)
                if hdlr_exec_params.get('run_once', False):
                    hdlrs_to_unsubscribe.add(hdlr)

        self._registry.unsubscribe(hdlrs_to_unsubscribe)

        try:
            await self._runner.await_(hdlr_tasks_to_await)
        finally:
            await self._runner.cancel(fltr_tasks.values())  # cancel unused filters
