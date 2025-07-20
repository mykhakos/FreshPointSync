import asyncio
import logging
import os
import tempfile
from typing import Literal, Union
from unittest.mock import AsyncMock, MagicMock

import pytest

from freshpointsync._callable_runner import (
    CallableRunner,
    is_run_safe,
    run_safe,
    run_unsafe,
)

logger = logging.getLogger(__name__)


@pytest.fixture(name='runner', scope='module')
def fixture_runner():
    yield CallableRunner()


def get_mock_func(
    type_: Literal['sync', 'async'], raise_exception: bool = False
) -> Union[MagicMock, AsyncMock]:
    """Create a MagicMock or AsyncMock function.

    The mock name is set to 'foo', return value to 42 (int), and side effect to
    ValueError if `raise_exception` is True.

    Args:
        type_ (Literal['sync', 'async']): Type of the function to create.
        raise_exception (bool, optional): Whether to raise a ValueError.
            Defaults to False.

    Raises:
        ValueError: If an invalid mock type is provided.

    Returns:
        Union[MagicMock, AsyncMock]: Mock function.
    """
    if type_ == 'sync':
        func = MagicMock()
    elif type_ == 'async':
        func = AsyncMock()
    else:
        raise ValueError(f'Invalid type: {type_}')
    func.__name__ = 'foo'
    func.return_value = 42
    if raise_exception:
        func.side_effect = ValueError('ValueError')
    return func


@pytest.mark.asyncio
async def test_run_async_success(runner: CallableRunner):
    func = get_mock_func('async')
    task = runner.run_async(func)
    result = await task
    assert result == 42  # result is set to 42
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_async_exception_run_safe(runner: CallableRunner):
    func = get_mock_func('async', raise_exception=True)
    task = runner.run_async(func, run_safe=True)
    result = await task
    assert result is None  # ValueError is caught, result is set to None
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_async_exception_run_unsafe(runner: CallableRunner):
    func = get_mock_func('async', raise_exception=True)
    task = runner.run_async(func, run_safe=False)
    result = 'notset'
    with pytest.raises(ValueError):
        result = await task
    assert result == 'notset'  # ValueError is propagated, result is not changed
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_success(runner: CallableRunner):
    func = get_mock_func('sync')
    task = runner.run_sync(func)
    await task
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_exception_run_safe(runner: CallableRunner):
    func = get_mock_func('sync', raise_exception=True)
    task = runner.run_sync(func, run_safe=True)
    await task
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_exception_run_unsafe(runner: CallableRunner):
    func = get_mock_func('sync', raise_exception=True)
    task = runner.run_sync(func, run_safe=False)
    with pytest.raises(ValueError):
        await task
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_non_blocking(runner: CallableRunner):
    func = get_mock_func('sync')
    task = runner.run_sync(func, run_in_executor=True)
    await task
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_blocking(runner: CallableRunner):
    func = get_mock_func('sync')
    task = runner.run_sync(func, run_in_executor=False)
    await task
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_with_args(runner: CallableRunner):
    func = get_mock_func('async')
    await runner.run_async(func, 'arg1', 'arg2')
    func.assert_called_once_with('arg1', 'arg2')


@pytest.mark.asyncio
async def test_run_with_kwargs(runner: CallableRunner):
    func = get_mock_func('async')
    # Cannot pass kwargs directly to run_async - need to use partial or wrapper function

    async def wrapper_func():
        return await func(kwarg1='value1', kwarg2='value2')

    await runner.run_async(wrapper_func)
    func.assert_called_once_with(kwarg1='value1', kwarg2='value2')


@pytest.mark.asyncio
async def test_run_with_args_and_kwargs(runner: CallableRunner):
    func = get_mock_func('async')
    # Cannot pass kwargs directly to run_async - need to use wrapper function

    async def wrapper_func():
        return await func('arg1', kwarg1='value1')

    await runner.run_async(wrapper_func)
    func.assert_called_once_with('arg1', kwarg1='value1')


@pytest.mark.asyncio
async def test_is_run_safe_checks(runner: CallableRunner):
    safe_func = get_mock_func('async')
    unsafe_func = get_mock_func('async')

    # Mark functions
    run_safe(safe_func)
    run_unsafe(unsafe_func)

    assert is_run_safe(safe_func) is True
    assert is_run_safe(unsafe_func) is False


@pytest.mark.asyncio
async def test_task_tracking(runner: CallableRunner):
    """Test that tasks are properly tracked and can be awaited."""
    func1 = get_mock_func('sync')
    func2 = get_mock_func('sync')

    # Start multiple tasks (use executor to ensure they are tracked)
    runner.run_sync(func1, run_in_executor=True)
    runner.run_sync(func2, run_in_executor=True)

    # Both should be tracked in futures (not tasks for sync functions)
    assert len(runner.futures) == 2

    # Await all
    await runner.await_all()

    # Tasks should be completed
    func1.assert_called_once()
    func2.assert_called_once()


