"""Settings of the API from environment variables (07_deploy); secrets are never logged."""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", extra="ignore", frozen=True)

    database_url: str | None = None  # Supavisor session pooler :5432 in the cloud
    supabase_jwks_url: str | None = None  # <project>/auth/v1/.well-known/jwks.json
    supabase_jwt_aud: str = "authenticated"
    supabase_jwt_secret: str | None = None  # HS256 of a local Supabase CLI; never in production
    cors_origins: str = ""  # comma-separated: the Vercel domain, http://localhost:3000
    db_pool_max: int = 4  # Render Free: a few connections are enough

    def origins(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]
