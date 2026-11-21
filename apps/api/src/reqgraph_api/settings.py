"""Settings of the API from environment variables (07_deploy); secrets are never logged."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", frozen=True)

    database_url: str | None = None  # Supavisor session pooler :5432 in the cloud
    supabase_jwks_url: str | None = None  # <project>/auth/v1/.well-known/jwks.json
    supabase_jwt_aud: str = "authenticated"
    supabase_jwt_secret: str | None = None  # HS256 of a local Supabase CLI; never in production
    cors_origins: str = ""  # comma-separated: the Vercel domain, http://localhost:3000
    db_pool_max: int = 4  # Render Free: a few connections are enough
    worker_enabled: bool = True  # ADR-009: the worker runs in the API process (T-502)
    worker_poll_seconds: float = 2.0  # an empty queue is checked again after this
    job_stale_seconds: int = 120  # a running job without a heartbeat this long was abandoned
    demo_runs_per_day: int = 3  # T-503: runs per user per day (admins and own keys: no limit)
    demo_daily_usd_cap: float = (
        0.20  # all users' paid spend today; above it new runs use free models (author 21.11)
    )
    demo_timezone: str = "Europe/Moscow"  # when a new day starts (author's decision 19.11)
    supabase_url: str | None = None  # T-505: Storage for the exported files (server only)
    supabase_service_role_key: SecretStr | None = None  # never in the site, never logged
    export_offline: bool = False  # exports without Kroki: no scheme pictures (CI, offline stand)
    project_profile: str = "free"  # models of new projects (roles.yaml); the public demo: cheap

    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
