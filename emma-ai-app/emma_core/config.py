"""Central configuration loaded from the app-root .env file.

Switching from local Supabase to cloud is just changing the four SUPABASE_*/
DATABASE_URL values here (via .env) — no code changes.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parent.parent  # emma-ai-app/


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=APP_ROOT / ".env",
        extra="ignore",
        case_sensitive=False,
    )

    # Supabase
    supabase_url: str = "http://127.0.0.1:54321"
    supabase_anon_key: str = ""
    supabase_service_role_key: str = ""
    # Direct Postgres (migrations / seed / tests)
    database_url: str = "postgresql://postgres:postgres@127.0.0.1:54322/postgres"

    app_env: str = "development"


settings = Settings()