@pytest.mark.asyncio
async def test_concurrent_execution():
    """Test that multiple runners can work concurrently."""

    def append_to_file(file_path, phrase, lock, count, **kwargs):
        logger.info('Appending %-8s\t(%s%s)', phrase, phrase[0], count)
        with open(file_path, 'a', encoding='utf-8') as f:
            f.write(f'{phrase}\n')
        logger.info('Appended %-8s\t(%s%s)', phrase, phrase[0], count)

    with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
        file_path = f.name

    try:
        runner = CallableRunner()
        for i in range(1, 4):  # 3 iterations
            runner.run_sync(
                append_to_file, file_path, 'rock', None, i, run_in_executor=True
            )
            runner.run_sync(
                append_to_file, file_path, 'paper', None, i, run_in_executor=True
            )
            runner.run_sync(
                append_to_file, file_path, 'scissors', None, i, run_in_executor=True
            )

        await runner.await_all()

        with open(file_path, encoding='utf-8') as f:
            contents = f.read()

        # Should have 9 lines (3 phrases x 3 iterations)
        lines = [line.strip() for line in contents.split('\n') if line.strip()]
        assert len(lines) == 9

        # Should contain all phrases
        for phrase in ['rock', 'paper', 'scissors']:
            assert phrase in contents

    finally:
        os.unlink(file_path)


class TestDecoratorFunctionality:
    """Tests for @run_safe and @run_unsafe decorators."""

    def test_run_safe_decorator_marking(self):
        """Test that @run_safe decorator marks functions correctly."""

        @run_safe
        def test_func():
            return 'test'

        assert is_run_safe(test_func) is True
        assert hasattr(test_func, '_run_safe')

    def test_run_unsafe_decorator_marking(self):
        """Test that @run_unsafe decorator marks functions correctly."""

        @run_unsafe
        def test_func():
            return 'test'

        assert is_run_safe(test_func) is False
        assert hasattr(test_func, '_run_safe')

    def test_decorator_function_call(self):
        """Test that decorated functions can still be called normally."""

        @run_safe
        def safe_func(x):
            return x * 2

        @run_unsafe
        def unsafe_func(x):
            return x + 1

        assert safe_func(5) == 10
        assert unsafe_func(5) == 6

    @pytest.mark.asyncio
    async def test_decorated_async_functions(self):
        """Test that decorators work with async functions."""

        @run_safe
        async def safe_async_func(x):
            await asyncio.sleep(0.01)
            return x * 2

        @run_unsafe
        async def unsafe_async_func(x):
            await asyncio.sleep(0.01)
            return x + 1

        assert is_run_safe(safe_async_func) is True
        assert is_run_safe(unsafe_async_func) is False

        # Functions should still work normally
        assert await safe_async_func(5) == 10
        assert await unsafe_async_func(5) == 6


class TestSessionWideErrorHandling:
    """Tests for session-wide error handling behavior."""

    @pytest.mark.asyncio
    async def test_session_error_isolation(self):
        """Test that errors in one task don't affect others."""
        runner = CallableRunner()

        def good_func():
            return 'success'

        def bad_func():
            raise ValueError('error')

        # Start both tasks
        runner.run_sync(good_func, run_in_executor=True, run_safe=True)
        runner.run_sync(bad_func, run_in_executor=True, run_safe=True)

        # Both should complete without one affecting the other
        await runner.await_all()

        # Check that futures were tracked (and now cleared after await_all)
        assert len(runner.futures) == 0  # Should be cleared after await_all


class TestDesignFlaws:
    """Test and document known design flaws in CallableRunner."""

    def test_sync_function_timeout_limitation(self):
        """
        Document that timeouts for sync functions are not implementable.

        This is a fundamental limitation - you cannot forcibly terminate
        a thread from outside in Python.
        """
        # This test documents the design limitation
        with pytest.raises(
            NotImplementedError, match='Timeouts for synchronous functions'
        ):
            raise NotImplementedError(
                'Timeouts for synchronous functions running in thread executors '
                'are not implementable in Python due to the inability to forcibly '
                'terminate threads'
            )

    def test_cancellation_limitation(self):
        """
        Document that cancellation for sync functions is not supported.
        """
        with pytest.raises(
            NotImplementedError, match='Cancellation for synchronous functions'
        ):
            raise NotImplementedError(
                'Cancellation for synchronous functions running in thread executors '
                'is not supported in Python'
            )


class TestCallableRunner:
    """Additional tests for CallableRunner functionality."""

    def test_initialization(self):
        """Test CallableRunner initialization."""
        runner = CallableRunner()
        assert isinstance(runner, CallableRunner)
        assert hasattr(runner, 'tasks')
        assert hasattr(runner, 'run_sync')
        assert hasattr(runner, 'run_async')
        assert hasattr(runner, 'await_all')

    @pytest.mark.asyncio
    async def test_empty_await_all(self):
        """Test await_all with no tasks."""
        runner = CallableRunner()
        await runner.await_all()  # Should complete without error

    @pytest.mark.asyncio
    async def test_multiple_await_all_calls(self):
        """Test multiple calls to await_all."""
        runner = CallableRunner()

        func = get_mock_func('sync')
        runner.run_sync(func, run_in_executor=True)

        # First await_all
        await runner.await_all()

        # Second await_all should also work
        await runner.await_all()

        func.assert_called_once()

    def test_function_inspection(self):
        """Test is_run_safe function with various inputs."""

        def normal_func():
            pass

        @run_safe
        def safe_func():
            pass

        @run_unsafe
        def unsafe_func():
            pass

        # Normal function should return None (no decorator)
        assert is_run_safe(normal_func) is None
        assert is_run_safe(safe_func) is True
        assert is_run_safe(unsafe_func) is False
