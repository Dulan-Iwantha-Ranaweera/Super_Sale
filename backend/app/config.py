from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from backend/.env."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mongo_uri: str = "mongodb://localhost:27017"
    db_name: str = "supersale"
    jwt_secret: str = "change-me-in-production"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:5176,http://127.0.0.1:5176"

    # Identifier of the single store document this deployment manages.
    store_id: str = "STORE_PRIMARY"

    # Where the trained IPF model is written. Empty means the default
    # `backend/models` directory; the test suite points it elsewhere so a
    # test run can never overwrite the deployed model.
    ipf_model_dir: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
