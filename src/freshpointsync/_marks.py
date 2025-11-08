import logging
from typing import (
    Any,
    Callable,
    Optional,
    TypeVar,
)

logger = logging.getLogger('freshpointsync.runner')
"""Logger for the `freshpointsync.runner` package."""


R = TypeVar('R')


class CallableRunMark:
    def __init__(self, attr: str) -> None:
        self.attr = attr

    def get_mark_value(self, fn: Callable[..., R]) -> Any:
        """Check if a function is decorated with a specific run mark.

        Args:
            fn (Callable[..., R]): The function to check.

        Returns:
            Any: The value of the mark if set, or None if not set.
                This can be True, False, or any other value that indicates
                the mark's state.
        """
        return getattr(fn, self.attr, None)

    def set_mark_value(self, fn: Callable[..., R], value: Any) -> None:
        """Mark a function with a specific run mark by setting the special attribute.

        Args:
            fn (Callable[..., R]): The function to mark.
            value (Any): The value to set for the mark. This can be True,
                False, or any other value that indicates the mark's state.
        """
        setattr(fn, self.attr, value)


run_safe_mark = CallableRunMark('_run_safe')


def run_safe(fn: Callable[..., R]) -> Callable[..., R]:
    """Mark a function to be executed safely, meaning that any exceptions raised
    during its execution will be caught and logged, and the result will
    be set to None in case of an error.

    This decorator overrides the session-wide error handling mode for this
    specific function, forcing safe execution regardless of the AsyncCallableRunner's
    global setting.

    Args:
        fn (Callable[..., R]): The function to be marked as safe.

    Returns:
        Callable[..., R]: The original function marked with a special attribute.
    """
    run_safe_mark.set_mark_value(fn, True)
    return fn


def run_unsafe(fn: Callable[..., R]) -> Callable[..., R]:
    """Mark a function to be executed unsafely, meaning that any exceptions raised
    during its execution will be propagated to the caller.

    This decorator overrides the session-wide error handling mode for this
    specific function, forcing unsafe execution regardless of the AsyncCallableRunner's
    global setting.

    Args:
        fn (Callable[..., R]): The function to be marked as unsafe.

    Returns:
        Callable[..., R]: The original function marked with a special attribute.
    """
    run_safe_mark.set_mark_value(fn, False)
    return fn


def is_run_safe(fn: Callable[..., R]) -> Optional[bool]:
    """Check if a function is decorated with `@run_safe` or `@run_unsafe`.

    Args:
        fn (Callable[..., R]): The function to check.

    Returns:
        Optional[bool]: True if the function is decorated with `@run_safe`,
                       False if decorated with `@run_unsafe`, None if no decorator.
    """
    return run_safe_mark.get_mark_value(fn)
