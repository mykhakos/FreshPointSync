import asyncio
import inspect
import logging
import sys
from concurrent.futures import Executor
from functools import partial
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Iterable,
    Literal,
    Optional,
    TypeVar,
    Union,
    cast,
)

if sys.version_info >= (3, 10):
    from typing import ParamSpec
else:
    from typing_extensions import ParamSpec

logger = logging.getLogger('freshpointsync.runner')
"""Logger for the `freshpointsync.runner` package."""


P = ParamSpec('P')
R = TypeVar('R')


class CallableRunMark:
    ATTR = ''  # This will be set in subclasses
    """Attribute name used to mark functions with this run mark."""

    @classmethod
    def get_mark_value(cls, fn: Callable[P, R]) -> Any:
        """Check if a function is decorated with a specific run mark.

        Args:
            fn (Callable[P, R]): The function to check.

        Returns:
            Any: The value of the mark if set, or None if not set.
                This can be True, False, or any other value that indicates
                the mark's state.
        """
        return getattr(fn, cls.ATTR, None)

    @classmethod
    def set_mark_value(cls, fn: Callable[P, R], value: Any) -> None:
        """Mark a function with a specific run mark by setting the special attribute.

        Args:
            fn (Callable[P, R]): The function to mark.
            value (Any): The value to set for the mark. This can be True,
                False, or any other value that indicates the mark's state.
        """
        setattr(fn, cls.ATTR, value)


class RunSafe(CallableRunMark):
    ATTR = '_run_safe'


def run_safe(fn: Callable[P, R]) -> Callable[P, R]:
    """Mark a function to be executed safely, meaning that any exceptions raised
    during its execution will be caught and logged, and the result will
    be set to None in case of an error.

    This decorator overrides the session-wide error handling mode for this
    specific function, forcing safe execution regardless of the CallableRunner's
    global setting.

    Args:
        fn (Callable[P, R]): The function to be marked as safe.

    Returns:
        Callable[P, R]: The original function marked with a special attribute.
    """
    RunSafe.set_mark_value(fn, True)
    return fn


def run_unsafe(fn: Callable[P, R]) -> Callable[P, R]:
    """Mark a function to be executed unsafely, meaning that any exceptions raised
    during its execution will be propagated to the caller.

    This decorator overrides the session-wide error handling mode for this
    specific function, forcing unsafe execution regardless of the CallableRunner's
    global setting.

    Args:
        fn (Callable[P, R]): The function to be marked as unsafe.

    Returns:
        Callable[P, R]: The original function marked with a special attribute.
    """
    RunSafe.set_mark_value(fn, False)
    return fn


def is_run_safe(fn: Callable[P, R]) -> Optional[bool]:
    """Check if a function is decorated with `@run_safe` or `@run_unsafe`.

    Args:
        fn (Callable[P, R]): The function to check.

    Returns:
        Optional[bool]: True if the function is decorated with `@run_safe`,
                       False if decorated with `@run_unsafe`, None if no decorator.
    """
    return RunSafe.get_mark_value(fn)


