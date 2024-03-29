import asyncio
import collections.abc
import enum
import inspect
import logging
import sys

from concurrent.futures import Executor
from dataclasses import dataclass
from typing import (
    cast,
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Generic,
    Iterable,
    Iterator,
    Literal,
    NamedTuple,
    Optional,
    TYPE_CHECKING,
    TypeVar,
    Union
)
if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    # define TypeAlias as a no-op for type checkers in older Python versions
    if TYPE_CHECKING:
        TypeAlias = type
    else:
        TypeAlias = None


from ..product._product import Product


logger = logging.getLogger('freshpointsync.update')


T = TypeVar('T')


class SafeAsyncTaskRunner:
    """
    A utility for running asynchronous and synchronous tasks in
    a non-blocking manner with optional error handling and
    the ability to await or cancel all running tasks.
    """

    def __init__(self, executor: Optional[Executor] = None) -> None:
        """
        Initialize a `SafeAsyncTaskRunner` instance with an optional executor.

        Args:
            executor (Optional[Executor]): A `concurrent.futures.Executor`
            object to be used for running synchronous functions in
            a non-blocking manner. If None, a default executor is used.
            For more information, see the asyncio event loop's
            `run_in_executor` documentation. Defaults to None.
        """
        self.tasks: set[asyncio.Task] = set()
        """
        A set that stores all running or pending tasks
        associated with calls to the `run_async` method.
        """
        self.futures: set[asyncio.Future] = set()
        """
        A set that stores all running or pending futures
        associated with calls to the `run_sync` method.
        """
        self.executor = executor
        """
        An optional `concurrent.futures.Executor` object to be used
        for running synchronous functions in the `run_sync` method.
        """

    @staticmethod
    def _log_task_or_future_done(
        task_or_future: Union[asyncio.Task, asyncio.Future],
        type_: Literal["Task", "Future"],
        name: str
    ) -> None:
        """
        Log the result of a completed asyncio Task or Future.

        Logs:
            - A warning if the Task or Future was cancelled.
            - A debug message if it completed successfully or
            if a raised exception was caught.
            - An error with details if an exception was raised.

        Args:
            task_or_future: The Task or Future object to log.
            type_: Specifies whether the object is a "Task" or a "Future".
            name: The name of the Task or Future for identification in logs.
        """
        if task_or_future.cancelled():
            logger.warning('%s "%s" was cancelled', type_, name)
        elif task_or_future.exception() is None:
            logger.debug('%s "%s" finished', type_, name)
        else:
            exc = task_or_future.exception()
            exc_type, exc_desc = type(exc).__name__, str(exc)
            if exc_desc:
                logger.error(
                    '%s "%s" raised an exception (%s: %s)',
                    type_, name, exc_type, exc_desc
                    )
            else:
                logger.error(
                    '%s "%s" raised an exception (%s)',
                    type_, name, exc_type
                    )

    @staticmethod
    def _log_caught_exception(
        exc: Exception,
        type_: Literal["Task", "Future"],
        name: str,
    ) -> None:
        """
        Log a warning for an exception caught from a Task or Future
        in a safe runner.

        Logs:
            - A warning with the exception type and description, if available.

        Args:
            exc: The exception instance that was caught.
            type_: Indicates whether the exception came from
            a "Task" or a "Future".
            name: The name of the Task or Future for identification in logs.
        """
        exc_type, exc_desc = type(exc).__name__, str(exc)
        if exc_desc:
            logger.warning(
                '%s "%s" failed (%s: %s)',
                type_, name, exc_type, exc_desc
                )
        else:
            logger.warning(
                '%s "%s" failed (%s)',
                type_, name, exc_type
                )

    @staticmethod
    def _get_awaitable_name(awaitable: Awaitable) -> str:
        """
        Retrieve a human-readable name of an awaitable object.

        Args:
            awaitable (Awaitable): The awaitable object for which to
            retrieve the name.

        Returns:
            str: A string representing the name of the awaitable.
            Defaults to the `repr` of the awaitable if
            a specific name cannot be determined.
        """
        try:
            if isinstance(awaitable, asyncio.Task):
                return awaitable.get_name()
            elif inspect.iscoroutine(awaitable):
                return awaitable.cr_code.co_name
            return repr(awaitable)
        except Exception:  # in case "inspect.iscoroutine" fails
            return repr(awaitable)

    async def _run_async_safe(self, awaitable: Awaitable[T]) -> Optional[T]:
        """
        Wrap an awaitable in a coroutine with added error handling that
        catches and logs exceptions. Note that the `asyncio.CancelledError`
        exceptions are re-raised to propagate cancellation.

        Args:
            awaitable (Awaitable[T]): The awaitable object to run.

        Returns:
            Optional[T]: The result of the awaitable if it completes
            successfully, `None` if an exception occurs.
        """
        try:
            return await awaitable
        except asyncio.CancelledError:
            raise  # re-raise to ensure cancellation is propagated
        except Exception as exc:
            awaitable_name = self._get_awaitable_name(awaitable)
            self._log_caught_exception(exc, "Task", awaitable_name)
            return None

    def run_async(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *func_args: Any,
        run_safe: bool = True,
        done_callback: Optional[Callable[[asyncio.Task], Any]] = None
    ) -> asyncio.Task[Optional[T]]:
        """
        Schedule a coroutine function to be run,
        optionally with error handling and a completion callback.

        This method is specifically designed for running coroutine functions
        that are asynchronous in nature. Providing a synchronous (non-async)
        function to this method will fail at runtime.

        Args:
            func (Callable[..., Coroutine[Any, Any, T]]): The coroutine
            function to be run.
            *func_args (Any): The arguments to run the coroutine function with.
            run_safe (bool): If True, the potential exceptions raised by
            the coroutine are caught and logged, and the result is set to
            `None` in case of an error. If False, exceptions are propagated
            and must be handled by the caller. Defaults to True.
            done_callback (Optional[Callable[[asyncio.Task], Any]]): An
            optional callback to be called when the task completes.

        Returns:
            asyncio.Task[Optional[T]]: An asyncio task object representing
            the scheduled coroutine. The task can be awaited to obtain
            the result of the coroutine function call or cancelled.
        """
        name = self._get_func_name(func)
        logger.debug('Scheduling task "%s"', name)
        if run_safe:
            task = asyncio.create_task(self._run_async_safe(func(*func_args)))
        else:
            task = asyncio.create_task(func(*func_args))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(
            lambda t: self._log_task_or_future_done(t, "Task", name)
            )
        if done_callback:
            task.add_done_callback(done_callback)
        return task

    @staticmethod
    def _get_func_name(func: Callable[..., T]) -> str:
        """
        Retrieve a human-readable name of a function.

        Args:
            func (Callable[..., T]): The function for which
            to retrieve the name.

        Returns:
            str: The name of the function.
        """
        try:
            return func.__name__
        except AttributeError:
            return repr(func)

    def _run_sync_safe(self, func: Callable[..., T], *args) -> Optional[T]:
        """
        Call a synchronous function with added error handling that
        catches and logs exceptions. Note that the `asyncio.CancelledError`
        exceptions are re-raised to propagate cancellation.

        Args:
            func (Callable[..., T]): The synchronous function to run.
            *args: Arguments to run the function with.

        Returns:
            Optional[T]: The result of the function if it completes
            successfully, `None` if an exception occurs.
        """
        try:
            return func(*args)
        except asyncio.CancelledError:
            raise  # re-raise to ensure cancellation is propagated
        except Exception as exc:
            name = self._get_func_name(func)
            self._log_caught_exception(exc, "Future", name)
            return None

    def run_sync(
        self,
        func: Callable[..., T],
        *func_args,
        run_safe: bool = True,
        done_callback: Optional[Callable[[asyncio.Future], Any]] = None
    ) -> asyncio.Future[Optional[T]]:
        """
        Schedule a synchronous function to be run in a non-blocking manner,
        optionally with error handling and a completion callback.

        This method is specifically designed for synchronous functions that
        block. It utilizes an executor, allowing for concurrent execution of
        such functions without blocking the asyncio event loop. Providing
        an asynchronous (async) function will fail at runtime.

        Args:
            func (Callable[..., T]): The synchronous function to be run.
            *func_args (Any): The arguments to run the function with.
            run_safe (bool): If True, the potential exceptions raised by
            the synchronous function are caught and logged, and the result
            is set to `None` in case of an error. If False, exceptions
            are propagated and must be handled by the caller. Defaults to True.
            done_callback (Optional[Callable[[asyncio.Future], Any]]): An
            optional callback to be called when the future completes.

        Returns:
            asyncio.Future[Optional[T]]: An asyncio future object representing
            the scheduled execution of the synchronous function. The future
            can be awaited to obtain the result of the function call. Note that
            cancellation of the future is not possible if the function is
            already running (for more information, see the `concurrent.futures`
            documentation on cancellation of the future objects).
        """
        name = self._get_func_name(func)
        logger.debug('Scheduling future "%s"', name)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Optional[T]]
        if run_safe:
            def wrapped(): return self._run_sync_safe(func, *func_args)
            future = loop.run_in_executor(self.executor, wrapped)
        else:
            future = loop.run_in_executor(self.executor, func, *func_args)
        future.add_done_callback(self.futures.discard)
        future.add_done_callback(
            lambda f: self._log_task_or_future_done(f, "Future", name)
            )
        if done_callback:
            future.add_done_callback(done_callback)
        self.futures.add(future)
        return future

    async def await_all(self) -> None:
        """
        Wait for all scheduled asynchronous and synchronous tasks to complete.

        This method gathers all active asyncio tasks and futures and awaits for
        their completion. It is particularly useful for ensuring that
        all background operations have finished before proceeding to another
        stage of the application or gracefully shutting down the application.

        Note that this method ensures that the tracking sets of tasks and
        futures have been cleared after their completion, effectively resetting
        the runner's state.
        """
        logger.debug('Awaiting all tasks and futures')
        tasks = set(self.tasks)
        futures = set(self.futures)
        await asyncio.gather(*tasks, *futures)
        self.tasks.clear()
        self.futures.clear()

    async def cancel_all(self) -> None:
        """
        Attempt to cancel all active tasks and futures.

        This method gathers and cancells all active asyncio tasks and attempts
        to cancel all active futures created by running synchronous functions.
        For the latter, the cancellation if only possible if the future has not
        started running yet (for more information, see the `concurrent.futures`
        documentation on cancellation of the future objects). The method is
        particularly useful for cancelling all background operations before
        proceeding to another stage of the application or gracefully shutting
        down the application.

        Note that this method ensures that the tracking set of tasks have been
        cleared after their completion. The set of futures is not cleared, as
        the cancellation of the futures is not guaranteed to be successful.
        """
        logger.debug('Cancelling all tasks and futures')
        # let the event loop run to allow for task cancellation
        # (helps if "cancel_all" is called right after a task is created)
        await asyncio.sleep(0)
        tasks = set(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        self.tasks.clear()
        futures = set(self.futures)
        for future in futures:
            if future.cancel():
                self.futures.remove(future)


class ProductUpdateEvent(enum.Enum):
    """
    An enumeration of different types of product updates.

    This enum is used to represent various kinds of changes or updates that can
    occur to a product on the product page. Each member represents a specific
    type of update event for easy identification and handling.
    """
    PRODUCT_ADDED = "product_added"
    """Indicates that a new product has been listed on the product page."""
    PRODUCT_UPDATED = "product_updated"
    """Indicates any update to a product's information and state."""
    QUANTITY_UPDATED = "quantity_updated"
    """Indicates that the stock quantity of a product has been updated."""
    PRICE_UPDATED = "price_updated"
    """Indicates that the pricing of a product has changed, including both
    full price and current sale price."""
    PIC_URL_UPDATED = "pic_url_updated"
    """Indicates an update to the product's illustration picture URL."""
    PRODUCT_REMOVED = "product_removed"
    """Indicates that a product has been removed from the product page."""


@dataclass(frozen=True)
class ProductUpdateContext(collections.abc.Mapping):
    """
    An update event context data wrapper for product update events with
    a mapping-like access to the data along with direct access to
    specific product state information, such as `product_new`, `product_old`,
    `location_id`, and `location_name`.

    This class is designed to encapsulate the update event context data
    passed to event handlers during product update events.
    """
    __kwargs: dict[Any, Any]

    def __getitem__(self, key: Any) -> Any:
        """
        Returns the value for the given key from the internal context data.

        Args:
            key (Any): The key to look up in the context data.

        Returns:
            Any: The value associated with the specified key.
        """
        return self.__kwargs[key]

    def __iter__(self) -> Iterator[Any]:
        """
        Returns an iterator over the keys of the internal context data.

        Returns:
            Iterator[Any]: An iterator over the keys of the context data.
        """
        return iter(self.__kwargs)

    def __len__(self) -> int:
        """
        Returns the number of items in the internal context data.

        Returns:
            int: The number of items in the context data.
        """
        return len(self.__kwargs)

    @property
    def location_id(self) -> int:
        """
        ID of the product location.
        If not available, defaults to 0.
        """
        return self.__kwargs['location_id']

    @property
    def location_name(self) -> str:
        """
        Name of the product location.
        If not available, defaults to an empty string.
        """
        return self.__kwargs['location_name']

    @property
    def product_new(self) -> Optional[Product]:
        """
        New state of the product after the update.
        If not available, defaults to None.
        """
        return self.__kwargs['product_new']

    @property
    def product_old(self) -> Optional[Product]:
        """
        Previous state of the product before the update.
        If not available, defaults to None.
        """
        return self.__kwargs['product_old']


class HandlerValidator:
    """
    A utility class for validating handler functions or methods based on their
    signature and whether they are asynchronous or synchronous.
    """

    @classmethod
    def _is_valid_is_async(cls, handler: Any) -> tuple[bool, bool]:
        """
        Determine if a given handler is valid based on its signature and
        whether it is an asynchronous coroutine or a synchronous function
        or method.

        Args:
            handler: The handler to be validated. This can be any callable
            including functions, methods, or objects with a `__call__` method.

        Returns:
            tuple(bool, bool): A tuple of two boolean values, where the first
            value indicates whether the handler is valid (True) or not (False)
            and the second value indicates whether the handler is an async
            coroutine (True) or a synchronous function or method (False).
        """
        if not callable(handler):
            return False, False
        if inspect.iscoroutinefunction(handler):
            sig = inspect.signature(handler)
            return (len(sig.parameters) == 1), True
        elif inspect.isfunction(handler) or inspect.ismethod(handler):
            sig = inspect.signature(handler)
            return (len(sig.parameters) == 1), False
        elif hasattr(handler, '__call__'):
            return cls._is_valid_is_async(handler.__call__)
        return False, False

    @classmethod
    def is_valid_async_handler(cls, handler: Any) -> bool:
        """
        Check if a handler is an asynchronous coroutine function with a valid
        signature (accepts exactly one argument).

        Args:
            handler: The handler to be validated.

        Returns:
            bool: True if the handler is valid and asynchronous;
            otherwise, False.
        """
        is_valid, is_async = cls._is_valid_is_async(handler)
        return is_valid and is_async

    @classmethod
    def is_valid_sync_handler(cls, handler: Any) -> bool:
        """
        Check if a handler is a synchronous function or method with a valid
        signature (accepts exactly one argument).

        Args:
            handler: The handler to be validated.

        Returns:
            bool: True if the handler is valid and synchronous;
            otherwise, False.
        """
        is_valid, is_async = cls._is_valid_is_async(handler)
        return is_valid and not is_async

    @classmethod
    def is_valid_handler(cls, handler: Any) -> bool:
        """
        Check if a handler has a valid signature and is a valid function or
        method, regardless of whether it is synchronous or asynchronous.

        Args:
            handler: The handler to be validated.

        Returns:
            bool: True if the handler is valid; otherwise, False.
        """
        is_valid, _ = cls._is_valid_is_async(handler)
        return is_valid


def is_valid_handler(handler: Any) -> bool:
    """
    Validate a handler based on its signature and whether it is an
    asynchronous coroutine or a synchronous function or method.

    Args:
        handler (Any): The handler to be validated.

    Returns:
        bool: True if the handler is valid; otherwise, False.
    """
    return HandlerValidator.is_valid_handler(handler)


SyncHandler: TypeAlias = Callable[
    [ProductUpdateContext], None
    ]
"""
Type alias for a synchronous handler function. Expects a single argument
of type `ProductUpdateContext` and returns `None`.
"""


AsyncHandler: TypeAlias = Callable[
    [ProductUpdateContext], Coroutine[Any, Any, None]
    ]
"""
Type alias for an asynchronous handler function. Expects a single argument
of type `ProductUpdateContext` and returns a coroutine that resolves to `None`.
"""


Handler: TypeAlias = Union[SyncHandler, AsyncHandler]
"""
Type alias for a handler function or method. Can be either a synchronous
callable that accepts a single argument of type `ProductUpdateContext` and
returns `None`, or an asynchronous callable that accepts a single argument
of type `ProductUpdateContext` and returns a coroutine that resolves to `None`.
"""


class HandlerExecParamsTuple(NamedTuple):
    """
    A `NamedTuple` implementation for storing handler execution parameters.
    """
    call_safe: bool
    """
    A flag indicating whether the handler should be called in a "safe" manner,
    meaning any exceptions raised by the handler will be caught and handled.
    """
    done_callback: Optional[Callable[[asyncio.Future], Any]]
    """
    An optional callback function to be called when the handler completes
    its execution. Depending of the type of the handler, the callback
    receives an `asyncio.Task` or `asyncio.Future` object as its argument,
    which represents the eventual result of the handler's execution.
    """


HandlerType = TypeVar('HandlerType', SyncHandler, AsyncHandler)
"""A `TypeVar` variable for a handler function or method."""


class HandlerDataTuple(NamedTuple, Generic[HandlerType]):
    """A `NamedTuple` implementation for storing handler data."""
    handler: HandlerType
    """The handler function to be executed after a certain event occurs."""
    exec_params: HandlerExecParamsTuple
    """The hanlder function execution parameters."""


SyncHandlerList: TypeAlias = list[HandlerDataTuple[SyncHandler]]
"""A list of `HandlerDataTuple` records of synchronous handlers."""


AsyncHandlerList: TypeAlias = list[HandlerDataTuple[AsyncHandler]]
"""A list of `HandlerDataTuple` records of asynchronous handlers."""


class ProductUpdateEventPublisher:
    """
    A publisher and a subscription manager for product update events.

    This class maintains a registry of event handlers for different types of
    product update events. It allows for subscribing or unsubscribing handlers
    to specific events and facilitates broadcasting events to all relevant
    handlers.
    """
    def __init__(self) -> None:
        self.context: dict[Any, Any] = {}  # global persistent context
        self.runner = SafeAsyncTaskRunner()
        self.sync_subscribers: dict[ProductUpdateEvent, SyncHandlerList] = {}
        self.async_subscribers: dict[ProductUpdateEvent, AsyncHandlerList] = {}

    @staticmethod
    def _is_in_subscribers_list(
        handler: Handler, subscribers: list[HandlerDataTuple]
    ) -> bool:
        """
        Check if a handler is already present in the list of subscribers.

        This method iterates over the subscribers list to check if the provided
        handler matches any handler in the list based on object identity.

        Args:
            handler: The handler function or method to check.
            subscribers: A list of `HandlerDataTuple` objects representing
            the current subscribers.

        Returns:
            bool: True if the handler is found in the list of subscribers;
            otherwise, False.
        """
        return any(existing.handler == handler for existing in subscribers)

    @staticmethod
    def _remove_from_subscribers_list(
        handler: Handler, subscribers: list[HandlerDataTuple]
    ) -> None:
        """
        Remove a handler from the list of subscribers.

        This method iterates over the subscribers list to find and remove
        the provided handler based on object identity. If the handler
        is not found in the list, no action is taken.

        Args:
            handler: The handler function or method to remove.
            subscribers: A list of `HandlerDataTuple` objects representing
            the current subscribers.
        """
        for i, existing in enumerate(subscribers):
            if existing.handler == handler:
                del subscribers[i]
                break

    def _subscribe_sync(
        self,
        event: ProductUpdateEvent,
        handler: Handler,
        call_safe: bool = True,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
    ) -> None:
        """
        Subscribe a synchronous handler to a specific product update event.

        This internal method adds a synchronous handler to the event's
        subscribers list, ensuring that the handler and its
        execution parameters are stored correctly.

        Args:
            event: The product update event to subscribe the handler to.
            handler: The synchronous handler to be subscribed.
            call_safe: Indicates whether the handler should be called in
            a "safe" manner, with exceptions caught and handled.
            handler_done_callback: An optional callback function to be called
            when the handler completes its execution.
        """
        subscribers = self.sync_subscribers.setdefault(event, [])
        if not self._is_in_subscribers_list(handler, subscribers):
            params = HandlerExecParamsTuple(call_safe, handler_done_callback)
            handler = cast(SyncHandler, handler)
            subscribers.append(HandlerDataTuple(handler, params))

    def _subscribe_async(
        self,
        event: ProductUpdateEvent,
        handler: Handler,
        call_safe: bool = True,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
    ) -> None:
        """
        Subscribe an asynchronous handler to a specific product update event.

        This internal method adds an asynchronous handler to the event's
        subscribers list, ensuring that the handler and its
        execution parameters are stored correctly.

        Args:
            event: The product update event to subscribe the handler to.
            handler: The asynchronous handler to be subscribed.
            call_safe: Indicates whether the handler should be called in
            a "safe" manner, with exceptions caught and handled.
            handler_done_callback: An optional callback function to be called
            when the handler completes its execution.
        """
        subscribers = self.async_subscribers.setdefault(event, [])
        if not self._is_in_subscribers_list(handler, subscribers):
            params = HandlerExecParamsTuple(call_safe, handler_done_callback)
            handler = cast(AsyncHandler, handler)
            subscribers.append(HandlerDataTuple(handler, params))

    def subscribe(
        self,
        event: ProductUpdateEvent,
        handler: Handler,
        call_safe: bool = True,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None
    ) -> None:
        """
        Subscribe a handler to a specific product update event to be invoked
        when the event is posted.

        This handler can be an asynchronous function, method, or any callable
        object that accepts exactly one argument (a `ProductUpdateContext`
        object) and returns `None` or a coroutine that resolves to `None`.

        Args:
            event (ProductUpdateEvent): The type of product update event to
            subscribe to.
            handler (Handler): The handler to be invoked for the event.

        Raises:
            TypeError: If the handler does not have a valid signature.
        """
        event = ProductUpdateEvent(event)
        is_valid, is_async = HandlerValidator._is_valid_is_async(handler)
        if not is_valid:
            raise TypeError("Handler signature is invalid.")
        callback = handler_done_callback
        if is_async:
            self._subscribe_async(event, handler, call_safe, callback)
        else:
            self._subscribe_sync(event, handler, call_safe, callback)

    def unsubscribe(
        self,
        event: ProductUpdateEvent,
        handler: Optional[Handler] = None
    ) -> None:
        """
        Unsubscribe a handler from a specific product update event,
        or all handlers if no specific handler is provided. The unsubscribed
        handler will no longer be invoked when the event is posted.

        Args:
            event (ProductUpdateEvent): The type of product update event to
            unsubscribe from.
            handler (Handler): The handler to be unsubscribed from the event.
            if None, all handlers for the event are unsubscribed.
        """
        event = ProductUpdateEvent(event)
        if handler is None:
            self.async_subscribers.pop(event, None)
            self.sync_subscribers.pop(event, None)
            return
        async_subs = self.async_subscribers.get(event)
        sync_subs = self.async_subscribers.get(event)
        if async_subs and self._is_in_subscribers_list(handler, async_subs):
            self._remove_from_subscribers_list(handler, async_subs)
        elif sync_subs and self._is_in_subscribers_list(handler, sync_subs):
            self._remove_from_subscribers_list(handler, sync_subs)

    def is_subscribed(self, event: ProductUpdateEvent) -> bool:
        """
        Check if there are any subscribers for the given event.

        Args:
            event (ProductUpdateEvent): The event to check for subscribers.

        Returns:
            bool: True if there are subscribers for the event, False otherwise.
        """
        e = ProductUpdateEvent(event)
        return bool(
            self.async_subscribers.get(e) or self.sync_subscribers.get(e)
            )

    def get_context(
        self,
        product_new: Optional[Product],
        product_old: Optional[Product],
        **kwargs: Any
    ) -> ProductUpdateContext:
        """
        Construct a `ProductUpdateContext` instance from the provided products
        and additional parameters, merging the global context data with the
        specific product information and any additional keyword arguments
        (the latter takes precedence).

        Args:
            product_new (Optional[Product]): The updated product instance,
            or None if not applicable.
            product_old (Optional[Product]): The original product instance
            before the update, or None if not applicable.
            **kwargs (Any): Additional context parameters to be included.

        Returns:
            ProductUpdateContext: A context object populated with the global
            context data and the provided product information and parameters.
        """
        context_kwargs = {**self.context, **kwargs}
        context_kwargs['product_new'] = product_new
        context_kwargs['product_old'] = product_old
        if product_new:
            context_kwargs['location_id'] = product_new.location_id
            context_kwargs['location_name'] = product_new.location_name
        elif product_old:
            context_kwargs['location_id'] = product_old.location_id
            context_kwargs['location_name'] = product_old.location_name
        else:
            context_kwargs['location_id'] = 0
            context_kwargs['location_name'] = ''
        return ProductUpdateContext(context_kwargs)

    def post(
        self,
        event: ProductUpdateEvent,
        product_new: Optional[Product],
        product_old: Optional[Product],
        **kwargs: Any
    ) -> None:
        """
        Notify registered handlers about a specific product update event.

        This function constructs a `ProductUpdateContext` with new and old
        product details, along with any additional keyword arguments. It then
        broadcasts the event to all relevant handlers, asynchronous and
        synchronous alike, registered for the event type.

        Args:
            event (ProductUpdateEvent): The type of product update event
            to be broadcasted.
            product_new (Optional[Product]): The updated product instance,
            or None if there's no new product.
            product_old (Optional[Product]): The original product instance
            before update, or None if unavailable.
            **kwargs (Any): Additional keyword arguments to be included
            in the event context. If any of the keyword arguments
            overlaps with the context data, it takes precedence.
        """
        event = ProductUpdateEvent(event)
        context: Optional[ProductUpdateContext] = None
        if event in self.async_subscribers:
            context = self.get_context(product_new, product_old, **kwargs)
            for async_sub in self.async_subscribers[event]:
                self.runner.run_async(
                    async_sub.handler,
                    context,
                    run_safe=async_sub.exec_params.call_safe,
                    done_callback=async_sub.exec_params.done_callback
                    )
        if event in self.sync_subscribers:
            if context is None:
                context = self.get_context(product_new, product_old, **kwargs)
            for sync_sub in self.sync_subscribers[event]:
                self.runner.run_sync(
                    sync_sub.handler,
                    context,
                    run_safe=sync_sub.exec_params.call_safe,
                    done_callback=sync_sub.exec_params.done_callback
                    )

    def post_multiple(
        self,
        events: Iterable[ProductUpdateEvent],
        product_new: Optional[Product],
        product_old: Optional[Product],
        **kwargs: Any
    ) -> None:
        """
        Notify registered handlers about multiple product update events.

        This function constructs a `ProductUpdateContext` once using
        the provided new and old product details, along with any additional
        keyword arguments. It then broadcasts each event in the given
        iterable to all relevant handlers, both asynchronous and synchronous,
        that are registered for each event type. This approach is slightly
        more efficient than calling `post` for each event separately, as it
        avoids creating a new context for each event.

        Args:
            events (Iterable[ProductUpdateEvent]): The types of product update
            events to be broadcasted.
            product_new (Optional[Product]): The updated product instance,
            or None if there's no new product.
            product_old (Optional[Product]): The original product instance
            before update, or None if unavailable.
            **kwargs (Any): Additional keyword arguments to be included
            in the event context. If any of the keyword arguments
            overlaps with the context data, it takes precedence.
        """
        old, new = product_old, product_new
        context: Optional[ProductUpdateContext] = None
        events = (ProductUpdateEvent(event) for event in events)
        for event in events:
            if event in self.async_subscribers:
                if context is None:
                    context = self.get_context(new, old, **kwargs)
                for async_sub in self.async_subscribers[event]:
                    self.runner.run_async(
                        async_sub.handler,
                        context,
                        run_safe=async_sub.exec_params.call_safe,
                        done_callback=async_sub.exec_params.done_callback
                        )
            if event in self.sync_subscribers:
                if context is None:
                    context = self.get_context(new, old, **kwargs)
                for sync_sub in self.sync_subscribers[event]:
                    self.runner.run_sync(
                        sync_sub.handler,
                        context,
                        run_safe=sync_sub.exec_params.call_safe,
                        done_callback=sync_sub.exec_params.done_callback
                        )


class ProductCacheUpdater:
    """
    Product cache manager. Updates the cache and notifies subscribers
    about product updates.

    This class is responsible for maintaining a cache of product data and
    using an event publisher to notify interested parties of changes to
    product information. It provides methods to create, delete, and update
    products in the cache and to trigger appropriate events for each action.
    """
    def __init__(
        self,
        products: dict[int, Product],
        publisher: ProductUpdateEventPublisher
    ) -> None:
        """
        Initialize a `ProductCacheUpdater` instance.

        Args:
            products (dict[int, Product]): A dictionary of products, where
            the keys are product IDs and the values are `Product` objects.
            publisher (ProductUpdateEventPublisher): An instance of
            the `ProductUpdateEventPublisher` class to call subscribed handlers
            when product updates occur.
        """
        self.products = products
        self._publisher = publisher

    def create_product(self, product: Product, **kwargs: Any) -> None:
        """
        Add a new product to the cache and post a `PRODUCT_ADDED` event.

        Note that this method assumes that the product is not present in the
        cache already.

        Args:
            product (Product): the product to add to the cache.
            **kwargs (Any): Additional keyword arguments to include
            in the update event context.
        """
        self.products[product.product_id] = product
        self._publisher.post(
            event=ProductUpdateEvent.PRODUCT_ADDED,
            product_new=product,
            product_old=None,
            **kwargs
            )

    def delete_product(self, product: Product, **kwargs: Any) -> None:
        """
        Remove a product from the cache and posts a `PRODUCT_REMOVED` event.

        Note that this method assumes that the product is present in the cache.

        Args:
            product (Product): the product to remove from the cache.
            **kwargs (Any): Additional keyword arguments to include
            in the update event context.
        """
        del self.products[product.product_id]
        self._publisher.post(
            event=ProductUpdateEvent.PRODUCT_REMOVED,
            product_new=None,
            product_old=product,
            **kwargs
            )

    def update_product(
        self, product: Product, product_cached: Product, **kwargs: Any
    ) -> None:
        """
        Update a product in the cache and post events reflecting
        the specific changes occured.

        This method determines what aspects of the product have changed
        (e.g., stock level, price, etc.) and posts the appropriate events
        for each type of update.

        Note that this method assumes that the product is different from
        the cached product.

        Args:
            product (Product): The new product state
            after the update.
            product_cached (Product): The original product state
            before the update.
            **kwargs (Any): Additional keyword arguments to include
            in the update event context.
        """
        self.products[product.product_id] = product
        events: list[ProductUpdateEvent] = [ProductUpdateEvent.PRODUCT_UPDATED]
        if product.quantity != product_cached.quantity:
            events.append(ProductUpdateEvent.QUANTITY_UPDATED)
        if (
            product.price_full != product_cached.price_full or
            product.price_curr != product_cached.price_curr
        ):
            events.append(ProductUpdateEvent.PRICE_UPDATED)
        if product.pic_url != product_cached.pic_url:
            events.append(ProductUpdateEvent.PIC_URL_UPDATED)
        self._publisher.post_multiple(
            events=events,
            product_new=product,
            product_old=product_cached,
            **kwargs
            )

    async def update(
        self,
        products: Iterable[Product],
        await_handlers: bool = False,
        **kwargs: Any
    ) -> None:
        """
        Processe a batch of product updates, adding, deleting, or updating
        products as necessary.

        This method iterates through a given iterable of products, updating
        the cache to reflect new, removed, or changed products. It optionally
        waits for all event handlers to complete if `await_handlers` is True.

        Args:
            products (Iterable[Product]): products to process.
            await_handlers: If True, waits for all triggered event handlers
            to complete.
            **kwargs (Any): Additional keyword arguments to include
            in the update event context.
        """
        products_mapping = {p.product_id: p for p in products}
        # check if any product is not listed anymore
        for id_number, product in self.products.items():
            if id_number not in products_mapping:
                self.delete_product(product, **kwargs)
        # update the products (or create if not previously listed)
        for id_number, product in products_mapping.items():
            product_cached = self.products.get(id_number)
            if product_cached is None:
                self.create_product(product, **kwargs)
            elif product_cached != product:
                self.update_product(product, product_cached, **kwargs)
        # optionally await the triggered handlers
        if await_handlers:
            await self._publisher.runner.await_all()

    def update_silently(self, products: Iterable[Product]) -> None:
        """
        Update the product cache without triggering any events.

        This method clears the cache dictionary and subsequently populates
        it with the given products, effectively replacing the entire cache
        contents while maintaining the dictionary object itself.

        Args:
            products (Iterable[Product]): products to populate the cache with.
        """
        self.products.clear()
        self.products.update({p.product_id: p for p in products})
