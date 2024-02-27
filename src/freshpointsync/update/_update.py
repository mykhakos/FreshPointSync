import asyncio
import collections.abc
import enum
import inspect
import logging
import typing

from concurrent.futures import Executor
from dataclasses import dataclass

from ..product._product import Product


T = typing.TypeVar('T')


class SafeAsyncTaskRunner:
    def __init__(self, executor: typing.Optional[Executor] = None) -> None:
        self.active_tasks: set[asyncio.Task] = set()
        self.executor = executor

    @staticmethod
    def _get_awaitable_name(awaitable: typing.Awaitable) -> str:
        try:
            return getattr(awaitable, '_assigned_name')
        except AttributeError:
            if isinstance(awaitable, asyncio.Task):
                return awaitable.get_name()
            elif inspect.iscoroutine(awaitable):
                return awaitable.cr_code.co_name
            return 'unknown'

    async def _run_safe(
        self, awaitable: typing.Awaitable[T]
    ) -> typing.Optional[T]:
        try:
            return await awaitable
        except asyncio.CancelledError:
            return None
        except Exception as e:
            name = self._get_awaitable_name(awaitable)
            logging.warning('Task "%s" failed (%s)', name, e)
            return None

    def run_async(
        self,
        awaitable: typing.Awaitable[T],
        *,
        done_callback: typing.Optional[
            typing.Callable[[asyncio.Future], typing.Any]
            ] = None
    ) -> asyncio.Task[typing.Optional[T]]:
        task = asyncio.create_task(self._run_safe(awaitable))
        task.add_done_callback(self.active_tasks.discard)
        if done_callback:
            task.add_done_callback(done_callback)
        self.active_tasks.add(task)
        return task

    def run_sync(
        self,
        func: typing.Callable[..., T],
        *func_args,
        done_callback: typing.Optional[
            typing.Callable[[asyncio.Future], typing.Any]
            ] = None,
    ) -> asyncio.Task[typing.Optional[T]]:
        loop = asyncio.get_running_loop()
        future: asyncio.Future[T] = loop.run_in_executor(
            self.executor, func, *func_args
            )
        name = func.__name__
        setattr(future, '_assigned_name', name)
        task = self.run_async(future, done_callback=done_callback)
        task.set_name(name)
        return task

    async def await_all(self) -> None:
        await asyncio.gather(*self.active_tasks)
        self.active_tasks.clear()

    async def cancel_all(self) -> None:
        for task in self.active_tasks:
            task.cancel()
        await asyncio.gather(*self.active_tasks, return_exceptions=True)
        self.active_tasks.clear()


class ProductUpdateEvent(enum.Enum):
    """
    An enumeration of different types of product updates.

    This enum is used to represent various kinds of changes or updates that can
    occur to a product on the product page. Each member represents a specific
    type of update event for easy identification and handling.
    """
    PRODUCT_ADDED = "product_added"
    """Indicates that a new product has been listed on the product page."""
    PRODUCT_UPDATED = "product_updated"
    """Indicates any update to a product's information and state."""
    STOCK_UPDATED = "stock_updated"
    """Indicates that the stock quantity of a product has been updated."""
    PRICE_UPDATED = "price_updated"
    """Indicates that the pricing of a product has changed, including both
    full price and current sale price."""
    PIC_URL_UPDATED = "pic_url_updated"
    """Indicates an update to the product's illustration picture URL."""
    PRODUCT_REMOVED = "product_removed"
    """Indicates that a product has been removed from the product page."""


@dataclass(frozen=True)
class ProductUpdateContext(collections.abc.Mapping):
    """
    A context wrapper for product update events with a mapping-like access to
    event data along with direct access to specific product state information.

    This class is designed to encapsulate the context data passed to event
    handlers during product update events.

    Args:
        _kwargs (dict): The internal dictionary storing event context data.
    """
    _kwargs: dict[typing.Any, typing.Any]

    def __getitem__(self, key: typing.Any) -> typing.Any:
        """
        Returns the value for the given key from the internal context data.

        Args:
            key (Any): The key to look up in the context data.

        Returns:
            Any: The value associated with the specified key.
        """
        return self._kwargs[key]

    def __iter__(self) -> typing.Iterator[typing.Any]:
        """
        Returns an iterator over the keys of the internal context data.

        Returns:
            Iterator[Any]: An iterator over the keys of the context data.
        """
        return iter(self._kwargs)

    def __len__(self) -> int:
        """
        Returns the number of items in the internal context data.

        Returns:
            int: The number of items in the context data.
        """
        return len(self._kwargs)

    @property
    def location_id(self) -> int:
        """ID of the product location."""
        return self._kwargs['location_id']

    @property
    def location_name(self) -> str:
        """Name of the product location."""
        return self._kwargs['location_name']

    @property
    def product_new(self) -> typing.Optional[Product]:
        """New state of the product after the update."""
        return self._kwargs['product_new']

    @property
    def product_old(self) -> typing.Optional[Product]:
        """Previous state of the product before the update."""
        return self._kwargs['product_old']


