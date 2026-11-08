from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr("postgresql+asyncpg://musefy:musefy@localhost:5432/musefy")
    tmdb_read_access_token: SecretStr | None = None
    tmdb_rps: float = Field(default=10, gt=0)
    jikan_base_url: HttpUrl = HttpUrl("https://api.jikan.moe/v4")
    jikan_interval: float = Field(default=1.1, ge=1.1)
    concurrency: int = Field(default=2, ge=1, le=10)
    http_timeout: float = Field(default=30, gt=0)
    http_retries: int = Field(default=3, ge=0, le=8)
    cors_origins: list[str] = Field(default_factory=list)
