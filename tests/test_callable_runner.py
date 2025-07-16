import asyncio
import logging
import os
import tempfile
import threading
import time
from typing import Literal, Optional, Union
from unittest.mock import AsyncMock, MagicMock, create_autospec

import pytest

from freshpointsync._callable_runner import (
    CallableRunner,
    is_run_safe,
    run_safe,
    run_unsafe,
)

logger = logging.getLogger(__name__)


@pytest.fixture(name="runner", scope="module")
def fixture_runner():
    yield CallableRunner()


def get_mock_func(
    type_: Literal["sync", "async"], raise_exception: bool = False
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
    if type_ == "sync":
        func = MagicMock()
    elif type_ == "async":
        func = AsyncMock()
    else:
        raise ValueError(f"Invalid type: {type_}")
    func.__name__ = "foo"
    func.return_value = 42
    if raise_exception:
        func.side_effect = ValueError("ValueError")
    return func


@pytest.mark.asyncio
async def test_run_async_success(runner: CallableRunner):
    func = get_mock_func("async")
    task = runner.run_async(func)
    result = await task
    assert result == 42  # result is set to 42
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_async_exception_run_safe(runner: CallableRunner):
    func = get_mock_func("async", raise_exception=True)
    task = runner.run_async(func, run_safe=True)
    result = await task
    assert result is None  # ValueError is caught, result is set to None
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_async_exception_run_unsafe(runner: CallableRunner):
    func = get_mock_func("async", raise_exception=True)
    task = runner.run_async(func, run_safe=False)
    result = "notset"
    with pytest.raises(ValueError):
        result = await task
    assert result == "notset"  # ValueError is propagated, result is not changed
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_success(runner: CallableRunner):
    func = get_mock_func("sync")
    task = runner.run_sync(func)
    result = await task
    assert result == 42  # result is set to 42
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_exception_run_safe(runner: CallableRunner):
    func = get_mock_func("sync", raise_exception=True)
    task = runner.run_sync(func, run_safe=True)
    result = -1
    result = await task
    assert result is None  # ValueError is caught, result is set to None
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_exception_run_unsafe(runner: CallableRunner):
    func = get_mock_func("sync", raise_exception=True)
    task = runner.run_sync(func, run_safe=False)
    result = "notset"
    with pytest.raises(ValueError):
        result = await task
    assert result == "notset"  # ValueError is propagated, result is not changed
    func.assert_called_once()


@pytest.mark.asyncio
async def test_run_sync_with_params(runner: CallableRunner):
    def concat(foo: str, bar: str) -> str:
        """Used as a source for `create_autospec`."""
        return f"{foo}{bar}"

    func = create_autospec(concat)
    func.return_value = "foobar"
    task = runner.run_sync(func, "foo", "bar")
    result = await task
    assert result == "foobar"
    func.assert_called_once_with("foo", "bar")


@pytest.mark.asyncio
async def test_await_all(runner: CallableRunner):
    func1 = get_mock_func("async")
    func2 = get_mock_func("async")
    func3 = get_mock_func("sync")
    func4 = get_mock_func("sync")
    task1 = runner.run_async(func1)
    task2 = runner.run_async(func2)
    task3 = runner.run_sync(func3)
    task4 = runner.run_sync(func4)
    await runner.await_all()
    func1.assert_called_once()
    func2.assert_called_once()
    func3.assert_called_once()
    func4.assert_called_once()
    assert task1.done() is True
    assert task2.done() is True
    assert task3.done() is True
    assert task4.done() is True


@pytest.mark.asyncio
async def test_await_all_exception_run_safe(runner: CallableRunner):
    func1 = get_mock_func("async")
    func2 = get_mock_func("async", raise_exception=True)
    task1 = runner.run_async(func1)
    task2 = runner.run_async(func2, run_safe=True)
    await runner.await_all()
    func1.assert_called_once()
    func2.assert_called_once()
    assert task1.done() is True
    assert task2.done() is True
    assert task1.result() == 42
    assert task2.result() is None


@pytest.mark.asyncio
async def test_await_all_exception_run_unsafe(runner: CallableRunner):
    # sync that raises is discarded right away, so it's necessary to test with async
    func1 = get_mock_func("async")
    func2 = get_mock_func("async", raise_exception=True)
    task1 = runner.run_async(func1)
    task2 = runner.run_async(func2, run_safe=False)
    with pytest.raises(ValueError):
        await runner.await_all()
    func1.assert_called_once()
    func2.assert_called_once()
    assert task1.done() is True
    assert task2.done() is True
    assert task1.result() == 42
    with pytest.raises(ValueError):
        task2.result()
    # cleanup task1
    try:
        await task1
    except Exception:  # noqa: S110
        pass


@pytest.mark.asyncio
async def test_cancel_all(runner: CallableRunner):
    def sync_func():
        for _ in range(2):
            time.sleep(0.5)
        return 42

    async def async_func():
        for _ in range(2):
            await asyncio.sleep(0.5)
        return 42

    task1 = runner.run_async(async_func, run_safe=True)
    task2 = runner.run_async(async_func, run_safe=True)
    task3 = runner.run_sync(sync_func, run_blocking=False, run_safe=True)
    task4 = runner.run_sync(sync_func, run_blocking=False, run_safe=True)
    await runner.cancel_all()
    assert task1.cancelled() is True
    assert task2.cancelled() is True
    assert task3.cancelled() is True
    assert task4.cancelled() is True


@pytest.fixture(name="file_path", scope="function")
def fixture_file_path():
    with tempfile.TemporaryDirectory() as tmp_dir:
        temp_file = os.path.join(tmp_dir, f"temp_{id(tmp_dir)}")
        yield temp_file


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "run_blocking, lock, iter_count",
    [
        pytest.param(
            False,
            None,
            42,
            marks=pytest.mark.xfail(
                reason=(
                    "Shared resource access without proper locking "
                    "can lead to data corruption"
                )
            ),
        ),
        pytest.param(False, threading.Lock(), 42),
        pytest.param(True, None, 42),
    ],
)
async def test_run_sync(file_path, run_blocking, lock, iter_count):
    def append_to_file(
        file_path: str,
        phrase: str,
        lock: Optional[threading.Lock] = None,
        count: int = 0,
    ) -> None:
        if lock:
            lock.acquire()
        logger.info("Appending %-8s\t(%s%s)", phrase, phrase[0], count)
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(f"{phrase}\n")
        logger.info("Appended %-8s\t(%s%s)", phrase, phrase[0], count)
        if lock:
            lock.release()

    logger.info(
        "test_run_sync params: Run blocking: %s; Lock() used: %s; Iteration "
        "count: %s, phrases: %s",
        run_blocking,
        lock is not None,
        iter_count,
        '"rock" (r), "paper" (p), "scissors" (s)',
    )

    runner = CallableRunner()
    for i in range(1, iter_count + 1):
        runner.run_sync(
            append_to_file,
            file_path,
            "rock",
            lock,
            i,
            run_blocking=run_blocking,
        )
        runner.run_sync(
            append_to_file,
            file_path,
            "paper",
            lock,
            i,
            run_blocking=run_blocking,
        )
        runner.run_sync(
            append_to_file,
            file_path,
            "scissors",
            lock,
            i,
            run_blocking=run_blocking,
        )
    await runner.await_all()

    with open(file_path, "r", encoding="utf-8") as f:  # noqa
        contents = f.read()

    for phrase in ["rock", "paper", "scissors"]:
        contents = contents.replace(phrase, "")
    contents = contents.strip()
    assert not contents


