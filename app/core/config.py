from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_env: str = "local"
    debug: bool = False
    secret_key: str

    database_url: str
    redis_url: str

    jwt_algorithm: str = "HS256"
    access_token_expire_minutes: int = 15
    refresh_token_expire_days: int = 30
    oauth_state_ttl_seconds: int = 300

    frontend_url: str = "http://localhost:3000"

    google_client_id: str = ""
    google_client_secret: str = ""
    google_redirect_uri: str = "http://localhost:8000/auth/google/callback"

    resend_api_key: str = ""
    email_from: str = "Multi-Tenant <notifications@notify.processzero.co.uk>"
    invitation_expire_days: int = 7


@lru_cache
def get_settings() -> Settings:
    return Settings()
