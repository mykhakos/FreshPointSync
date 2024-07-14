import asyncio
import collections.abc
import enum
import functools
import inspect
import logging
import sys
from typing import (
    Any,
    Callable,
    Coroutine,
    Dict,
    Generic,
    Iterable,
    Iterator,
    List,
    NamedTuple,
    Optional,
    Tuple,
    TypeVar,
    Union,
    cast,
)

if sys.version_info >= (3, 10):
    from typing import TypeAlias
else:
    from typing_extensions import TypeAlias

if sys.version_info >= (3, 11):
    from typing import NamedTuple
else:
    from typing_extensions import NamedTuple


from ..product._product import DiffValueTuple, Product
from ..runner._runner import CallableRunner

logger = logging.getLogger('freshpointsync.update')
"""Logger for the `freshpointsync.update` package."""


T = TypeVar('T')


class ProductUpdateEvent(enum.Enum):
    """An enumeration of different types of product updates.

    This enum is used to represent various kinds of changes or updates that can
    occur to a product on the product page. Each member represents a specific
    type of update event for easy identification and handling.
    """

    PRODUCT_ADDED = 'product_added'
    """Indicates that a new product has been listed on the product page."""
    PRODUCT_UPDATED = 'product_updated'
    """Indicates any update to a product's information and state."""
    QUANTITY_UPDATED = 'quantity_updated'
    """Indicates that the stock quantity of a product has been updated."""
    PRICE_UPDATED = 'price_updated'
    """Indicates that the pricing of a product has changed, including both
    full price and current sale price.
    """
    OTHER_UPDATED = 'other_updated'
    """Indicates an update to the product's metadata,
    for example, a change of the illustration picture URL.
    """
    PRODUCT_REMOVED = 'product_removed'
    """Indicates that a product has been removed from the product page."""


