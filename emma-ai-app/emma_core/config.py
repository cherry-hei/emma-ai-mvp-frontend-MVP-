"""Config loaded from a per-environment .env selected by APP_ENV (.env / .env.test / .env.production). Real OS env vars take precedence. See CLOUD_SETUP.md."""
import os
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

APP_ROOT = Path(__file__).resolve().parent.parent  # emma-ai-app/


def _env_file() -> Path:
    """Pick the .env for APP_ENV. A missing cloud file must NOT fall back to local
    ``.env`` - that would point a prod run at the dev DB; OS env vars must supply
    the config instead."""
    env = os.getenv("APP_ENV", "development").strip().lower()
    if env in ("", "development"):
        return APP_ROOT / ".env"

    candidate = APP_ROOT / f".env.{env}"
    if candidate.exists():
        return candidate
    if os.getenv("SUPABASE_URL"):
        return candidate  # missing file is ignored; OS env vars provide the config
    raise FileNotFoundError(
        f"APP_ENV={env} but neither {candidate.name} nor a SUPABASE_URL environment "
        f"variable is set. Create {candidate.name} from .env.example (see CLOUD_SETUP.md), "
        f"or provide SUPABASE_URL/keys via the environment. Refusing to fall back to the "
        f"local dev database for a '{env}' run."
    )


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

    # CORS allow-list for the frontend origin(s); set CORS_ORIGINS per deployment.
    cors_origins: str = ("http://localhost:3000,http://127.0.0.1:3000,"
                         "http://localhost:3001,http://127.0.0.1:3001")

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
