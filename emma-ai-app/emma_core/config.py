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
    """Pick the .env file for the active APP_ENV.

    Local dev uses ``.env``. A cloud env (``test``/``production``) uses its own
    ``.env.<env>`` file. If that file is absent we must NOT silently fall back to
    the local ``.env`` — that would point a "production" run at the dev database.
    A missing cloud file is only acceptable when config is supplied via real OS
    env vars (container / CI, where ``SUPABASE_URL`` is set); otherwise we fail
    loudly with an actionable message.
    """
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

    # CORS — the Next.js frontend is a separate browser origin, so it must be
    # allow-listed or the browser blocks every call. Comma-separated list; set
    # CORS_ORIGINS in the deployed environment to the real frontend URL(s).
    cors_origins: str = ("http://localhost:3000,http://127.0.0.1:3000,"
                         "http://localhost:3001,http://127.0.0.1:3001")

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
