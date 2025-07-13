import asyncio
import functools

import pytest
from freshpointparser.models.annotations import DiffType

from freshpointsync._callable_runner import run_safe
from freshpointsync.update._update import (
    ItemUpdateContext,
    PageUpdateContext,
    UpdateConsumerRegistry,
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


# region Validation Functions Tests


class TestValidationFunctions:
    """Test helper validation functions for update consumers."""

    def test_is_async_consumer_basic(self):
        assert is_async_consumer(async_handler) is True
        assert is_async_consumer(sync_handler) is False

    def test_is_async_consumer_partial(self):
        part = functools.partial(async_handler)
        assert is_async_consumer(part) is True
        part_sync = functools.partial(sync_handler)
        assert is_async_consumer(part_sync) is False

    def test_is_valid_consumer(self):
        def one_arg(x):
            return x

        def two_args(x, y):
            return None

        assert is_valid_consumer(one_arg) is True
        assert is_valid_consumer(two_args) is False
        assert is_valid_consumer(len) is True

    def test_is_valid_handler_alias(self):
        assert is_valid_handler(sync_handler) is True
        assert is_valid_handler(async_handler) is True

    def test_is_valid_filter_annotations(self):
        def flt(ctx) -> bool:
            return True

        def flt_no_anno(ctx):
            return True

        def flt_wrong(ctx) -> str:
            return ''

        assert is_valid_filter(flt) is True
        assert is_valid_filter(flt_no_anno) is True
        assert is_valid_filter(flt_wrong) is False


# endregion Validation Functions Tests

# region UpdateConsumerRegistry Tests


class TestUpdateConsumerRegistry:
    """Test UpdateConsumerRegistry functionality."""

    def test_get_consumers_meta_none(self):
        assert UpdateConsumerRegistry._get_consumers_meta(None) == {}

    def test_get_consumers_meta_single(self):
        meta = UpdateConsumerRegistry._get_consumers_meta(sync_handler)
        assert list(meta.keys()) == [sync_handler]
        info = meta[sync_handler]
        assert info.is_async is False
        assert info.run_safe is False

    def test_get_consumers_meta_iterable_and_run_safe(self):
        @run_safe
        def safe_fn(ctx):
            return None

        meta = UpdateConsumerRegistry._get_consumers_meta([safe_fn, async_handler])
        assert meta[safe_fn].run_safe is True
        assert meta[async_handler].is_async is True

    @pytest.mark.asyncio
    async def test_subscribe_unsubscribe_basic(self):
        """Test basic subscribe and unsubscribe functionality."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        called = False

        def handler(ctx):
            nonlocal called
            called = True

        registry.subscribe(handler)
        await pub.post(object())
        assert called is True

        called = False
        registry.unsubscribe(handler)
        await pub.post(object())
        assert called is False

    @pytest.mark.asyncio
    async def test_subscribe_with_filter(self):
        """Test subscribe with filter functionality."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        called = False

        def flt(ctx) -> bool:
            return True

        def handler(ctx):
            nonlocal called
            called = True

        registry.subscribe(handler, flt)
        await pub.post(object())
        assert called is True

        called = False
        registry.unsubscribe(handler)
        await pub.post(object())
        assert called is False
        assert flt not in registry._filters

    @pytest.mark.asyncio
    async def test_sync_filter_allows_handler(self):
        """Test that sync filter allows handler execution when returning True."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        handler_called = False

        def sync_filter(ctx) -> bool:
            return True

        def sync_handler_test(ctx) -> None:
            nonlocal handler_called
            handler_called = True

        registry.subscribe(sync_handler_test, sync_filter)
        await pub.post(object())
        assert handler_called is True

    @pytest.mark.asyncio
    async def test_sync_filter_blocks_handler(self):
        """Test that sync filter blocks handler execution when returning False."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        handler_called = False

        def sync_filter(ctx) -> bool:
            return False

        def sync_handler_test(ctx) -> None:
            nonlocal handler_called
            handler_called = True

        registry.subscribe(sync_handler_test, sync_filter)
        await pub.post(object())
        assert handler_called is False

    @pytest.mark.asyncio
    async def test_async_filter_allows_handler(self):
        """Test that async filter allows handler execution when returning True."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        handler_called = False

        async def async_filter(ctx) -> bool:
            await asyncio.sleep(0.01)
            return True

        async def async_handler_test(ctx) -> None:
            nonlocal handler_called
            await asyncio.sleep(0.01)
            handler_called = True

        registry.subscribe(async_handler_test, async_filter, await_for=True)
        await pub.post(object())
        assert handler_called is True

    @pytest.mark.asyncio
    async def test_async_filter_blocks_handler(self):
        """Test that async filter blocks handler execution when returning False."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        async def async_filter(ctx) -> bool:
            await asyncio.sleep(0.01)
            return False

        def async_handler_test(ctx) -> None:
            raise AssertionError('Handler should not be called')

        registry.subscribe(async_handler_test, async_filter)
        await pub.post(object())  # Should not raise assertion

    @pytest.mark.asyncio
    async def test_sync_handler_with_async_filter(self):
        """Test sync handler with async filter."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        handler_called = False

        async def async_filter(ctx) -> bool:
            await asyncio.sleep(0.01)
            return True

        def sync_handler_test(ctx) -> None:
            nonlocal handler_called
            handler_called = True

        registry.subscribe(sync_handler_test, async_filter)
        await pub.post(object())
        assert handler_called is True

    @pytest.mark.asyncio
    async def test_async_handler_with_sync_filter(self):
        """Test async handler with sync filter."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        handler_called = False

        def sync_filter(ctx) -> bool:
            return True

        async def async_handler_test(ctx) -> None:
            nonlocal handler_called
            await asyncio.sleep(0.01)
            handler_called = True

        registry.subscribe(async_handler_test, sync_filter, await_for=True)
        await pub.post(object())
        assert handler_called is True

    @pytest.mark.asyncio
    async def test_multiple_handlers_different_filters(self):
        """Test multiple handlers with different filter conditions."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        handler1_called = False
        handler2_called = False
        handler3_called = False

        def filter_allow(ctx) -> bool:
            return True

        def filter_block(ctx) -> bool:
            return False

        async def async_filter_allow(ctx) -> bool:
            await asyncio.sleep(0.01)
            return True

        def handler1(ctx) -> None:
            nonlocal handler1_called
            handler1_called = True

        async def handler2(ctx) -> None:
            nonlocal handler2_called
            await asyncio.sleep(0.01)
            handler2_called = True

        def handler3(ctx) -> None:
            nonlocal handler3_called
            handler3_called = True

        # Subscribe handlers with different filters
        registry.subscribe(handler1, filter_allow)
        registry.subscribe(handler2, async_filter_allow, await_for=True)
        registry.subscribe(handler3, filter_block)

        await pub.post(object())

        assert handler1_called is True
        assert handler2_called is True
        assert handler3_called is False

    @pytest.mark.asyncio
    async def test_multiple_filters_single_handler(self):
        """Test single handler with multiple filters."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        handler_called = False

        def filter1(ctx) -> bool:
            return True

        def filter2(ctx) -> bool:
            return True

        def handler(ctx) -> None:
            nonlocal handler_called
            handler_called = True

        registry.subscribe(handler, [filter1, filter2])
        await pub.post(object())
        assert handler_called is True

        # Test with one filter blocking
        handler_called = False

        def filter_blocking(ctx) -> bool:
            return False

        registry.unsubscribe(handler)
        registry.subscribe(handler, [filter1, filter_blocking])
        await pub.post(object())
        assert handler_called is False

    @pytest.mark.asyncio
    async def test_exception_handling(self):
        """Test that handler exceptions don't break other handlers."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        working_handler1_called = False
        working_handler2_called = False

        def failing_handler(ctx) -> None:
            raise RuntimeError('Handler failed')

        def working_handler1(ctx) -> None:
            nonlocal working_handler1_called
            working_handler1_called = True

        def working_handler2(ctx) -> None:
            nonlocal working_handler2_called
            working_handler2_called = True

        registry.subscribe(working_handler1)
        registry.subscribe(failing_handler)
        registry.subscribe(working_handler2)

        await pub.post(object())

        assert working_handler1_called is True
        assert working_handler2_called is True

    @pytest.mark.asyncio
    async def test_run_once_parameter(self):
        """Test run_once parameter functionality."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        runs = 0

        async def handler(ctx):
            nonlocal runs
            await asyncio.sleep(0.01)
            runs += 1

        registry.subscribe(handler, run_once=True, await_for=True)
        await pub.post(object())
        await pub.post(object())
        assert runs == 1

    @pytest.mark.asyncio
    async def test_await_for_parameter(self):
        """Test await_for parameter functionality."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        handler_completed = False

        async def slow_handler(ctx) -> None:
            nonlocal handler_completed
            await asyncio.sleep(0.1)
            handler_completed = True

        registry.subscribe(slow_handler, await_for=True)
        await pub.post(object())
        assert handler_completed is True

    @pytest.mark.asyncio
    async def test_unsubscribed_handler_not_called(self):
        """Test that unsubscribed handlers are not called."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        handler_called = False

        def handler(ctx) -> None:
            nonlocal handler_called
            handler_called = True

        registry.subscribe(handler)
        registry.unsubscribe(handler)
        await pub.post(object())
        assert handler_called is False


# endregion UpdateConsumerRegistry Tests

# region UpdatePublisher Tests


class TestUpdatePublisher:
    """Test UpdatePublisher functionality."""

    @pytest.mark.asyncio
    async def test_basic_posting(self):
        """Test basic event posting functionality."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)
        called = False

        def handler(ctx):
            nonlocal called
            called = True

        registry.subscribe(handler)
        await pub.post(object())
        assert called is True

    @pytest.mark.asyncio
    async def test_async_handler_execution(self):
        """Test async handler execution."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        called = False

        async def async_handler_test(ctx):
            nonlocal called
            await asyncio.sleep(0.01)
            called = True

        registry.subscribe(async_handler_test, await_for=True)
        await pub.post(object())
        assert called is True

    @pytest.mark.asyncio
    async def test_sync_and_async_combinations(self):
        """Test different combinations of sync/async handlers and filters."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        sync_handler_called = False
        async_handler_called = False

        def sync_filter(ctx) -> bool:
            return True

        async def async_filter(ctx) -> bool:
            await asyncio.sleep(0.01)
            return True

        def sync_handler_test(ctx) -> None:
            nonlocal sync_handler_called
            sync_handler_called = True

        async def async_handler_test(ctx) -> None:
            nonlocal async_handler_called
            await asyncio.sleep(0.01)
            async_handler_called = True

        # Test sync handler with async filter
        registry.subscribe(sync_handler_test, async_filter)
        # Test async handler with sync filter
        registry.subscribe(async_handler_test, sync_filter, await_for=True)

        await pub.post(object())

        assert sync_handler_called is True
        assert async_handler_called is True


# endregion UpdatePublisher Tests


# region Context Classes Tests


class TestItemUpdateContext:
    """Test ItemUpdateContext functionality."""

    def test_is_item_created(self):
        """Test is_item_created property."""
        context = ItemUpdateContext(
            item_new=None,
            item_old=None,
            item_diff={'type': DiffType.CREATED, 'diff': {}},
            context={},
        )
        assert context.is_item_created is True
        assert context.is_item_deleted is False
        assert context.is_item_updated is False

    def test_is_item_deleted(self):
        """Test is_item_deleted property."""
        context = ItemUpdateContext(
            item_new=None,
            item_old=None,
            item_diff={'type': DiffType.DELETED, 'diff': {}},
            context={},
        )
        assert context.is_item_created is False
        assert context.is_item_deleted is True
        assert context.is_item_updated is False

    def test_is_item_updated(self):
        """Test is_item_updated property."""
        context = ItemUpdateContext(
            item_new=None,
            item_old=None,
            item_diff={'type': DiffType.UPDATED, 'diff': {}},
            context={},
        )
        assert context.is_item_created is False
        assert context.is_item_deleted is False
        assert context.is_item_updated is True


class TestPageUpdateContext:
    """Test PageUpdateContext functionality."""

    def test_initialization(self):
        """Test PageUpdateContext initialization."""
        page_new = None
        page_old = None
        page_diff = {}
        context_data = {'key': 'value'}

        context = PageUpdateContext(
            page_new=page_new,
            page_old=page_old,
            page_diff=page_diff,
            context=context_data,
        )

        assert context.page_new is page_new
        assert context.page_old is page_old
        assert context.page_diff is page_diff
        assert context.context is context_data


# endregion Context Classes Tests

# region UpdateConsumerRegistry Edge Cases Tests


class TestUpdateConsumerRegistryEdgeCases:
    """Test edge cases for UpdateConsumerRegistry."""

    @pytest.mark.asyncio
    async def test_subscribe_empty_iterable(self):
        """Test subscribing with empty iterable handlers."""
        registry = UpdateConsumerRegistry()
        pub = UpdatePublisher(registry=registry)

        registry.subscribe([])  # Empty list
        await pub.post(object())  # Should not raise any errors

        # Verify no handlers are registered
        assert len(registry._handlers) == 0

    @pytest.mark.asyncio
    async def test_unsubscribe_nonexistent_handler(self):
        """Test unsubscribing handlers that don't exist."""
        registry = UpdateConsumerRegistry()

        def handler(ctx):
            pass

        # Should not raise error when unsubscribing non-existent handler
        registry.unsubscribe(handler)
        registry.unsubscribe([handler])  # As iterable too

    @pytest.mark.asyncio
    async def test_filter_cleanup_after_unsubscribe(self):
        """Test that unused filters are cleaned up after unsubscribing handlers."""
        registry = UpdateConsumerRegistry()

        def filter1(ctx) -> bool:
            return True

        def filter2(ctx) -> bool:
            return True

        def handler1(ctx):
            pass

        def handler2(ctx):
            pass

        # Subscribe handlers with different filters
        registry.subscribe(handler1, filter1)
        registry.subscribe(handler2, filter2)

        assert filter1 in registry._filters
        assert filter2 in registry._filters

        # Unsubscribe one handler
        registry.unsubscribe(handler1)

        # filter1 should be removed, filter2 should remain
        assert filter1 not in registry._filters
        assert filter2 in registry._filters

        # Unsubscribe last handler
        registry.unsubscribe(handler2)

        # All filters should be removed
        assert len(registry._filters) == 0


# endregion UpdateConsumerRegistry Edge Cases Tests
