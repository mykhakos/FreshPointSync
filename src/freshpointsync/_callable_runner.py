import asyncio
import inspect
import logging
from typing import (
    Any,
    Awaitable,
    Callable,
    Iterable,
    Optional,
    TypeVar,
    Union,
)

logger = logging.getLogger('freshpointsync.runner')
"""Logger for the `freshpointsync.runner` package."""


R = TypeVar('R')


class AwaitableRunner:
    """A utility for running asynchronous callables in a non-blocking manner
    with optional error handling and the ability to await or cancel all running tasks.
    """

    def __init__(self, run_safe: bool = True) -> None:
        """Initialize an `AsyncCallableRunner` instance with an error handling mode.

        Args:
            run_safe (bool): The default error handling mode for all callables executed
                through this runner. If True, exceptions are caught and logged,
                and the result is set to None in case of an error. If False, exceptions
                are propagated and must be handled by the caller. Defaults to True.
        """
        self.tasks: set[asyncio.Task] = set()
        """A set that stores all running or pending tasks
        associated with calls to the `run` method.
        """
        self.run_safe = run_safe
        """The default error handling mode for callables executed through
        this runner. Can be overridden per callable using decorators.
        """

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
    def _log_task_done(task: asyncio.Task, task_name: str) -> None:
        """Log the result of a completed asyncio Task.

        Args:
            task: The Task object to log.
            task_name: The name of the Task for identification in logs.
        """
        if task.cancelled():
            logger.debug('Task "%s" was cancelled', task_name)
        elif task.exception() is None:
            logger.debug('Task "%s" finished', task_name)
        else:
            exc = task.exception()
            exc_type, exc_desc = type(exc).__name__, str(exc)
            if exc_desc:
                logger.warning(
                    'Task "%s" raised an exception (%s: %s)',
                    task_name,
                    exc_type,
                    exc_desc,
                )
            else:
                logger.warning(
                    'Task "%s" raised an exception (%s)',
                    task_name,
                    exc_type,
                )

    @staticmethod
    def _log_caught_timeout(timeout: Optional[float], task_name: str) -> None:
        """Log a warning for a timeout caught from a Task in a safe runner.

        Args:
            timeout: The timeout duration in seconds.
            task_name: The name of the Task for identification in logs.

        """
        if timeout is not None:
            logger.warning('Task "%s" timed out after %.3f seconds', task_name, timeout)
        else:
            logger.warning('Task "%s" timed out', task_name)

    @staticmethod
    def _log_caught_exception(exc: Exception, task_name: str) -> None:
        """Log a warning for an exception caught from a Task in a safe runner.

        Args:
            exc: The exception instance that was caught.
            task_name: The name of the Task for identification in logs.
        """
        exc_type, exc_desc = type(exc).__name__, str(exc)
        if exc_desc:
            logger.warning('Task "%s" failed (%s: %s)', task_name, exc_type, exc_desc)
        else:
            logger.warning('Task "%s" failed (%s)', task_name, exc_type)

    @staticmethod
    async def _run_unsafe(
        awaitable: Awaitable[R], timeout: Optional[float] = None
    ) -> R:
        """Run an awaitable with the given timeout.

        Args:
            awaitable (Awaitable[R]): The awaitable to run.
            timeout (Optional[float], optional): The timeout for the awaitable in
                seconds. Defaults to None.

        Returns:
            R: The result of the awaitable.
        """
        if timeout is None:
            return await awaitable
        return await asyncio.wait_for(awaitable, timeout=timeout)

    async def _run_safe(
        self, awaitable: Awaitable[R], timeout: Optional[float] = None
    ) -> Optional[R]:
        """Wrap an awaitable with added error handling that catches and logs
        exceptions, including timeout errors. Note that the `asyncio.CancelledError`
        exceptions are re-raised to propagate cancellation.

        Args:
            awaitable (Awaitable[R]): The awaitable to run.
            timeout: Optional timeout in seconds. If provided, the awaitable
                will be cancelled if it doesn't complete within this time.

        Returns:
            Optional[R]: The result of the awaitable if it completes
                successfully, `None` if an exception occurs (including timeout).
        """
        try:
            return await self._run_unsafe(awaitable, timeout=timeout)
        except asyncio.CancelledError:
            raise  # re-raise to ensure cancellation is propagated
        except asyncio.TimeoutError:
            name = self._get_awaitable_name(awaitable)
            self._log_caught_timeout(timeout, name)
            return None
        except Exception as exc:
            name = self._get_awaitable_name(awaitable)
            self._log_caught_exception(exc, name)
            return None

    def run(
        self,
        awaitable: Awaitable[R],
        *,
        done_callback: Optional[Callable[[asyncio.Task], Any]] = None,
        run_safe: Optional[bool] = None,
        timeout: Optional[Union[int, float]] = None,
    ) -> asyncio.Task[Optional[R]]:
        """Schedule a coroutine function or awaitable to be run,
        optionally with error handling and a completion callback.

        Args:
            awaitable (Awaitable[R]):
                An awaitable to be scheduled directly.
            run_safe (Optional[bool]): If True, the potential exceptions raised by
                the awaitable are caught and logged, and the result is set to
                None in case of an error. If False, exceptions are propagated
                and must be handled by the caller. If None, the effective error
                handling mode is determined based on decorators and session-wide
                settings. Defaults to None.
            done_callback (Optional[Callable[[asyncio.Task], Any]]):
                An optional callback to be called when the task completes.
            timeout (Optional[Union[int, float]]): If provided, the awaitable
                will be cancelled if it doesn't complete within this time (in seconds).
                When run_safe=True, timeout errors are caught and logged, returning None.
                When run_safe=False, timeout errors are propagated as asyncio.TimeoutError.

        Returns:
            asyncio.Task[Optional[R]]: An asyncio task object representing
                the scheduled execution. The task can be awaited to obtain
                the result or cancelled.
        """
        # determine the effective error handling mode
        run_safe_ = run_safe if run_safe is not None else self.run_safe

        awaitable_name = self._get_awaitable_name(awaitable)

        logger.debug(
            'Scheduling task for "%s" (safe=%s, timeout=%s)',
            awaitable_name,
            run_safe_,
            timeout,
        )

        # create the appropriate coroutine based on safety and timeout settings
        if run_safe_:
            coro = self._run_safe(awaitable, timeout=timeout)
        else:
            coro = self._run_unsafe(awaitable, timeout=timeout)
        task = asyncio.create_task(coro)
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        task.add_done_callback(lambda task: self._log_task_done(task, awaitable_name))
        if done_callback:
            task.add_done_callback(done_callback)

        return task

    async def await_(self, tasks: Iterable[Awaitable[Any]]) -> None:
        """Wait for a set of tasks to complete.

        Args:
            tasks (Iterable[Awaitable[Any]]): An iterable of tasks to await.
        """
        logger.debug('Awaiting tasks')
        tasks = tuple(tasks)
        try:
            await asyncio.gather(*tasks)
        except Exception:
            await self.cancel(tasks)
            raise

    async def await_all(self) -> None:
        """Wait for all scheduled asynchronous tasks to complete.

        This method gathers all active asyncio tasks and awaits for
        their completion. It is particularly useful for ensuring that
        all background operations have finished before proceeding to another
        stage of the application or gracefully shutting down the application.

        Note that this method ensures that the tracking set of tasks has been
        cleared after their completion, effectively resetting the runner's state.
        """
        logger.debug('Awaiting all tasks')
        await self.await_(self.tasks)
        self.tasks.clear()

    async def cancel(self, tasks: Iterable[Awaitable[Any]]) -> None:  # noqa: PLR6301
        """Attempt to cancel a set of tasks.

        This method attempts to cancel the provided task objects.

        Args:
            tasks (Iterable[Awaitable]): An iterable of tasks to cancel.
        """
        logger.debug('Cancelling tasks')
        tasks = tuple(tasks)
        # let the event loop run to allow for task cancellation
        # (helps if "cancel" is called right after a task is created)
        await asyncio.sleep(0)
        for task in tasks:
            try:
                task.cancel()  # type: ignore[no-untyped-call]
            except AttributeError:
                pass
        await asyncio.gather(*tasks, return_exceptions=True)

    async def cancel_all(self) -> None:
        """Attempt to cancel all active tasks.

        This method gathers and cancels all active asyncio tasks.
        The method is particularly useful for cancelling all background
        operations before proceeding to another stage of the application
        or gracefully shutting down the application.

        Note that this method ensures that the tracking set of tasks has been
        cleared after their completion.
        """
        logger.debug('Cancelling all tasks')
        await self.cancel(self.tasks)
        self.tasks.clear()
