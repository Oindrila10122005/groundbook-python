"""Settings for groundbook, all in one place; an env-file can feed it."""

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    database_url: str = "sqlite:///./groundbook.db"
    hold_hours: int = Field(default=24, ge=1)      # after HOLD_HOURS a requested slot no longer holds the ground
    seed_dir: str = "seed"
    host: str = "0.0.0.0"                          #  and reachable from the gate tablet, not only from the PC itself
    port: int = Field(default=8080, ge=1, le=65535)