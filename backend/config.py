from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ROOT / '.env', extra='ignore')

    secret_key: str = Field(min_length=32)
    database_url: str = f"sqlite:///{ROOT / 'chirp.db'}"
    access_token_expire_minutes: int = Field(default=60, ge=1)
    cors_origins: str = 'http://localhost:5500,http://127.0.0.1:5500'

    @field_validator('secret_key')
    @classmethod
    def reject_placeholder(cls, value: str) -> str:
        if value.startswith('REPLACE_'):
            raise ValueError('Generate a private SECRET_KEY; see README.md')
        return value


settings = Settings()
