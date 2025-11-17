"""Global configuration for the `freshpointsync` library."""

from typing import TYPE_CHECKING, Any, Final

from pydantic import BaseModel, ConfigDict
from pydantic_settings import BaseSettings, SettingsConfigDict

if TYPE_CHECKING:
    from httpx._types import TimeoutTypes
else:
    try:
        from httpx._types import TimeoutTypes
    except ImportError:
        TimeoutTypes = Any


class Httpx(BaseModel):
    model_config = ConfigDict(validate_assignment=True, arbitrary_types_allowed=True)

    timeout: TimeoutTypes = 60.0
    retries_total: int = 5
    retries_backoff_factor: float = 1
    retries_backoff_jitter: float = 0.5
    retries_max_backoff_wait: float = 90


class FreshPointSyncConfig(BaseSettings):
    model_config = SettingsConfigDict(env_prefix='FRESHPOINTSYNC_', frozen=True)

    httpx: Httpx = Httpx()


config: Final[FreshPointSyncConfig] = FreshPointSyncConfig()