class HandlerValidator:

    @classmethod
    def _is_valid_handler(cls, handler: typing.Any) -> tuple[bool, bool]:
        """is_valid, is_async"""
        if not callable(handler):
            return False, False
        if inspect.iscoroutinefunction(handler):
            sig = inspect.signature(handler)
            return (len(sig.parameters) == 1), True
        elif inspect.isfunction(handler) or inspect.ismethod(handler):
            sig = inspect.signature(handler)
            return (len(sig.parameters) == 1), False
        elif hasattr(handler, '__call__'):
            return cls._is_valid_handler(handler.__call__)
        return False, False

    @classmethod
    def is_valid_async_handler(cls, handler: typing.Any) -> bool:
        is_valid, is_async = cls._is_valid_handler(handler)
        return is_valid and is_async

    @classmethod
    def is_valid_sync_handler(cls, handler: typing.Any) -> bool:
        is_valid, is_async = cls._is_valid_handler(handler)
        return is_valid and not is_async

    @classmethod
    def is_valid_handler(cls, handler: typing.Any) -> bool:
        is_valid, _ = cls._is_valid_handler(handler)
        return is_valid


def is_valid_handler(handler: typing.Any) -> bool:
    return HandlerValidator.is_valid_handler(handler)


SyncHandler: typing.TypeAlias = typing.Callable[
    [ProductUpdateContext], None
    ]

AsyncHandler: typing.TypeAlias = typing.Callable[
    [ProductUpdateContext], typing.Awaitable[None]
    ]

Handler: typing.TypeAlias = typing.Union[SyncHandler, AsyncHandler]

SyncHandlerList: typing.TypeAlias = list[SyncHandler]

AsyncHandlerList: typing.TypeAlias = list[AsyncHandler]


class ProductUpdateEventPublisher:
    """
    A publisher for product update events, managing subscriptions and
    broadcasting events to registered handlers.

    This class maintains a registry of event handlers for different types of
    product update events. It allows for subscribing or unsubscribing handlers
    to specific events and facilitates broadcasting events to all relevant
    handlers.

    Attributes:
        subscribers (dict):
            A dictionary mapping each `ProductUpdateEvent` to
            a list of subscribed handler awaitable callables.
        context (dict):
            A dictionary representing a shared context that is
            passed to handlers in addition to the event-specific data.
    """
    def __init__(self) -> None:
        self.active_tasks: set[asyncio.Task] = set()
        self.context: dict[typing.Any, typing.Any] = {}
        self.runner = SafeAsyncTaskRunner()
        self.sync_subscribers: dict[ProductUpdateEvent, SyncHandlerList] = {}
        self.async_subscribers: dict[ProductUpdateEvent, AsyncHandlerList] = {}

    def subscribe(
        self,
        event: ProductUpdateEvent,
        handler: Handler
    ) -> None:
        """
        Subscribes a handler to a specific product update event.

        This method adds the given handler to the list of callable objects
        to be invoked when the specified event is posted. The handler can be
        an asynchronous function, method, or any callable object that accepts
        exactly one argument (a `ProductUpdateContext` object) and returns
        an awaitable object.

        Args:
            event (ProductUpdateEvent):
                The type of product update event to subscribe to.
            handler (Callable[[ProductUpdateContext], Awaitable]):
                An async handler, which can be a function, method, or any
                callable object, to be invoked for the event.

        Raises:
            TypeError: If the handler is not a valid awaitable callable.
        """
        event = ProductUpdateEvent(event)
        is_valid, is_async = HandlerValidator._is_valid_handler(handler)
        if not is_valid:
            raise TypeError("Handler signature is invalid.")
        subscribers: list
        if is_async:
            subscribers = self.async_subscribers.setdefault(event, [])
        else:
            subscribers = self.sync_subscribers.setdefault(event, [])
        if handler not in subscribers:
            subscribers.append(handler)

    def unsubscribe(
        self,
        event: ProductUpdateEvent,
        handler: typing.Optional[Handler] = None
    ) -> None:
        """
        Unsubscribes a handler from a specific product update event.

        This method removes the given handler from the list of callable objects
        that are invoked for the specified event type.

        Args:
            event (ProductUpdateEvent):
                The type of product update event to unsubscribe from.
            handler (Callable[[ProductUpdateContext], Awaitable]):
                The async handler, which can be a function, method, or any
                callable object, to be removed.
        """
        event = ProductUpdateEvent(event)
        async_subscribers = self.async_subscribers.get(event, [])
        sync_subscribers = self.async_subscribers.get(event, [])
        if handler is None:
            async_subscribers.clear()
            sync_subscribers.clear()
        elif handler in async_subscribers:
            async_subscribers.remove(handler)  # type: ignore
        elif handler in sync_subscribers:
            async_subscribers.remove(handler)  # type: ignore

    def is_subscribed(self, event: ProductUpdateEvent) -> bool:
        return (
            bool(self.async_subscribers.get(event, [])) or
            bool(self.sync_subscribers.get(event, []))
            )

    def get_context(
        self,
        product_new: typing.Optional[Product],
        product_old: typing.Optional[Product],
        **kwargs: typing.Any
    ) -> ProductUpdateContext:
        context_kwargs = {**self.context, **kwargs}
        context_kwargs['product_new'] = product_new
        context_kwargs['product_old'] = product_old
        if product_new:
            context_kwargs['location_id'] = product_new.location_id
            context_kwargs['location_name'] = product_new.location_name
        elif product_old:
            context_kwargs['location_id'] = product_old.location_id
            context_kwargs['location_name'] = product_old.location_name
        else:
            context_kwargs['location_id'] = 0
            context_kwargs['location_name'] = ''
        return ProductUpdateContext(context_kwargs)

    def post(
        self,
        event: ProductUpdateEvent,
        product_new: typing.Optional[Product],
        product_old: typing.Optional[Product],
        **kwargs: typing.Any
    ) -> None:
        event = ProductUpdateEvent(event)
        context: typing.Optional[ProductUpdateContext] = None
        if event in self.async_subscribers:
            context = self.get_context(product_new, product_old, **kwargs)
            for async_sub in self.async_subscribers[event]:
                self.runner.run_async(async_sub(context))
        if event in self.sync_subscribers:
            if context is None:
                context = self.get_context(product_new, product_old, **kwargs)
            for sync_sub in self.sync_subscribers[event]:
                self.runner.run_sync(sync_sub, context)

    def post_multiple(
        self,
        events: typing.Iterable[ProductUpdateEvent],
        product_new: typing.Optional[Product],
        product_old: typing.Optional[Product],
        **kwargs: typing.Any
    ) -> None:
        old, new = product_old, product_new
        context: typing.Optional[ProductUpdateContext] = None
        events = (ProductUpdateEvent(event) for event in events)
        for event in events:
            if event in self.async_subscribers:
                if context is None:
                    context = self.get_context(old, new, **kwargs)
                for async_sub in self.async_subscribers[event]:
                    self.runner.run_async(async_sub(context))
            if event in self.sync_subscribers:
                if context is None:
                    context = self.get_context(old, new, **kwargs)
                for sync_sub in self.sync_subscribers[event]:
                    self.runner.run_sync(sync_sub, context)