class ProductUpdateContext(collections.abc.Mapping):
    """An update event context data wrapper for product update events with
    a mapping-like access to the data along with direct access to specific
    product state information via the `product_old` and `product_new` keys and
    the event type via the `event` key.

    This class is designed to encapsulate the update event context data
    passed to event handlers during product update events.
    """

    def __init__(self, __kwargs: Dict[Union[str, Any], Any]) -> None:
        super().__init__()
        self.__kwargs = __kwargs

    def __str__(self) -> str:
        """Returns a string representation of the context data."""
        return str(self.__kwargs)

    def __repr__(self) -> str:
        """Returns a string representation of the context data object
        initialization.
        """
        return f'{self.__class__.__name__}({self.__kwargs})'

    def __getitem__(self, key: object) -> object:
        """Returns the value for the given key from the internal context data.

        Args:
            key (Any): The key to look up in the context data.

        Returns:
            Any: The value associated with the specified key.
        """
        return self.__kwargs[key]

    def __iter__(self) -> Iterator[Any]:
        """Returns an iterator over the keys of the internal context data.

        Returns:
            Iterator[Any]: An iterator over the keys of the context data.
        """
        return iter(self.__kwargs)

    def __len__(self) -> int:
        """Returns the number of items in the internal context data.

        Returns:
            int: The number of items in the context data.
        """
        return len(self.__kwargs)

    def __get_product_attr(self, attr: str, default: T) -> T:
        """Retrieve a specific attribute from the product state data.

        Args:
            attr (str): The attribute to retrieve from the product state data.
            default (T): The default value to return if the attribute
                is not found.

        Returns:
            T: The value of the attribute if found, otherwise the default value.
        """
        if attr in self.__kwargs:
            return self.__kwargs[attr]  # type: ignore
        if self.product_new:
            return getattr(self.product_new, attr)  # type: ignore
        if self.product_old:
            return getattr(self.product_old, attr)  # type: ignore
        return default

    @property
    def event(self) -> ProductUpdateEvent:
        """The type of product update event that occurred."""
        return self.__kwargs['event']  # type: ignore

    @property
    def timestamp(self) -> float:
        """The timestamp of the product update event."""
        return self.__get_product_attr('timestamp', 0)

    @property
    def product_id(self) -> int:
        """ID of the product being updated.
        If not available, defaults to 0.
        """
        return self.__get_product_attr('id_', 0)

    @property
    def product_name(self) -> str:
        """Name of the product being updated.
        If not available, defaults to an empty string.
        """
        return self.__get_product_attr('name', '')

    @property
    def product_name_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the product name.
        If not available, defaults to an empty string.
        """
        return self.__get_product_attr('name_lowercase_ascii', '')

    @property
    def location_id(self) -> int:
        """ID of the product location.
        If not available, defaults to 0.
        """
        return self.__get_product_attr('location_id', 0)

    @property
    def location(self) -> str:
        """Name of the product location.
        If not available, defaults to an empty string.
        """
        return self.__get_product_attr('location', '')

    @property
    def location_lowercase_ascii(self) -> str:
        """Lowercase ASCII representation of the location name.
        If not available, defaults to an empty string.
        """
        return self.__get_product_attr('location_lowercase_ascii', '')

    @property
    def product_new(self) -> Optional[Product]:
        """New state of the product after the update.
        If not available, defaults to None.
        """
        return self.__kwargs['product_new']  # type: ignore

    @property
    def product_old(self) -> Optional[Product]:
        """Previous state of the product before the update.
        If not available, defaults to None.
        """
        return self.__kwargs['product_old']  # type: ignore

    def asdict(self) -> Dict[Union[str, object], object]:
        """Convert the context data to a dictionary.

        Returns:
            dict[str, Any]: A dictionary representation of the context data.
        """
        return self.__kwargs.copy()


class HandlerValidator:
    """A utility class for validating handler functions or methods based on
    their signature and whether they are asynchronous or synchronous.
    """

    @classmethod
    def _is_valid_is_async(cls, handler: object) -> Tuple[bool, bool]:
        """Determine if a given handler is valid based on its signature and
        whether it is an asynchronous coroutine or a synchronous function
        or method.

        Args:
            handler: The handler to be validated. This can be any callable
                (a function, a method, or an object with a `__call__` method).

        Returns:
            tuple(bool, bool): A tuple of two boolean values, where
                the first value indicates whether the handler is valid (True)
                or not (False) and the second value indicates whether
                the handler is an asynchronous (True) or synchronous (False).
        """
        while isinstance(handler, functools.partial):
            handler = handler.func
        if not callable(handler):
            return False, False
        try:
            is_valid_sig = len(inspect.signature(handler).parameters) == 1
            is_async = inspect.iscoroutinefunction(handler)
            if not is_async:
                call_method = getattr(handler, '__call__', None)  # noqa: B004
                is_async = inspect.iscoroutinefunction(call_method)
            return is_valid_sig, is_async
        except Exception as e:
            logger.warning('Failed to validate handler "%s": %s', handler, e)
            return False, False

    @classmethod
    def is_valid_async_handler(cls, handler: object) -> bool:
        """Check if a handler is an asynchronous coroutine function with
        a valid signature (accepts exactly one argument).

        Args:
            handler: The handler to be validated.

        Returns:
            bool: True if the handler is valid and asynchronous,
                otherwise, False.
        """
        is_valid, is_async = cls._is_valid_is_async(handler)
        return is_valid and is_async

    @classmethod
    def is_valid_sync_handler(cls, handler: object) -> bool:
        """Check if a handler is a synchronous function or method with a valid
        signature (accepts exactly one argument).

        Args:
            handler: The handler to be validated.

        Returns:
            bool: True if the handler is valid and synchronous,
                otherwise, False.
        """
        is_valid, is_async = cls._is_valid_is_async(handler)
        return is_valid and not is_async

    @classmethod
    def is_valid_handler(cls, handler: object) -> bool:
        """Check if a handler has a valid signature and is a valid function or
        method, regardless of whether it is synchronous or asynchronous.

        Args:
            handler: The handler to be validated.

        Returns:
            bool: True if the handler is valid, otherwise, False.
        """
        is_valid, _ = cls._is_valid_is_async(handler)
        return is_valid


def is_valid_handler(handler: object) -> bool:
    """Validate a handler based on its signature and whether it is an
    asynchronous coroutine or a synchronous function or method.

    Args:
        handler (Any): The handler to be validated.

    Returns:
        bool: True if the handler is valid, otherwise, False.
    """
    return HandlerValidator.is_valid_handler(handler)


SyncHandler: TypeAlias = Callable[[ProductUpdateContext], None]
"""Type alias for a synchronous handler function. Expects a single argument
of type `ProductUpdateContext` and returns `None`.
"""


AsyncHandler: TypeAlias = Callable[
    [ProductUpdateContext], Coroutine[Any, Any, None]
]
"""Type alias for an asynchronous handler function. Expects a single argument
of type `ProductUpdateContext` and returns a coroutine that resolves to `None`.
"""


Handler: TypeAlias = Union[SyncHandler, AsyncHandler]
"""Type alias for a handler function or method. Can be either a synchronous
callable that accepts a single argument of type `ProductUpdateContext` and
returns `None`, or an asynchronous callable that accepts a single argument
of type `ProductUpdateContext` and returns a coroutine that resolves to `None`.
"""


class HandlerExecParamsTuple(NamedTuple):
    """A named tuple for storing handler execution parameters."""

    run_safe: bool
    """A flag indicating whether the handler should be executed in a "safe"
    manner, meaning any exceptions raised by the handler will be caught,
    logged, and suppressed.
    """
    run_blocking: bool
    """A flag indicating whether a synchronous handler should be executed in
    a blocking manner, i.e., called directly without using a separate
    `ThreadPoolExecutor`. This flag is ignored for asynchronous handlers.
    """
    done_callback: Optional[Callable[[asyncio.Future], Any]]
    """An optional callback function to be called when the handler completes
    its execution. Depending of the type of the handler, the callback
    receives an `asyncio.Task` or `asyncio.Future` object as its argument,
    which represents the eventual result of the handler's execution.
    """


HandlerType = TypeVar('HandlerType', SyncHandler, AsyncHandler)
"""A `TypeVar` variable for a handler function or method."""


class HandlerDataTuple(NamedTuple, Generic[HandlerType]):
    """A named tuple for storing handler data."""

    handler: HandlerType
    """The handler function to be executed after a certain event occurs."""
    exec_params: HandlerExecParamsTuple
    """The hanlder function execution parameters."""


SyncHandlerList: TypeAlias = List[HandlerDataTuple[SyncHandler]]
"""A list of `HandlerDataTuple` records of synchronous handlers."""


AsyncHandlerList: TypeAlias = List[HandlerDataTuple[AsyncHandler]]
"""A list of `HandlerDataTuple` records of asynchronous handlers."""


class ProductUpdateEventPublisher:
    """A publisher and a subscription manager for product update events.

    This class maintains a registry of event handlers for different types of
    product update events. It allows for subscribing or unsubscribing handlers
    to specific events and facilitates broadcasting events to all relevant
    handlers.
    """

    def __init__(self) -> None:
        self.context: dict[Any, Any] = {}  # global persistent context
        self.runner = CallableRunner()
        self.sync_subscribers: dict[ProductUpdateEvent, SyncHandlerList] = {}
        self.async_subscribers: dict[ProductUpdateEvent, AsyncHandlerList] = {}

    @staticmethod
    def _is_in_subscribers_list(
        handler: Handler, subscribers: List[HandlerDataTuple]
    ) -> bool:
        """Check if a handler is already present in the list of subscribers.

        This method iterates over the subscribers list to check if the provided
        handler matches any handler in the list based on object identity.

        Args:
            handler: The handler function or method to check.
            subscribers: A list of `HandlerDataTuple` objects representing
                the current subscribers.

        Returns:
            bool: True if the handler is found in the list of subscribers,
                otherwise, False.
        """
        return any(existing.handler == handler for existing in subscribers)

    @staticmethod
    def _remove_from_subscribers_list(
        handler: Handler, subscribers: List[HandlerDataTuple]
    ) -> None:
        """Remove a handler from the list of subscribers.

        This method iterates over the subscribers list to find and remove
        the provided handler based on object identity. If the handler
        is not found in the list, no action is taken.

        Args:
            handler: The handler function or method to remove.
            subscribers: A list of `HandlerDataTuple` objects representing
                the current subscribers.
        """
        for i, existing in enumerate(subscribers):
            if existing.handler == handler:
                del subscribers[i]
                break

    def _subscribe_sync(
        self,
        event: ProductUpdateEvent,
        handler: Handler,
        run_safe: bool,
        run_blocking: bool,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]],
    ) -> None:
        """Subscribe a synchronous handler to a specific product update event.

        This internal method adds a synchronous handler to the event's
        subscribers list, ensuring that the handler and its
        execution parameters are stored correctly.

        Args:
            event: The product update event to subscribe the handler to.
            handler: The synchronous handler to be subscribed.
            run_safe: Indicates whether the handler should be called in
                a "safe" manner, with exceptions caught and handled.
            run_blocking: Indicates whether the handler should be called in
                a blocking manner, i.e., called directly without using an
                executor. If False, the handler is executed in a non-blocking
                manner in a separate thread.
            handler_done_callback: An optional callback function to be called
                when the handler completes its execution.
        """
        subscribers = self.sync_subscribers.setdefault(event, [])
        if not self._is_in_subscribers_list(handler, subscribers):
            handler = cast(SyncHandler, handler)
            params = HandlerExecParamsTuple(
                run_safe, run_blocking, handler_done_callback
            )
            subscribers.append(HandlerDataTuple(handler, params))

    def _subscribe_async(
        self,
        event: ProductUpdateEvent,
        handler: Handler,
        run_safe: bool,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]],
    ) -> None:
        """Subscribe an asynchronous handler to a specific product update
        event.

        This internal method adds an asynchronous handler to the event's
        subscribers list, ensuring that the handler and its
        execution parameters are stored correctly.

        Args:
            event: The product update event to subscribe the handler to.
            handler: The asynchronous handler to be subscribed.
            run_safe: Indicates whether the handler should be called in
                a "safe" manner, with exceptions caught and handled.
            handler_done_callback: An optional callback function to be called
                when the handler completes its execution.
        """
        subscribers = self.async_subscribers.setdefault(event, [])
        if not self._is_in_subscribers_list(handler, subscribers):
            handler = cast(AsyncHandler, handler)
            params = HandlerExecParamsTuple(
                run_safe, False, handler_done_callback
            )
            subscribers.append(HandlerDataTuple(handler, params))

    @staticmethod
    def _validate_event(
        event: Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None],
    ) -> List[ProductUpdateEvent]:
        """Validate the provided event(s) and return a list of event objects.

        Args:
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The event or events to validate.

        Raises:
            TypeError: If the event is not a valid type.

        Returns:
            list[ProductUpdateEvent]: A list of validated event objects.
        """
        if event is None:
            return list(ProductUpdateEvent)
        if isinstance(event, ProductUpdateEvent):
            return [event]
        if isinstance(event, Iterable) and not isinstance(event, str):  # type: ignore
            return [ProductUpdateEvent(e) for e in event]
        raise TypeError(
            f'Event must be a ProductUpdateEvent or an iterable of '
            f'ProductUpdateEvent, got {type(event).__name__} instead.'
        )

    def subscribe(
        self,
        handler: Handler,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
        run_safe: bool = True,
        run_blocking: bool = True,
        handler_done_callback: Optional[Callable[[asyncio.Future], Any]] = None,
    ) -> None:
        """Subscribe a handler to specific product update event(s). The handler
        will be invoked when the event is posted, with the event context
        passed as an argument.

        The handler can be an asynchronous function, method, or any callable
        object that accepts exactly one argument (a `ProductUpdateContext`
        object) and returns `None` or a coroutine that resolves to `None`.

        Args:
            handler (Handler): The function or callable to invoke for
                the event(s).
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to subscribe to. If None,
                the handler will be subscribed to all events.
            run_safe (bool, optional): If True, exceptions raised by
                the handler are caught and logged. If False, exceptions are
                propagated and must be handled by the caller. Defaults to True.
            run_blocking (bool, optional): If True, synchronous handlers are
                executed in a blocking manner, i.e., called directly without
                using an executor. If False, synchronous handlers are executed
                in a non-blocking manner in a separate thread. Defaults to True.
            handler_done_callback (Optional[Callable[[asyncio.Future], Any]]):
                Optional function to be called when the handler completes
                execution. Depending on the type of the handler, the callback
                receives an `asyncio.Task` or `asyncio.Future` object as its
                argument, which represents the return value of the callback
                execution. Defaults to None.

        Raises:
            TypeError: If the handler does not have a valid signature.
        """
        events = self._validate_event(event)
        is_valid, is_async = HandlerValidator._is_valid_is_async(handler)
        if not is_valid:
            raise TypeError('Handler signature is invalid.')
        callback = handler_done_callback
        if is_async:
            for event_ in events:
                self._subscribe_async(event_, handler, run_safe, callback)
        else:
            for event_ in events:
                self._subscribe_sync(
                    event_, handler, run_safe, run_blocking, callback
                )

    def unsubscribe(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
    ) -> None:
        """Unsubscribe a handler from specific product update event(s),
        or all handlers if no specific handler is provided. The unsubscribed
        handler will no longer be invoked when the event is posted.

        Args:
            handler (Handler): The handler to be unsubscribed from the
                event(s). if None, all handlers for the event are unsubscribed.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to unsubscribe from.
                If None, the handler(s) will be subscribed from all events.
        """
        events = self._validate_event(event)
        for e in events:
            async_subs = self.async_subscribers.pop(e, None)
            sync_subs = self.sync_subscribers.pop(e, None)
            if handler is None:
                continue
            if async_subs:
                if self._is_in_subscribers_list(handler, async_subs):
                    self._remove_from_subscribers_list(handler, async_subs)
            if sync_subs:
                if self._is_in_subscribers_list(handler, sync_subs):
                    self._remove_from_subscribers_list(handler, sync_subs)

    def is_subscribed(
        self,
        handler: Optional[Handler] = None,
        event: Union[
            ProductUpdateEvent, Iterable[ProductUpdateEvent], None
        ] = None,
    ) -> bool:
        """Check if there are any subscribers for the given event(s).

        Args:
            handler (Optional[Handler], optional): The handler to check for
                subscription. If None, all handlers are checked.
            event (Union[ProductUpdateEvent, Iterable[ProductUpdateEvent], None], optional):
                The type of product update event(s) to check for subscribers.
                If None, all events are checked.

        Returns:
            bool: True if there are subscribers for the event, False otherwise.
        """
        events = self._validate_event(event)
        for e in events:
            if e in self.async_subscribers or e in self.sync_subscribers:
                if handler is None:
                    return True
                async_subs = self.async_subscribers.get(e, [])
                sync_subs = self.sync_subscribers.get(e, [])
                if self._is_in_subscribers_list(handler, async_subs):
                    return True
                if self._is_in_subscribers_list(handler, sync_subs):
                    return True
        return False

    def get_context(
        self,
        event: ProductUpdateEvent,
        product_new: Optional[Product],
        product_old: Optional[Product],
        **kwargs: Any,
    ) -> ProductUpdateContext:
        """Construct a `ProductUpdateContext` instance from the provided
        product and additional parameters, merging the global context data with
        the specific product information and any additional keyword arguments
        (the latter takes precedence).

        Args:
            event (ProductUpdateEvent): The type of product update event
                to be broadcasted.
            product_new (Optional[Product]): The updated product instance,
                or None if not applicable.
            product_old (Optional[Product]): The original product instance
                before the update, or None if not applicable.
            **kwargs (Any): Additional context parameters to be included.

        Returns:
            ProductUpdateContext: A context object populated with the global
                context data and the provided product information and
                parameters.
        """
        context_kwargs = {**self.context, **kwargs}
        context_kwargs['event'] = event
        context_kwargs['product_new'] = product_new
        context_kwargs['product_old'] = product_old
        return ProductUpdateContext(context_kwargs)

    def post(
        self,
        event: ProductUpdateEvent,
        product_new: Optional[Product],
        product_old: Optional[Product],
        **kwargs: Any,
    ) -> None:
        """Notify registered handlers about a specific product update event.

        This method constructs a `ProductUpdateContext` with new and old
        product details, along with any additional keyword arguments. It then
        broadcasts the event to all relevant handlers, asynchronous and
        synchronous alike, registered for the event type.

        Args:
            event (ProductUpdateEvent): The type of product update event
                to be broadcasted.
            product_new (Optional[Product]): The updated product instance,
                or None if there's no new product.
            product_old (Optional[Product]): The original product instance
                before update, or None if unavailable.
            **kwargs (Any): Additional keyword arguments to be included
                in the event context. If any of the keyword arguments
                overlaps with the context data, it takes precedence.
        """
        event = ProductUpdateEvent(event)
        context: Optional[ProductUpdateContext] = None
        if event in self.async_subscribers:
            context = self.get_context(
                event, product_new, product_old, **kwargs
            )
            for async_sub in self.async_subscribers[event]:
                self.runner.run_async(
                    async_sub.handler,
                    context,
                    run_safe=async_sub.exec_params.run_safe,
                    done_callback=async_sub.exec_params.done_callback,
                )
        if event in self.sync_subscribers:
            if context is None:
                context = self.get_context(
                    event, product_new, product_old, **kwargs
                )
            for sync_sub in self.sync_subscribers[event]:
                self.runner.run_sync(
                    sync_sub.handler,
                    context,
                    run_safe=sync_sub.exec_params.run_safe,
                    run_blocking=sync_sub.exec_params.run_blocking,
                    done_callback=sync_sub.exec_params.done_callback,
                )


class ProductCacheUpdater:
    """Product cache manager. Updates the cache and notifies subscribers
    about product updates.

    This class is responsible for maintaining a cache of product data and
    using an event publisher to notify interested parties of changes to
    product information. It provides methods to create, delete, and update
    products in the cache and to trigger appropriate events for each action.
    """

    def __init__(
        self,
        products: Dict[int, Product],
        publisher: ProductUpdateEventPublisher,
    ) -> None:
        """Initialize a `ProductCacheUpdater` instance.

        Args:
            products (dict[int, Product]): A dictionary of products, where
                the keys are product IDs and the values are `Product` objects.
            publisher (ProductUpdateEventPublisher): An instance of
                the `ProductUpdateEventPublisher` class to call subscribed
                handlers when product updates occur.
        """
        self.products = products
        self._publisher = publisher

    @staticmethod
    def get_location_id(products: Iterable[Product]) -> Optional[int]:
        """Get the location ID from the given products.

        Args:
            products (Iterable[Product]): A collection of products.

        Returns:
            Optional[int]: The location ID if it is found in the products,
                otherwise, None.
        """
        for product in products:
            if product.location_id is not None:
                return product.location_id
        return None

    def create_product(self, product: Product, **kwargs: Any) -> None:
        """Add a new product to the cache and post a `PRODUCT_ADDED` event.

        Note that this method assumes that the product is not present in the
        cache already.

        Args:
            product (Product): the product to add to the cache.
            **kwargs (Any): Additional keyword arguments to include
                in the update event context.
        """
        self.products[product.id_] = product
        self._publisher.post(
            event=ProductUpdateEvent.PRODUCT_ADDED,
            product_new=product,
            product_old=None,
            **kwargs,
        )

    def delete_product(self, product: Product, **kwargs: Any) -> None:
        """Remove a product from the cache and posts a `PRODUCT_REMOVED` event.

        Note that this method assumes that the product is present in the cache.

        Args:
            product (Product): the product to remove from the cache.
            **kwargs (Any): Additional keyword arguments to include
                in the update event context.
        """
        del self.products[product.id_]
        self._publisher.post(
            event=ProductUpdateEvent.PRODUCT_REMOVED,
            product_new=None,
            product_old=product,
            **kwargs,
        )

    def update_product(
        self,
        product: Product,
        product_cached: Product,
        diff: Dict[str, DiffValueTuple],
        **kwargs: Any,
    ) -> None:
        """Update a product in the cache and post events reflecting
        the specific changes occured.

        This method determines what aspects of the product have changed
        (e.g., stock level, price, etc.) and posts the appropriate events
        for each type of update.

        Note that this method assumes that the product is different from
        the cached product.

        Args:
            product (Product): The new product state
                after the update.
            product_cached (Product): The original product state
                before the update.
            diff (dict[str, DiffValueTuple]): A dictionary of differences
                between the new and old product states.
            **kwargs (Any): Additional keyword arguments to include
                in the update event context.
        """
        self.products[product.id_] = product
        events: set[ProductUpdateEvent] = {ProductUpdateEvent.PRODUCT_UPDATED}
        if 'quantity' in diff:
            events.add(ProductUpdateEvent.QUANTITY_UPDATED)
            del diff['quantity']
        if 'price_full' in diff:
            events.add(ProductUpdateEvent.PRICE_UPDATED)
            del diff['price_full']
        if 'price_curr' in diff:
            events.add(ProductUpdateEvent.PRICE_UPDATED)
            del diff['price_curr']
        if diff:  # some other changes are present in the diff
            events.add(ProductUpdateEvent.OTHER_UPDATED)
        for event in events:
            self._publisher.post(
                event=event,
                product_new=product,
                product_old=product_cached,
                **kwargs,
            )

    async def update(
        self,
        products: Iterable[Product],
        await_handlers: bool = False,
        **kwargs: Any,
    ) -> None:
        """Process a batch of product updates, adding, deleting, or updating
        products as necessary.

        This method iterates through a given iterable of products, updating
        the cache to reflect new, removed, or changed products. It optionally
        waits for all event handlers to complete if `await_handlers` is True.

        Args:
            products (Iterable[Product]): products to process.
            await_handlers: If True, waits for all triggered event handlers
                to complete.
            **kwargs (Any): Additional keyword arguments to include
                in the update event context.
        """
        products_mapping = {p.id_: p for p in products}
        # log the product cache update with the location ID
        location_id = self.get_location_id(products_mapping.values()) or '?'
        logger.info('Updating product cache for location ID "%s"', location_id)
        # check if any product is not listed anymore
        for id_number, product in self.products.copy().items():
            if id_number not in products_mapping:
                self.delete_product(product, **kwargs)
        # update the products (or create if not previously listed)
        for id_number, product in products_mapping.items():
            product_cached = self.products.get(id_number)
            if product_cached is None:
                self.create_product(product, **kwargs)
            else:
                diff = product_cached.diff(product, exclude={'timestamp'})
                if diff:
                    self.update_product(product, product_cached, diff, **kwargs)
        # optionally await the triggered handlers
        if await_handlers:
            await self._publisher.runner.await_all()

    def update_silently(self, products: Iterable[Product]) -> None:
        """Update the product cache without triggering any events.

        This method clears the cache dictionary and subsequently populates
        it with the given products, effectively replacing the entire cache
        contents while maintaining the dictionary object itself.

        Args:
            products (Iterable[Product]): products to populate the cache with.
        """
        products_mapping = {p.id_: p for p in products}
        # log the product cache update with the location ID
        location_id = self.get_location_id(products_mapping.values()) or '?'
        logger.info(
            'Updating product cache for location ID "%s" silently', location_id
        )
        self.products.clear()
        self.products.update(products_mapping)