# Tests for decorator functionality and session-wide error handling


class TestDecoratorFunctionality:
    """Tests for @run_safe and @run_unsafe decorators."""

    def test_run_safe_decorator_marking(self):
        """Test that @run_safe decorator marks functions correctly."""

        @run_safe
        def test_func():
            return "test"

        assert is_run_safe(test_func) is True
        assert hasattr(test_func, "_run_safe")

    def test_run_unsafe_decorator_marking(self):
        """Test that @run_unsafe decorator marks functions correctly."""

        @run_unsafe
        def test_func():
            return "test"

        assert is_run_safe(test_func) is False
        assert hasattr(test_func, "_run_safe")

    def test_undecorated_function_marking(self):
        """Test that undecorated functions return None."""

        def test_func():
            return "test"

        assert is_run_safe(test_func) is None

    def test_both_decorators_applied(self):
        """Test precedence when both decorators are applied."""

        @run_unsafe
        @run_safe
        def test_func():
            return "test"

        # The outer decorator (@run_unsafe) should take precedence
        assert is_run_safe(test_func) is False

    @pytest.mark.asyncio
    async def test_run_safe_decorator_overrides_session_unsafe(self):
        """Test that @run_safe overrides session-wide unsafe mode."""
        runner = CallableRunner(run_safe=False)  # Session-wide unsafe mode

        @run_safe
        async def test_func():
            raise ValueError("test error")

        # Should be safe due to decorator, despite session-wide unsafe mode
        task = runner.run_async(test_func, run_safe=None)
        result = await task
        assert result is None  # Exception caught and logged

    @pytest.mark.asyncio
    async def test_run_unsafe_decorator_overrides_session_safe(self):
        """Test that @run_unsafe overrides session-wide safe mode."""
        runner = CallableRunner(run_safe=True)  # Session-wide safe mode

        @run_unsafe
        async def test_func():
            raise ValueError("test error")

        # Should be unsafe due to decorator, despite session-wide safe mode
        task = runner.run_async(test_func, run_safe=None)
        with pytest.raises(ValueError, match="test error"):
            await task

    @pytest.mark.asyncio
    async def test_explicit_parameter_overrides_decorator(self):
        """Test that explicit run_safe parameter overrides decorator."""
        runner = CallableRunner(run_safe=True)

        @run_unsafe
        async def test_func():
            raise ValueError("test error")

        # Explicit run_safe=True should override @run_unsafe
        task = runner.run_async(test_func, run_safe=True)
        result = await task
        assert result is None  # Exception caught due to explicit parameter

    @pytest.mark.asyncio
    async def test_session_safe_mode_with_no_decorator(self):
        """Test session-wide safe mode with undecorated function."""
        runner = CallableRunner(run_safe=True)

        async def test_func():
            raise ValueError("test error")

        task = runner.run_async(test_func, run_safe=None)
        result = await task
        assert result is None  # Exception caught due to session-wide safe mode

    @pytest.mark.asyncio
    async def test_session_unsafe_mode_with_no_decorator(self):
        """Test session-wide unsafe mode with undecorated function."""
        runner = CallableRunner(run_safe=False)

        async def test_func():
            raise ValueError("test error")

        task = runner.run_async(test_func, run_safe=None)
        with pytest.raises(ValueError, match="test error"):
            await task

    @pytest.mark.asyncio
    async def test_sync_function_with_decorators(self):
        """Test that decorators work with sync functions."""
        runner = CallableRunner(run_safe=False)

        @run_safe
        def test_func():
            raise ValueError("test error")

        future = runner.run_sync(test_func, run_safe=None)
        result = await future
        assert result is None  # Exception caught due to decorator