class CallableRunner:
    """A utility for running asynchronous and synchronous callables in
    a non-blocking or blocking manner (the latter is only relevant for
    synchronous callables) with optional error handling and the ability to
    await or cancel all running tasks.
    """

    def __init__(
        self,
        executor: Optional[Executor] = None,
        run_safe: bool = True,
    ) -> None:
        """Initialize a `CallableRunner` instance with an optional executor
        and error handling mode.

        Args:
            executor (Optional[Executor]): A `concurrent.futures.Executor`
                object to be used for running synchronous callables in
                a non-blocking manner. If None, a default executor is used.
                For more information, see the asyncio event loop's
                `run_in_executor` documentation. Defaults to None.
            run_safe (bool): The default error handling mode for all callables executed
                through this runner. If True, exceptions are caught and logged,
                and the result is set to None in case of an error. If False, exceptions
                are propagated and must be handled by the caller. Defaults to True.
        """
        self.tasks: set[asyncio.Task] = set()
        """A set that stores all running or pending tasks
        associated with calls to the `run_async` method.
        """
        self.futures: set[asyncio.Future] = set()
        """A set that stores all running or pending futures
        associated with calls to the `run_sync` method.
        """
        self.executor = executor
        """An optional `concurrent.futures.Executor` object to be used
        for running synchronous functions in the `run_sync` method.
        """
        self.run_safe = run_safe
        """The default error handling mode for callables executed through
        this runner. Can be overridden per callable using decorators.
        """

    # region Common (private)

    @staticmethod
    def _log_task_or_future_done(
        task_or_future: Union[asyncio.Task, asyncio.Future],
        type_: Literal['Task', 'Future'],
        name: str,
    ) -> None:
        """Log the result of a completed asyncio Task or Future.

        Logs:
            - A debug message if it completed successfully or
            if a raised exception was caught or cancelled.
            - An warning with details if an exception was raised.

        Args:
            task_or_future: The Task or Future object to log.
            type_: Specifies whether the object is a "Task" or a "Future".
            name: The name of the Task or Future for identification in logs.
        """
        if task_or_future.cancelled():
            logger.debug('%s "%s" was cancelled', type_, name)
        elif task_or_future.exception() is None:
            logger.debug('%s "%s" finished', type_, name)
        else:
            exc = task_or_future.exception()
            exc_type, exc_desc = type(exc).__name__, str(exc)
            if exc_desc:
                logger.warning(
                    '%s "%s" raised an exception (%s: %s)',
                    type_,
                    name,
                    exc_type,
                    exc_desc,
                )
            else:
                logger.warning(
                    '%s "%s" raised an exception (%s)', type_, name, exc_type
                )

    @staticmethod
    def _log_caught_exception(
        exc: Exception,
        type_: Literal['Task', 'Future'],
        name: str,
    ) -> None:
        """Log a warning for an exception caught from a Task or Future
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
            logger.warning('%s "%s" failed (%s: %s)', type_, name, exc_type, exc_desc)
        else:
            logger.warning('%s "%s" failed (%s)', type_, name, exc_type)

    # endregion Common (private)

    # region Async

    @staticmethod
    def _get_awaitable_name(awaitable: Awaitable) -> str:
        """Retrieve a human-readable name of an awaitable object.

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

    @staticmethod
    async def _run_async_unsafe(
        coro: Coroutine[Any, Any, R],
        timeout: Optional[float] = None,
    ) -> R:
        """Run a coroutine function with the given arguments and timeout.

        Args:
            coro (Coroutine[Any, Any, R]): The coroutine function to run.
            timeout (Optional[float], optional): The timeout for the coroutine in
                seconds. Defaults to None.

        Returns:
            R: The result of the coroutine function.
        """
        if timeout is not None:
            return await asyncio.wait_for(coro, timeout=timeout)
        else:
            return await coro

    async def _run_async_safe(
        self,
        coro: Coroutine[Any, Any, R],
        timeout: Optional[float] = None,
    ) -> Optional[R]:
        """Wrap an awaitable in a coroutine with added error handling that
        catches and logs exceptions, including timeout errors. Note that the
        `asyncio.CancelledError` exceptions are re-raised to propagate cancellation.

        Args:
            coro (Coroutine[Any, Any, R]): The coroutine function to run.
            *args: Arguments to run the coroutine function with.
            timeout: Optional timeout in seconds. If provided, the coroutine
                will be cancelled if it doesn't complete within this time.

        Returns:
            Optional[T]: The result of the coroutine function if it completes
                successfully, `None` if an exception occurs (including timeout).
        """
        try:
            return await self._run_async_unsafe(coro, timeout=timeout)
        except asyncio.CancelledError:
            raise  # re-raise to ensure cancellation is propagated
        except asyncio.TimeoutError:
            func_name = self._get_awaitable_name(coro)
            logger.warning('Task "%s" timed out after %.3f seconds', func_name, timeout)
            return None
        except Exception as exc:
            awaitable_name = self._get_awaitable_name(coro)
            self._log_caught_exception(exc, 'Task', awaitable_name)
            return None

    def run_async(
        self,
        func: Callable[..., Coroutine[Any, Any, R]],
        *func_args: Any,
        run_safe: Optional[bool] = None,
        done_callback: Optional[Callable[[asyncio.Task], Any]] = None,
        timeout: Optional[Union[int, float]] = None,
    ) -> asyncio.Task:
        """Schedule a function that returns a coroutine to be run,
        optionally with error handling and a completion callback.

        This method is specifically designed for running coroutine functions
        that are asynchronous in nature. Providing a synchronous function to
        this method will fail at runtime.

        Args:
            func (Callable[..., Coroutine[Any, Any, T]]): The coroutine
                function to be run.
            *func_args (Any): The arguments to run the coroutine function with.
            run_safe (Optional[bool]): If True, the potential exceptions raised by
                the coroutine are caught and logged, and the result is set to
                None in case of an error. If False, exceptions are propagated
                and must be handled by the caller. If None, the effective error
                handling mode is determined based on decorators and session-wide
                settings. Defaults to None.
            done_callback (Optional[Callable[[asyncio.Task], Any]]):
                An optional callback to be called when the task completes.
            timeout (Optional[Union[int, float]]): If provided, the coroutine
                will be cancelled if it doesn't complete within this time (in seconds).
                When run_safe=True, timeout errors are caught and logged, returning None.
                When run_safe=False, timeout errors are propagated as asyncio.TimeoutError.

        Returns:
            asyncio.Task[Optional[T]]: An asyncio task object representing
                the scheduled coroutine. The task can be awaited to obtain
                the result of the coroutine function call or cancelled.
        """
        # determine the effective error handling mode
        run_safe_ = run_safe if run_safe is not None else self.run_safe

        func_name = self._get_func_name(func)
        logger.debug(
            'Scheduling task for "%s" (async, safe=%s, timeout=%s)',
            func_name,
            run_safe_,
            timeout,
        )

        # create the appropriate coroutine based on safety and timeout settings
        if run_safe_:
            coro = self._run_async_safe(coro=func(*func_args), timeout=timeout)
        else:
            coro = self._run_async_unsafe(coro=func(*func_args), timeout=timeout)
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(
            lambda t: self._log_task_or_future_done(t, 'Task', func_name)
        )
        if done_callback:
            task.add_done_callback(done_callback)

        return task

    # endregion Async

    # region Sync

    @staticmethod
    def _get_func_name(func: Callable) -> str:
        """Retrieve a human-readable name of a function.

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

    def _run_sync_safe(self, func: Callable[..., R], *args: Any) -> Optional[R]:
        """Call a synchronous function with added error handling that
        catches and logs exceptions. Note that the `asyncio.CancelledError` exceptions
        are re-raised to propagate cancellation.

        Args:
            func (Callable[..., T]): The synchronous function to run.
            *args (Any): Arguments to run the function with.

        Returns:
            Optional[T]: The result of the function if it completes
                successfully, or `None` if an exception occurs.
        """
        try:
            return func(*args)
        except asyncio.CancelledError:
            raise  # re-raise to ensure cancellation is propagated
        except Exception as exc:
            name = self._get_func_name(func)
            self._log_caught_exception(exc, 'Future', name)
            return None

    def run_sync(
        self,
        func: Callable[..., R],
        *func_args: Any,
        run_safe: Optional[bool] = None,
        run_blocking: bool = True,
        done_callback: Optional[Callable[[asyncio.Future], Any]] = None,
    ) -> asyncio.Future:
        """Schedule a synchronous function to be run in a blocking or
        a non-blocking manner, optionally with error handling and
        a completion callback.

        This method is specifically designed for synchronous functions that
        block. If `run_blocking` is set to True, the function is executed
        directly without using an executor. If `run_blocking` is set to False,
        the function is executed in a non-blocking manner using an executor,
        allowing for concurrent execution of multiple functions. Providing
        an asynchronous function will fail at runtime.

        Args:
            func (Callable[..., T]): The synchronous function to be run.
            *func_args (Any): The arguments to run the function with.
            run_safe (Optional[bool]): If True, the potential exceptions raised by
                the synchronous function are caught and logged, and the result
                is set to None in case of an error. If False, exceptions
                are propagated and must be handled by the caller. If None,
                the effective error handling mode is determined based on
                decorators and session-wide settings. Defaults to None.
            run_blocking (bool): If True, the synchronous function is executed
                in a blocking manner, i.e., called directly without using an
                executor. If False, the function is executed in a non-blocking
                manner in a separate thread. Defaults to True.
            done_callback (Optional[Callable[[asyncio.Future], Any]]):
                An optional callback to be called when the future completes.

        Returns:
            asyncio.Future[Optional[T]]: An asyncio future object representing
                the scheduled execution of the synchronous function.
                The future can be awaited to obtain the result of the function
                call. Note that cancellation of the future is not possible if
                the function is already running (for more information, see
                the `concurrent.futures` documentation on cancellation of
                the future objects).
        """
        # determine the effective error handling mode
        run_safe_ = run_safe if run_safe is not None else self.run_safe

        # get the event loop, prepare for scheduling the future
        func_name = self._get_func_name(func)
        logger.debug(
            'Scheduling future for "%s" (sync, blocking=%s, safe=%s)',
            func_name,
            run_blocking,
            run_safe_,
        )

        # create a future based on the blocking mode, add callbacks
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Optional[R]]
        if run_blocking:
            future = loop.create_future()
            try:
                if run_safe_:
                    result = self._run_sync_safe(func, *func_args)
                else:
                    result = func(*func_args)
                future.set_result(result)
            except Exception as exc:
                future.set_exception(exc)
        else:
            if run_safe_:
                func_ = partial(self._run_sync_safe, func)
                future = loop.run_in_executor(self.executor, func_, *func_args)
            else:
                future = loop.run_in_executor(self.executor, func, *func_args)
            # adding the future to the tracking set only makes sense
            # when running in a non-blocking manner in executor. Blocking calls are
            # already done by the time the future is returned.
            self.futures.add(future)
            future.add_done_callback(self.futures.discard)
        future.add_done_callback(
            lambda f: self._log_task_or_future_done(f, 'Future', func_name)
        )
        if done_callback:
            future.add_done_callback(done_callback)

        return future

    # endregion Sync

    # region Common

    @staticmethod
    def _validate_run_params(
        run_async: bool,
        run_safe: Optional[bool],
        run_blocking: bool,
        timeout: Optional[Union[int, float]] = None,
    ) -> None:
        """Validate the parameters for the `run` method.

        Args:
            run_async (bool): If True, the function is run as an asynchronous task.
                If False, the function is run as a synchronous future.
            run_safe (Optional[bool]): If True, exceptions are caught and logged,
                and the result is set to None in case of an error. If False,
                exceptions are propagated and must be handled by the caller.
                If None, the effective error handling mode is determined based
                on decorators and session-wide settings.
            run_blocking (bool): If True, the synchronous function is executed
                in a blocking manner. If False, it is executed in a non-blocking
                manner using an executor.
            timeout (Optional[Union[int, float]]): If provided, the function
                will be cancelled if it doesn't complete within this time (in seconds).

        Raises:
            ValueError: If `run_async` is True and `run_blocking` is False.
        """
        if run_async and run_blocking:
            raise ValueError(
                'Cannot run an asynchronous function in a blocking manner.'
            )
        if not run_async and timeout is not None:
            raise ValueError('Timeout is not applicable for synchronous functions.')

    def run(
        self,
        func: Union[Callable[..., Coroutine[Any, Any, R]], Callable[..., R]],
        *func_args: Any,
        run_async: bool,
        run_safe: Optional[bool] = None,
        run_blocking: bool = True,
        done_callback: Optional[Callable[[asyncio.Future], Any]] = None,
        timeout: Optional[Union[int, float]] = None,
    ) -> asyncio.Future[Optional[R]]:
        """Run a callable function, either synchronous or asynchronous,
        with optional error handling and a completion callback.

        Args:
            func (Union[Callable[..., Coroutine[Any, Any, T]], Callable[..., T]]):
                The function to be run, either synchronous or asynchronous.
            *func_args (Any): The arguments to run the function with.
            run_async (bool): If True, the function is run as an asynchronous
                task. If False, the function is run as a synchronous future.
            run_safe (Optional[bool]): If True, the potential exceptions raised by
                the function are caught and logged, and the result is set to
                None in case of an error. If False, exceptions are propagated
                and must be handled by the caller. If None, the effective error
                handling mode is determined based on decorators and session-wide
                settings. Defaults to None.
            run_blocking (bool): If True, the synchronous function is executed
                in a blocking manner. If False, it is executed in a non-blocking
                manner using an executor. Defaults to True.
            done_callback (Optional[Callable[[asyncio.Future], Any]]):
                An optional callback to be called when the future completes.
            timeout (Optional[Union[int, float]]): If provided, the function
                will be cancelled if it doesn't complete within this time (in seconds).
                Only applicable for asynchronous functions.

        Raises:
            ValueError: If the provided run flags are incompatible, such as
                running an asynchronous function in a blocking manner or
                providing a timeout for a synchronous function.

        Returns:
            asyncio.Future[Optional[R]]:
                An asyncio task or future object representing the scheduled
                execution of the function. The task or future can be awaited
                to obtain the result of the function call or cancelled.
        """
        self._validate_run_params(
            run_async=run_async,
            run_safe=run_safe,
            run_blocking=run_blocking,
            timeout=timeout,
        )
        if run_async:
            return self.run_async(
                cast(Callable[..., Coroutine[Any, Any, R]], func),
                *func_args,
                run_safe=run_safe,
                done_callback=done_callback,
                timeout=timeout,
            )
        else:
            return self.run_sync(
                cast(Callable[..., R], func),
                *func_args,
                run_safe=run_safe,
                run_blocking=run_blocking,
                done_callback=done_callback,
            )

    async def await_(self, futures: Iterable[Awaitable[Any]]) -> None:
        logger.debug('Awaiting futures')
        # convert to tuple in case the iterable is a generator
        futures = tuple(futures)
        try:
            await asyncio.gather(*futures)
        except Exception:
            await self.cancel(futures)
            raise

    async def await_all(self) -> None:
        """Wait for all scheduled asynchronous and synchronous tasks
        to complete.

        This method gathers all active asyncio tasks and futures and awaits for
        their completion. It is particularly useful for ensuring that
        all background operations have finished before proceeding to another
        stage of the application or gracefully shutting down the application.

        Note that this method ensures that the tracking sets of tasks and
        futures have been cleared after their completion, effectively resetting
        the runner's state.
        """
        logger.debug('Awaiting all tasks and futures')
        await self.await_(self.tasks)
        self.tasks.clear()
        await self.await_(self.futures)
        self.futures.clear()

    async def cancel(self, futures: Iterable[Awaitable[Any]]) -> None:  # noqa: PLR6301
        """Attempt to cancel a set of futures.

        This method attempts to cancel the provided future-like objects.

        Args:
            futures (Iterable[Awaitable]): An iterable of futures to cancel.
        """
        logger.debug('Cancelling futures')
        # convert to tuple in case the iterable is a generator
        futures = tuple(futures)
        # let the event loop run to allow for task cancellation
        # (helps if "cancel" is called right after a task is created)
        await asyncio.sleep(0)
        for future in futures:
            if isinstance(future, (asyncio.Future, asyncio.Task)):
                future.cancel()
        await asyncio.gather(*futures, return_exceptions=True)

    async def cancel_all(self) -> None:
        """Attempt to cancel all active tasks and futures.

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
        await self.cancel(self.tasks)
        self.tasks.clear()
        await self.cancel(self.futures)
        self.futures.clear()

    # endregion Common
