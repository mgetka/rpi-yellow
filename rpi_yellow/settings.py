from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    database_path: str = "yellow.db"
    trigger_time: int = 2
    backoff_time: int = 5

    class Config:
        env_file = ".env"  # optional: load from .env if present


def get_settings():
    return Settings()
