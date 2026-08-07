"""Settings, read from a `.env` file or the environment.

Everything here can also be passed on the command line, and the command line
wins. The file is for the things you set once and would rather not retype --
your domain, your PIN -- so they do not have to be threaded through make on
every run.

Variables are prefixed, so `ASTABUZZ_DOMAIN=astabuzz.example.com` in `.env`.
"""

from typing import Final

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from astabuzz.buttons import DEFAULT_COUNT, MAX_COUNT

PIN_LENGTH: Final[int] = 4
DEFAULT_PORT: Final[int] = 8787
MAX_PORT: Final[int] = 65535


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="ASTABUZZ_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    pin: str = ""
    domain: str = ""
    port: int = Field(default=DEFAULT_PORT, ge=1, le=MAX_PORT)
    buttons: int = Field(default=DEFAULT_COUNT, ge=1, le=MAX_COUNT)

    @field_validator("pin")
    @classmethod
    def _four_digits_or_empty(cls, value: str) -> str:
        """Empty means "generate one"; anything else must be a real PIN.

        Caught here rather than at first login, when the operator has already
        read it out to everyone.
        """
        if value and (len(value) != PIN_LENGTH or not value.isdigit()):
            msg = f"must be exactly {PIN_LENGTH} digits, got {value!r}"
            raise ValueError(msg)
        return value

    @field_validator("domain")
    @classmethod
    def _looks_like_a_hostname(cls, value: str) -> str:
        if value and (" " in value or "/" in value or "." not in value):
            msg = f"must be a bare hostname like astabuzz.example.com, got {value!r}"
            raise ValueError(msg)
        return value
