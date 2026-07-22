"""Central configuration, loaded from a per-environment .env file.

The active environment is chosen by the APP_ENV variable:

    APP_ENV unset / development  ->  .env             (local `supabase start`)
    APP_ENV=test                 ->  .env.test        (cloud "emma-test" project)
    APP_ENV=production           ->  .env.production  (cloud "emma-prod" project)

Each file holds the same keys pointing at a different Supabase project. Real OS
environment variables still take precedence over the file (handy for CI /
container deploys). Switching environments is a config change only — no code
changes. See CLOUD_SETUP.md.
"""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parent.parent  # emma-ai-app/


def _env_file() -> Path:
    """Pick the .env file for the active APP_ENV, falling back to .env."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    candidate = APP_ROOT / f".env.{env}"
    return candidate if candidate.exists() else APP_ROOT / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=_env_file(),
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
