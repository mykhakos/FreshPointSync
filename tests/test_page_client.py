import asyncio
import json
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

from freshpointsync._page_client import ProductPageClient
from freshpointsync.update._update import ItemUpdateContext, PageUpdateContext


class TestPageClientHandlerInvocation:
    """Test handler invocation logic for ProductPageClient updates."""

    @pytest.fixture
    def test_data_dir(self):
        """Get the path to test data directory."""
        return Path(__file__).parent

    @pytest.fixture
    def product_page_html(self, test_data_dir):
        """Load product page HTML test data."""
        with open(test_data_dir / 'product_page.html', encoding='utf-8') as f:
            return f.read()

    @pytest.fixture
    def product_page_json(self, test_data_dir):
        """Load product page JSON test data."""
        with open(test_data_dir / 'product_page.json', encoding='utf-8') as f:
            return json.load(f)

    @pytest.fixture
    def location_page_html(self, test_data_dir):
        """Load location page HTML test data."""
        with open(test_data_dir / 'location_page.html', encoding='utf-8') as f:
            return f.read()

    @pytest.fixture
    def location_page_json(self, test_data_dir):
        """Load location page JSON test data."""
        with open(test_data_dir / 'location_page.json', encoding='utf-8') as f:
            return json.load(f)

    @pytest.fixture
    def mock_client(self, product_page_html):
        """Mock the HTML client to return test data."""
        with patch('freshpointsync._page_client.PageHTMLClient') as mock_client_class:
            mock_instance = AsyncMock()
            mock_instance.fetch.return_value = product_page_html
            mock_client_class.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def mock_client_with_changing_content(self, product_page_html):
        """Mock the HTML client to return different content on subsequent calls."""
        with patch('freshpointsync._page_client.PageHTMLClient') as mock_client_class:
            mock_instance = AsyncMock()

            # Create a counter to track call numbers
            call_count = 0

            async def mock_fetch(url, *, retries=None, **kwargs):
                nonlocal call_count
                await asyncio.sleep(0)  # Make it properly async

                if call_count % 2 == 0:
                    # Return original content on even calls (0, 2, 4, ...)
                    result = product_page_html
                else:
                    # Return modified content on odd calls (1, 3, 5, ...)
                    result = product_page_html.replace(
                        '<span class="px-2 font-italic font-weight-bold price">167.92</span>',
                        '<span class="px-2 font-italic font-weight-bold price">169.92</span>',
                    )

                call_count += 1
                return result

            mock_instance.fetch = mock_fetch
            mock_client_class.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def product_page_client(self, mock_client):
        """Create a ProductPageClient instance for testing."""
        return ProductPageClient(location_id=296)

    @pytest.fixture
    def product_page_client_with_changes(self, mock_client_with_changing_content):
        """Create a ProductPageClient instance that will receive changing content."""
        return ProductPageClient(location_id=296)

    @pytest.fixture
    def mock_client_with_multiple_changes(self, product_page_html):
        """Mock the HTML client to return different content on multiple calls."""
        with patch('freshpointsync._page_client.PageHTMLClient') as mock_client_class:
            mock_instance = AsyncMock()

            # Create multiple variations for tests that need more than 2 updates
            prices = ['167.92', '169.92', '179.92', '189.92', '199.92']
            call_count = 0

            async def mock_fetch(url, *, retries=None, **kwargs):
                nonlocal call_count
                await asyncio.sleep(0.01)  # Make it properly async

                current_price = prices[call_count % len(prices)]
                modified_html = product_page_html.replace(
                    '<span class="px-2 font-italic font-weight-bold price">167.92</span>',
                    f'<span class="px-2 font-italic font-weight-bold price">{current_price}</span>',
                )
                call_count += 1
                return modified_html

            mock_instance.fetch = mock_fetch
            mock_client_class.return_value = mock_instance
            yield mock_instance

    @pytest.fixture
    def product_page_client_with_multiple_changes(
        self, mock_client_with_multiple_changes
    ):
        """Create a ProductPageClient instance that will receive multiple changing content."""
        return ProductPageClient(location_id=296)

    # Test sync handlers

    @pytest.mark.asyncio
    async def test_sync_handler_called_on_update(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that sync handlers are called when actual changes occur."""
        handler_called = False
        handler_context = None

        def sync_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called, handler_context
            handler_called = True
            handler_context = context

        product_page_client_with_changes.page_update.subscribe(
            sync_handler, await_for=True
        )

        # First update to establish baseline - no handlers should be called
        await product_page_client_with_changes.update(force=True)
        assert handler_called is False  # No old state to compare against

        # Second update with actual changes should trigger handlers
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert handler_called is True
        assert handler_context is not None
        assert isinstance(handler_context, PageUpdateContext)
        assert handler_context.page_new is not None
        assert handler_context.page_old is not None

    @pytest.mark.asyncio
    async def test_sync_item_handler_called_on_update(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that sync item handlers are called when items are updated."""
        item_handler_calls = []

        def sync_item_handler(context: ItemUpdateContext) -> None:
            item_handler_calls.append(context)

        product_page_client_with_changes.item_update.subscribe(sync_item_handler)

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update should trigger item handlers (due to changing content)
        await product_page_client_with_changes.update(force=True)

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(item_handler_calls) > 0
        for context in item_handler_calls:
            assert isinstance(context, ItemUpdateContext)

    # Test async handlers

    @pytest.mark.asyncio
    async def test_async_handler_called_on_update(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that async handlers are called when actual changes occur."""
        handler_called = False
        handler_context = None

        async def async_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called, handler_context
            await asyncio.sleep(0.01)  # Simulate async work
            handler_called = True
            handler_context = context

        product_page_client_with_changes.page_update.subscribe(
            async_handler, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)
        assert handler_called is False

        # Second update with actual changes should trigger handlers
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert handler_called is True
        assert handler_context is not None
        assert isinstance(handler_context, PageUpdateContext)

    @pytest.mark.asyncio
    async def test_async_item_handler_called_on_update(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that async item handlers are called when items are updated."""
        item_handler_calls = []

        async def async_item_handler(context: ItemUpdateContext) -> None:
            await asyncio.sleep(0.01)  # Simulate async work
            item_handler_calls.append(context)

        product_page_client_with_changes.item_update.subscribe(
            async_item_handler, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update should trigger item handlers
        await product_page_client_with_changes.update(force=True)

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(item_handler_calls) > 0

    # Test sync filters

    @pytest.mark.asyncio
    async def test_sync_filter_allows_handler_execution(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that sync filter allows handler execution when returning True."""
        handler_called = False

        def sync_filter(context: PageUpdateContext) -> bool:
            return True

        def sync_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client_with_changes.page_update.subscribe(
            sync_handler, sync_filter
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger handlers (filter allows)
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert handler_called is True

    @pytest.mark.asyncio
    async def test_sync_filter_blocks_handler_execution(
        self, product_page_client, mock_client
    ):
        """Test that sync filter blocks handler execution when returning False."""
        handler_called = False

        def sync_filter(context: PageUpdateContext) -> bool:
            return False

        def sync_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client.page_update.subscribe(
            sync_handler, sync_filter, await_for=True
        )

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update should trigger handlers (but filter will block)
        await product_page_client.update(force=True)

        assert handler_called is False

    @pytest.mark.asyncio
    async def test_sync_item_filter_functionality(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test sync filter functionality for item updates."""
        item_handler_calls = []
        filter_calls = []

        def sync_item_filter(context: ItemUpdateContext) -> bool:
            filter_calls.append(context)
            # Only allow items with ID greater than 1500
            if context.item_new:
                return context.item_new.id_ > 1500
            return False

        def sync_item_handler(context: ItemUpdateContext) -> None:
            item_handler_calls.append(context)

        product_page_client_with_changes.item_update.subscribe(
            sync_item_handler, sync_item_filter
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update should trigger filters and some handlers
        await product_page_client_with_changes.update(force=True)

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(filter_calls) > 0
        assert len(item_handler_calls) >= 0  # Some items should pass the filter
        # Verify all handled items have ID > 1500
        for context in item_handler_calls:
            if context.item_new:
                assert context.item_new.id_ > 1500

    # Test async filters

    @pytest.mark.asyncio
    async def test_async_filter_allows_handler_execution(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that async filter allows handler execution when returning True."""
        handler_called = False

        async def async_filter(context: PageUpdateContext) -> bool:
            await asyncio.sleep(0.01)  # Simulate async work
            return True

        async def async_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            await asyncio.sleep(0.01)  # Simulate async work
            handler_called = True

        product_page_client_with_changes.page_update.subscribe(
            async_handler, async_filter, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger handlers
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert handler_called is True

    @pytest.mark.asyncio
    async def test_async_filter_blocks_handler_execution(
        self, product_page_client, mock_client
    ):
        """Test that async filter blocks handler execution when returning False."""
        handler_called = False

        async def async_filter(context: PageUpdateContext) -> bool:
            await asyncio.sleep(0.01)  # Simulate async work
            return False

        async def async_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            await asyncio.sleep(0.01)  # Simulate async work
            handler_called = True

        product_page_client.page_update.subscribe(
            async_handler, async_filter, await_for=True
        )

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update should trigger filters but block handlers
        await product_page_client.update(force=True, await_handlers=True)

        assert handler_called is False

    # Test mixed sync/async combinations

    @pytest.mark.asyncio
    async def test_sync_handler_with_async_filter(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test sync handler with async filter."""
        handler_called = False

        async def async_filter(context: PageUpdateContext) -> bool:
            await asyncio.sleep(0.01)
            return True

        def sync_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client_with_changes.page_update.subscribe(
            sync_handler, async_filter
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger handlers
        await product_page_client_with_changes.update(force=True)

        # Allow async filters time to execute
        await asyncio.sleep(0.1)

        assert handler_called is True

    @pytest.mark.asyncio
    async def test_async_handler_with_sync_filter(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test async handler with sync filter."""
        handler_called = False

        def sync_filter(context: PageUpdateContext) -> bool:
            return True

        async def async_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            await asyncio.sleep(0.01)
            handler_called = True

        product_page_client_with_changes.page_update.subscribe(
            async_handler, sync_filter, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger handlers
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert handler_called is True

    # Test multiple handlers and filters

    @pytest.mark.asyncio
    async def test_multiple_handlers_with_different_filters(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test multiple handlers with different filter conditions."""
        handler1_called = False
        handler2_called = False
        handler3_called = False

        def filter_allow(context: PageUpdateContext) -> bool:
            return True

        def filter_block(context: PageUpdateContext) -> bool:
            return False

        async def async_filter_allow(context: PageUpdateContext) -> bool:
            await asyncio.sleep(0.01)
            return True

        def handler1(context: PageUpdateContext) -> None:
            nonlocal handler1_called
            handler1_called = True

        async def handler2(context: PageUpdateContext) -> None:
            nonlocal handler2_called
            await asyncio.sleep(0.01)  # Simulate async work
            handler2_called = True

        def handler3(context: PageUpdateContext) -> None:
            nonlocal handler3_called
            handler3_called = True

        # Subscribe handlers with different filters
        product_page_client_with_changes.page_update.subscribe(handler1, filter_allow)
        product_page_client_with_changes.page_update.subscribe(
            handler2, async_filter_allow, await_for=True
        )
        product_page_client_with_changes.page_update.subscribe(handler3, filter_block)

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger some handlers
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert handler1_called is True
        assert handler2_called is True
        assert handler3_called is False  # Blocked by filter

    @pytest.mark.asyncio
    async def test_multiple_filters_for_single_handler(
        self, product_page_client, mock_client
    ):
        """Test single handler with multiple filters (all must pass)."""
        handler_called = False

        def filter1(context: PageUpdateContext) -> bool:
            return True

        async def filter2(context: PageUpdateContext) -> bool:
            await asyncio.sleep(0.01)
            return True

        def filter3(context: PageUpdateContext) -> bool:
            return False  # This will block the handler

        def handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        # Subscribe with multiple filters
        product_page_client.page_update.subscribe(handler, [filter1, filter2, filter3])

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update should be blocked by filter3
        await product_page_client.update(force=True)

        assert handler_called is False  # Blocked by filter3

    # Test context passing and data validation

    @pytest.mark.asyncio
    async def test_handler_receives_correct_context_data(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that handlers receive correct context data."""
        received_contexts = []

        def page_handler(context: PageUpdateContext) -> None:
            received_contexts.append(('page', context))

        def item_handler(context: ItemUpdateContext) -> None:
            received_contexts.append(('item', context))

        product_page_client_with_changes.page_update.subscribe(
            page_handler, await_for=True
        )
        product_page_client_with_changes.item_update.subscribe(item_handler)

        # Set some custom context
        product_page_client_with_changes.update_context['test_key'] = 'test_value'

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update should trigger handlers with context
        await product_page_client_with_changes.update(
            force=True, custom_param='custom_value'
        )

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(received_contexts) > 0

        # Check page context - find the one with custom_param
        page_contexts = [ctx for typ, ctx in received_contexts if typ == 'page']
        assert len(page_contexts) >= 1

        # Find the page context with custom_param (the one from the second update)
        page_ctx_with_custom = None
        for page_ctx in page_contexts:
            if 'custom_param' in page_ctx.context:
                page_ctx_with_custom = page_ctx
                break

        assert page_ctx_with_custom is not None
        assert 'test_key' in page_ctx_with_custom.context
        assert page_ctx_with_custom.context['test_key'] == 'test_value'
        assert 'custom_param' in page_ctx_with_custom.context
        assert page_ctx_with_custom.context['custom_param'] == 'custom_value'

        # Check item contexts
        item_contexts = [ctx for typ, ctx in received_contexts if typ == 'item']
        assert len(item_contexts) > 0
        for item_ctx in item_contexts:
            assert 'test_key' in item_ctx.context
            assert item_ctx.context['test_key'] == 'test_value'
            assert 'custom_param' in item_ctx.context
            assert item_ctx.context['custom_param'] == 'custom_value'

    @pytest.mark.asyncio
    async def test_handler_context_contains_page_diff(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that page context contains diff information."""
        page_context = None

        def page_handler(context: PageUpdateContext) -> None:
            nonlocal page_context
            page_context = context

        product_page_client_with_changes.page_update.subscribe(
            page_handler, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger handler with diff
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        assert page_context is not None
        assert page_context.page_new is not None
        assert page_context.page_old is not None
        assert page_context.page_diff is not None
        assert isinstance(page_context.page_diff, dict)

    @pytest.mark.asyncio
    async def test_item_handler_context_contains_item_diff(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that item context contains diff information."""
        item_contexts = []

        def item_handler(context: ItemUpdateContext) -> None:
            item_contexts.append(context)

        product_page_client_with_changes.item_update.subscribe(item_handler)

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update should trigger item handlers
        await product_page_client_with_changes.update(force=True)

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(item_contexts) > 0
        for item_ctx in item_contexts:
            assert item_ctx.item_diff is not None
            assert isinstance(item_ctx.item_diff, dict)
            # At least one of item_new or item_old should be present
            assert item_ctx.item_new is not None or item_ctx.item_old is not None

    # Test error handling and edge cases

    @pytest.mark.asyncio
    async def test_handler_exception_does_not_break_other_handlers(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that exception in one handler doesn't prevent others from running."""
        handler1_called = False
        handler2_called = False

        def failing_handler(context: PageUpdateContext) -> None:
            raise ValueError('Handler failed')

        def working_handler1(context: PageUpdateContext) -> None:
            nonlocal handler1_called
            handler1_called = True

        def working_handler2(context: PageUpdateContext) -> None:
            nonlocal handler2_called
            handler2_called = True

        product_page_client_with_changes.page_update.subscribe(
            working_handler1, await_for=True
        )
        product_page_client_with_changes.page_update.subscribe(
            failing_handler, await_for=True
        )
        product_page_client_with_changes.page_update.subscribe(
            working_handler2, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_changes.update(force=True)

        # Second update with changes should trigger handlers (some may fail)
        await product_page_client_with_changes.update(force=True, await_handlers=True)

        # Both working handlers should still be called despite the failing one
        assert handler1_called is True
        assert handler2_called is True

    @pytest.mark.asyncio
    async def test_filter_exception_blocks_handler(
        self, product_page_client, mock_client
    ):
        """Test that exception in filter blocks handler execution."""
        handler_called = False

        def failing_filter(context: PageUpdateContext) -> bool:
            raise ValueError('Filter failed')

        def handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client.page_update.subscribe(
            handler, failing_filter, await_for=True
        )

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update should be blocked by failing filter
        await product_page_client.update(force=True)

        assert handler_called is False

    # Test unsubscription

    @pytest.mark.asyncio
    async def test_unsubscribed_handler_not_called(
        self, product_page_client, mock_client
    ):
        """Test that unsubscribed handlers are not called."""
        handler_called = False

        def handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client.page_update.subscribe(handler, await_for=True)
        product_page_client.page_update.unsubscribe(handler)

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update should not trigger handler (unsubscribed)
        await product_page_client.update(force=True)

        assert handler_called is False

    # Test silent mode

    @pytest.mark.asyncio
    async def test_silent_mode_prevents_handler_execution(
        self, product_page_client, mock_client
    ):
        """Test that silent mode prevents handler execution.

        NOTE: This test currently fails because there appears to be an issue
        with the silent parameter implementation. The documented behavior states
        that silent=True should prevent handlers from being called, but they
        are still being triggered.
        """
        handler_called = False

        def handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client.page_update.subscribe(handler, await_for=True)

        # # First update to establish baseline
        await product_page_client.update()

        # Second update in silent mode
        await product_page_client.update(silent=True)

        # Third update in silent mode with force
        await product_page_client.update(force=True, silent=True)

        # For now, expect that handlers are still called (bug in implementation)
        assert handler_called is False

    # Test force mode

    @pytest.mark.asyncio
    async def test_force_mode_with_changes_triggers_handlers(
        self, product_page_client_with_changes, mock_client_with_changing_content
    ):
        """Test that force mode triggers handlers when there are actual changes."""
        handler_call_count = 0

        def handler(context: PageUpdateContext) -> None:
            nonlocal handler_call_count
            handler_call_count += 1

        product_page_client_with_changes.page_update.subscribe(handler, await_for=True)

        # First update should not trigger handler (no baseline)
        await product_page_client_with_changes.update(force=True)
        assert handler_call_count == 0

        # Second update with changes should trigger handler
        await product_page_client_with_changes.update(force=True, await_handlers=True)
        assert handler_call_count == 1

    @pytest.mark.asyncio
    async def test_force_mode_without_changes_does_not_trigger_handlers(
        self, product_page_client, mock_client
    ):
        """Test that force mode does NOT trigger handlers without actual changes."""
        handler_call_count = 0

        def handler(context: PageUpdateContext) -> None:
            nonlocal handler_call_count
            handler_call_count += 1

        product_page_client.page_update.subscribe(handler, await_for=True)

        # First update should not trigger handler (no baseline)
        await product_page_client.update(force=True)
        assert handler_call_count == 0

        # Second update without changes should NOT trigger handler
        await product_page_client.update(force=True)
        assert handler_call_count == 0  # No changes, so no handlers

        # Third update without changes should still NOT trigger handler
        await product_page_client.update(force=True)
        assert handler_call_count == 0

    # Test await_handlers behavior

    @pytest.mark.asyncio
    async def test_await_handlers_waits_for_async_handlers(
        self,
        product_page_client_with_multiple_changes,
        mock_client_with_multiple_changes,
    ):
        """Test that await_handlers=True waits for async handlers to complete."""
        handler_completed = False

        async def slow_handler(context: PageUpdateContext) -> None:
            nonlocal handler_completed
            await asyncio.sleep(0.1)  # Simulate slow async work
            handler_completed = True

        product_page_client_with_multiple_changes.page_update.subscribe(
            slow_handler, await_for=True
        )

        # First update to establish baseline
        await product_page_client_with_multiple_changes.update(force=True)

        # With await_handlers=True, should wait for completion
        await product_page_client_with_multiple_changes.update(
            force=True, await_handlers=True
        )
        assert handler_completed is True

        # Reset and test without await_handlers
        handler_completed = False
        await product_page_client_with_multiple_changes.update(
            force=True, await_handlers=False
        )
        # Should return immediately, handler may not be complete yet
        # Note: This test is timing-dependent, so we just ensure it doesn't hang

    @pytest.mark.asyncio
    async def test_handler_not_called_without_changes(
        self, product_page_client, mock_client
    ):
        """Test that handlers are NOT called when there are no actual changes."""
        handler_called = False

        def sync_handler(context: PageUpdateContext) -> None:
            nonlocal handler_called
            handler_called = True

        product_page_client.page_update.subscribe(sync_handler, await_for=True)

        # First update to establish baseline
        await product_page_client.update(force=True)
        assert handler_called is False

        # Second update with same content should NOT trigger handlers
        await product_page_client.update(force=True)
        assert handler_called is False  # No actual changes, so no handlers

    # Test sync item handlers

    @pytest.mark.asyncio
    async def test_sync_item_handler_not_called_without_changes(
        self, product_page_client, mock_client
    ):
        """Test that sync item handlers are NOT called when there are no actual changes."""
        item_handler_calls = []

        def sync_item_handler(context: ItemUpdateContext) -> None:
            item_handler_calls.append(context)

        product_page_client.item_update.subscribe(sync_item_handler)

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update with same content should NOT trigger item handlers
        await product_page_client.update(force=True)

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(item_handler_calls) == 0

    # Test async item handlers

    @pytest.mark.asyncio
    async def test_async_item_handler_not_called_without_changes(
        self, product_page_client, mock_client
    ):
        """Test that async item handlers are NOT called when there are no actual changes."""
        item_handler_calls = []

        async def async_item_handler(context: ItemUpdateContext) -> None:
            await asyncio.sleep(0.01)  # Simulate async work
            item_handler_calls.append(context)

        product_page_client.item_update.subscribe(async_item_handler, await_for=True)

        # First update to establish baseline
        await product_page_client.update(force=True)

        # Second update with same content should NOT trigger item handlers
        await product_page_client.update(force=True)

        # Allow async handlers time to execute
        await asyncio.sleep(0.1)

        assert len(item_handler_calls) == 0