class ProductCacheUpdater:
    def __init__(
        self,
        products: dict[int, Product],
        publisher: ProductUpdateEventPublisher
    ) -> None:
        self.products = products
        self._publisher = publisher

    def create_product(
        self, product: Product, **kwargs: typing.Any
    ) -> None:
        self.products[product.id] = product
        self._publisher.post(
            event=ProductUpdateEvent.PRODUCT_ADDED,
            product_new=product,
            product_old=None,
            **kwargs
            )

    def delete_product(
        self, product: Product, **kwargs: typing.Any
    ) -> None:
        del self.products[product.id]
        self._publisher.post(
            event=ProductUpdateEvent.PRODUCT_REMOVED,
            product_new=None,
            product_old=product,
            **kwargs
            )

    def update_product(
        self, product: Product, product_cached: Product, **kwargs: typing.Any
    ) -> None:
        self.products[product.id] = product
        events: list[ProductUpdateEvent] = [ProductUpdateEvent.PRODUCT_UPDATED]
        if product.count != product_cached.count:
            events.append(ProductUpdateEvent.STOCK_UPDATED)
        if (
            product.price_full != product_cached.price_full or
            product.price_curr != product_cached.price_curr
        ):
            events.append(ProductUpdateEvent.PRICE_UPDATED)
        if product.pic_url != product_cached.pic_url:
            events.append(ProductUpdateEvent.PIC_URL_UPDATED)
        self._publisher.post_multiple(
            events=events,
            product_new=product,
            product_old=product_cached,
            **kwargs
            )

    async def update(
        self,
        products: typing.Iterable[Product],
        await_handlers: bool = False,
        **kwargs: typing.Any
    ) -> None:
        products_mapping = {p.id: p for p in products}
        # check if any product is not listed anymore
        for id_number, product in self.products.items():
            if id_number not in products_mapping:
                self.delete_product(product, **kwargs)
        # update the products (or create if not previously listed)
        for id_number, product in products_mapping.items():
            product_cached = self.products.get(id_number)
            if product_cached is None:
                self.create_product(product, **kwargs)
            elif product_cached != product:
                self.update_product(product, product_cached, **kwargs)
        # optionally await the triggered handlers
        if await_handlers:
            await self._publisher.runner.await_all()

    def update_silently(self, products: typing.Iterable[Product]) -> None:
        self.products.clear()
        self.products.update({p.id: p for p in products})
