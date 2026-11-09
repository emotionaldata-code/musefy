from pydantic import Field, HttpUrl, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: SecretStr = SecretStr("postgresql+asyncpg://musefy:musefy@localhost:5432/musefy")
    tmdb_read_access_token: SecretStr | None = None
    tmdb_rps: float = Field(default=10, gt=0, le=30)
    tvmaze_rps: float = Field(default=1, gt=0, le=2)
    jikan_base_url: HttpUrl = HttpUrl("https://api.jikan.moe/v4")
    jikan_interval: float = Field(default=1.1, ge=1.1)
    concurrency: int = Field(default=2, ge=1, le=10)
    http_timeout: float = Field(default=30, gt=0)
    http_retries: int = Field(default=3, ge=0, le=8)
    cors_origins: list[str] = Field(default_factory=list)

    google_client_id: str | None = None
    google_client_secret: SecretStr | None = None
    google_redirect_uri: str = "http://127.0.0.1:8000/auth/callback"
    auth_frontend_url: str = "http://127.0.0.1:5173"
    auth_jwt_secret: SecretStr | None = None
    auth_cookie_secure: bool = False
    auth_session_ttl_seconds: int = Field(default=604800, ge=60, le=2592000)
