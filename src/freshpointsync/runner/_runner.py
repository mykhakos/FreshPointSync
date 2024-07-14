import asyncio
import inspect
import logging
from concurrent.futures import Executor
from functools import partial
from typing import (
    Any,
    Awaitable,
    Callable,
    Coroutine,
    Literal,
    Optional,
    TypeVar,
    Union,
)

logger = logging.getLogger('freshpointsync.runner')
"""Logger for the `freshpointsync.runner` package."""


T = TypeVar('T')


class CallableRunner:
    """A utility for running asynchronous and synchronous callables in
    a non-blocking or blocking manner (the latter is only relevant for
    synchronous callables) with optional error handling and the ability to
    await or cancel all running tasks.
    """

    def __init__(self, executor: Optional[Executor] = None) -> None:
        """Initialize a `CallableRunner` instance with an optional executor.

        Args:
            executor (Optional[Executor]): A `concurrent.futures.Executor`
                object to be used for running synchronous callables in
                a non-blocking manner. If None, a default executor is used.
                For more information, see the asyncio event loop's
                `run_in_executor` documentation. Defaults to None.
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
            logger.warning(
                '%s "%s" failed (%s: %s)', type_, name, exc_type, exc_desc
            )
        else:
            logger.warning('%s "%s" failed (%s)', type_, name, exc_type)

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

    async def _run_async_safe(self, awaitable: Awaitable[T]) -> Optional[T]:
        """Wrap an awaitable in a coroutine with added error handling that
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
            self._log_caught_exception(exc, 'Task', awaitable_name)
            return None

    def run_async(
        self,
        func: Callable[..., Coroutine[Any, Any, T]],
        *func_args: Any,
        run_safe: bool = True,
        done_callback: Optional[Callable[[asyncio.Task], Any]] = None,
    ) -> 'asyncio.Task[Optional[T]]':
        """Schedule a function that returns a coroutine to be run,
        optionally with error handling and a completion callback.

        This method is specifically designed for running coroutine functions
        that are asynchronous in nature. Providing a synchronous function to
        this method will fail at runtime.

        Args:
            func (Callable[..., Coroutine[Any, Any, T]]): The coroutine
                function to be run.
            *func_args (Any): The arguments to run the coroutine function with.
            run_safe (bool): If True, the potential exceptions raised by
                the coroutine are caught and logged, and the result is set to
                None in case of an error. If False, exceptions are propagated
                and must be handled by the caller. Defaults to True.
            done_callback (Optional[Callable[[asyncio.Task], Any]]):
                An optional callback to be called when the task completes.

        Returns:
            asyncio.Task[Optional[T]]: An asyncio task object representing
                the scheduled coroutine. The task can be awaited to obtain
                the result of the coroutine function call or cancelled.
        """
        func_name = self._get_func_name(func)
        logger.debug(
            'Scheduling task for "%s" (async, safe=%s)',
            func_name,
            run_safe,
        )
        if run_safe:
            task = asyncio.create_task(self._run_async_safe(func(*func_args)))
        else:
            task = asyncio.create_task(func(*func_args))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(
            lambda t: self._log_task_or_future_done(t, 'Task', func_name)
        )
        if done_callback:
            task.add_done_callback(done_callback)
        return task

    @staticmethod
    def _get_func_name(func: Callable[..., T]) -> str:
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

    def _run_sync_safe(self, func: Callable[..., T], *args: Any) -> Optional[T]:
        """Call a synchronous function with added error handling that
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
            self._log_caught_exception(exc, 'Future', name)
            return None

    def run_sync(
        self,
        func: Callable[..., T],
        *func_args: Any,
        run_safe: bool = True,
        run_blocking: bool = True,
        done_callback: Optional[Callable[[asyncio.Future], Any]] = None,
    ) -> 'asyncio.Future[Optional[T]]':
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
            run_safe (bool): If True, the potential exceptions raised by
                the synchronous function are caught and logged, and the result
                is set to None in case of an error. If False, exceptions
                are propagated and must be handled by the caller.
                Defaults to True.
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
        # get the event loop, prepare for scheduling the future
        name = self._get_func_name(func)
        loop = asyncio.get_running_loop()
        future: asyncio.Future[Optional[T]]
        # schedule the future based on the blocking mode
        logger.debug(
            'Scheduling future for "%s" (sync, blocking=%s, safe=%s)',
            name,
            run_blocking,
            run_safe,
        )
        if run_blocking:
            future = loop.create_future()
            try:
                if run_safe:
                    result = self._run_sync_safe(func, *func_args)
                else:
                    result = func(*func_args)
                future.set_result(result)
            except Exception as e:
                future.set_exception(e)
        else:
            if run_safe:
                func_ = partial(self._run_sync_safe, func)
                future = loop.run_in_executor(self.executor, func_, *func_args)
            else:
                future = loop.run_in_executor(self.executor, func, *func_args)
            self.futures.add(future)
            future.add_done_callback(self.futures.discard)
        # add a callback to log the completion of the future
        future.add_done_callback(
            lambda f: self._log_task_or_future_done(f, 'Future', name)
        )
        # add an optional callback to be called when the future completes
        if done_callback:
            future.add_done_callback(done_callback)
        return future

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
        tasks = set(self.tasks)
        futures = set(self.futures)
        await asyncio.gather(*tasks, *futures)
        self.tasks.clear()
        self.futures.clear()

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
