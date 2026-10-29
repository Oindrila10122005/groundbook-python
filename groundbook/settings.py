"""One settings object, read once at start-up. Nothing is hard-coded.
The buffers live on the event types (loaded from seed/event_types.csv), never in a setting."""
"""Settings for groundbook, all in one place."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./groundbook.db"
    seed_dir: str = "seed"
    host: str = "0.0.0.0"                          #  and reachable from the gate tablet, not only from the PC itself
    port: int = Field(default=8080, ge=1, le=65535)