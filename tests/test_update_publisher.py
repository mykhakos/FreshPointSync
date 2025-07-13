import asyncio
import functools

import pytest

from freshpointsync._callable_runner import run_safe
from freshpointsync._update_publisher import (
    UpdatePublisher,
    is_async_consumer,
    is_valid_consumer,
    is_valid_filter,
    is_valid_handler,
)


def sync_handler(ctx):
    return 'ok'


async def async_handler(ctx):
    await asyncio.sleep(0)
    return 'ok'


# region Helper validation functions


def test_is_async_consumer_basic():
    assert is_async_consumer(async_handler) is True
    assert is_async_consumer(sync_handler) is False


def test_is_async_consumer_partial():
    part = functools.partial(async_handler)
    assert is_async_consumer(part) is True
    part_sync = functools.partial(sync_handler)
    assert is_async_consumer(part_sync) is False


def test_is_valid_consumer():
    def one_arg(x):
        return x

    def two_args(x, y):
        return None

    assert is_valid_consumer(one_arg) is True
    assert is_valid_consumer(two_args) is False
    assert is_valid_consumer(len) is True


def test_is_valid_handler_alias():
    assert is_valid_handler(sync_handler) is True
    assert is_valid_handler(async_handler) is True


def test_is_valid_filter_annotations():
    def flt(ctx) -> bool:
        return True

    def flt_no_anno(ctx):
        return True

    def flt_wrong(ctx) -> str:
        return ''

    assert is_valid_filter(flt) is True
    assert is_valid_filter(flt_no_anno) is True
    assert is_valid_filter(flt_wrong) is False


# endregion Helper validation functions

# region _get_consumers_meta


def test_get_consumers_meta_none():
    assert UpdatePublisher._get_consumers_meta(None) == {}


def test_get_consumers_meta_single():
    meta = UpdatePublisher._get_consumers_meta(sync_handler)
    assert list(meta.keys()) == [sync_handler]
    info = meta[sync_handler]
    assert info.is_async is False
    assert info.run_safe is False


def test_get_consumers_meta_iterable_and_run_safe():
    @run_safe
    def safe_fn(ctx):
        return None

    meta = UpdatePublisher._get_consumers_meta([safe_fn, async_handler])
    assert meta[safe_fn].run_safe is True
    assert meta[async_handler].is_async is True


# endregion _get_consumers_meta

# region Subscribe, unsubscribe and post


@pytest.mark.asyncio
async def test_subscribe_unsubscribe_and_post():
    pub = UpdatePublisher()
    called = False

    def flt(ctx) -> bool:
        return True

    def handler(ctx):
        nonlocal called
        called = True

    pub.subscribe(handler, flt)
    await pub.post(object())
    assert called is True

    called = False
    pub.unsubscribe(handler)
    await pub.post(object())
    assert called is False
    assert flt not in pub._filters


@pytest.mark.asyncio
async def test_post_filter_blocks_handler():
    pub = UpdatePublisher()

    def flt(ctx) -> bool:
        return False

    async def handler(ctx):  # noqa: RUF029
        raise AssertionError('should not be called')

    pub.subscribe(handler, flt)
    await pub.post(object())


@pytest.mark.asyncio
async def test_post_run_once_and_await_for():
    pub = UpdatePublisher()
    runs = 0

    async def handler(ctx):
        nonlocal runs
        await asyncio.sleep(0.01)
        runs += 1

    pub.subscribe(handler, run_once=True, await_for=True)
    await pub.post(object())
    await pub.post(object())
    assert runs == 1


# endregion Subscribe, unsubscribe and post