class TestSessionWideErrorHandling:
    """Tests for session-wide error handling mode."""

    def test_default_session_mode(self):
        """Test that default session mode is safe."""
        runner = CallableRunner()
        assert runner.run_safe is True

    def test_explicit_session_safe_mode(self):
        """Test explicit safe session mode."""
        runner = CallableRunner(run_safe=True)
        assert runner.run_safe is True

    def test_explicit_session_unsafe_mode(self):
        """Test explicit unsafe session mode."""
        runner = CallableRunner(run_safe=False)
        assert runner.run_safe is False

    @pytest.mark.asyncio
    async def test_precedence_order(self):
        """Test the precedence order: explicit parameter > decorator > session."""
        runner = CallableRunner(run_safe=False)  # Session default: unsafe

        @run_safe  # Decorator: safe
        async def test_func():
            raise ValueError("test error")

        # Test 1: Explicit parameter takes precedence over decorator
        task1 = runner.run_async(test_func, run_safe=False)  # Explicit: unsafe
        with pytest.raises(ValueError):
            await task1

        # Test 2: Decorator takes precedence over session default
        task2 = runner.run_async(test_func, run_safe=None)  # Use decorator
        result = await task2
        assert result is None  # Safe due to decorator

        # Test 3: Session default when no decorator and no explicit parameter
        async def undecorated_func():
            raise ValueError("test error")

        task3 = runner.run_async(undecorated_func, run_safe=None)
        with pytest.raises(ValueError):
            await task3  # Unsafe due to session default
