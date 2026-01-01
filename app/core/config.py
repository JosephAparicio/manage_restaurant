from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False
    )

    database_url: str = (
        "postgresql+asyncpg://user:password@localhost:5432/restaurant_ledger"
    )
    database_pool_size: int = 10
    database_max_overflow: int = 20

    api_title: str = "Restaurant Ledger API"
    api_version: str = "1.0.0"
    api_debug: bool = False


settings = Settings()
