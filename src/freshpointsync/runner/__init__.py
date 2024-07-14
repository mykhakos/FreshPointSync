"""`freshpointsync.runner` package provides means for running and managing
syncronous and asynchronous tasks in a non-blocking manner. It is a part of the
low-level API.
"""

from ._runner import CallableRunner, logger

__all__ = ['CallableRunner', 'logger']
