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

    # Firebase Cloud Messaging (spec SA.4 / SA.4b). Empty until the Firebase
    # project is provisioned; `push.deliver()` reports "not configured" and
    # leaves the notification queued rather than claiming a delivery that never
    # happened.
    #
    # The service account key is the production setting - either the JSON itself
    # (secret manager) or a path to the downloaded file (developer machine).
    # `push` mints a one-hour OAuth2 token from it and re-mints on expiry.
    fcm_service_account_json: str = ""
    # Optional: the key already names its project. Set only to point a deploy at
    # a different project than the key's own.
    fcm_project_id: str = ""
    # Escape hatch for testing against a project whose key is not on the machine
    # (`gcloud auth print-access-token`). Expires in an hour and is not refreshed
    # - do not use it for a deploy.
    fcm_access_token: str = ""

    # Vertex AI. Empty until the Google Cloud project exists, and the gateway
    # falls back to the offline provider rather than pretending it called out.
    vertex_project: str = ""
    vertex_region: str = "asia-southeast1"
    vertex_model: str = ""
    # Short-lived, from `gcloud auth print-access-token`. A service account key
    # replaces this once the project is provisioned.
    vertex_access_token: str = ""

    # CORS allow-list for the frontend origin(s); set CORS_ORIGINS per deployment.
    # The staff PWA is listed exactly, not matched by pattern: manus.space is
    # shared hosting, so anything looser would hand credentialed requests to
    # every other site deployed there.
    cors_origins: str = ("http://localhost:3000,http://127.0.0.1:3000,"
                         "http://localhost:3001,http://127.0.0.1:3001,"
                         "https://emmastaff-7p8bhd5l.manus.space")

    # Amplify hands every branch its own hostname, so match them instead of listing them.
    cors_origin_regex: str = r"https://[a-z0-9-]+(?:\.[a-z0-9-]+)*\.amplifyapp\.com"

    @property
    def allowed_origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def allowed_origin_regex(self) -> str | None:
        """Anchored both ends, or None when the setting is blank."""
        pattern = (self.cors_origin_regex or "").strip()
        return f"^(?:{pattern})$" if pattern else None


settings = Settings()
