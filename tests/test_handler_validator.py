import pytest
from freshpointsync.update import HandlerValidator


async def async_handler_valid(arg):
    """Valid asynchronous handler, expects one parameter."""
    pass


async def async_handler_invalid():
    """Invalid asynchronous handler, expects no parameters."""
    pass


def sync_handler_valid(arg):
    """Valid synchronous handler, expects one parameter."""
    pass


def sync_handler_invalid():
    """Invalid synchronous handler, expects no parameters."""
    pass


class AsyncCallableClassValid:
    """Valid asynchronous callable class,
    (implements async `__call__` method, expects one parameter).
    """

    async def __call__(self, arg):
        pass


class AsyncCallableClassInvalid:
    """Inalid asynchronous callable class,
    (implements async `__call__` method, expects no parameters).
    """

    async def __call__(self):
        pass


class SyncCallableClassValid:
    """Valid synchronous callable class,
    (implements sync `__call__` method, expects one parameter).
    """

    def __call__(self, arg):
        pass


class SyncCallableClassInvalid:
    """Inalid synchronous callable class,
    (implements sync `__call__` method, expects no parameters).
    """

    def __call__(self):
        pass


class NotCallableClass:
    """Invalid class (does not implement `__call__` method)."""

    pass


@pytest.mark.parametrize(
    'handler, expected',
    [
        (async_handler_valid, True),
        (async_handler_invalid, False),
        (sync_handler_valid, False),
        (sync_handler_invalid, False),
        (AsyncCallableClassValid(), True),
        (AsyncCallableClassInvalid(), False),
        (SyncCallableClassValid(), False),
        (SyncCallableClassInvalid(), False),
        (NotCallableClass(), False),
        ('not a callable', False),
    ],
)
def test_is_valid_async_handler(handler, expected):
    assert HandlerValidator.is_valid_async_handler(handler) is expected


@pytest.mark.parametrize(
    'handler, expected',
    [
        (async_handler_valid, False),
        (async_handler_invalid, False),
        (sync_handler_valid, True),
        (sync_handler_invalid, False),
        (AsyncCallableClassValid(), False),
        (AsyncCallableClassInvalid(), False),
        (SyncCallableClassValid(), True),
        (SyncCallableClassInvalid(), False),
        (NotCallableClass(), False),
        ('not a callable', False),
    ],
)
def test_is_valid_sync_handler(handler, expected):
    assert HandlerValidator.is_valid_sync_handler(handler) is expected


@pytest.mark.parametrize(
    'handler, expected',
    [
        (async_handler_valid, True),
        (async_handler_invalid, False),
        (sync_handler_valid, True),
        (sync_handler_invalid, False),
        (AsyncCallableClassValid(), True),
        (AsyncCallableClassInvalid(), False),
        (SyncCallableClassValid(), True),
        (SyncCallableClassInvalid(), False),
        (NotCallableClass(), False),
        ('not a callable', False),
    ],
)
def test_is_valid_handler(handler, expected):
    assert HandlerValidator.is_valid_handler(handler) is expected
