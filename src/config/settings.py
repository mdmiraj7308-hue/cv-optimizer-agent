import os

from pydantic import Field, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # ── OpenAI ────────────────────────────────────────────────────────────────
    openai_api_key: str = Field(..., description="OpenAI secret key")
    openai_model: str = Field("gpt-4o-mini", description="Model used for both agents")

    # ── Supabase ──────────────────────────────────────────────────────────────
    supabase_url: str = Field(..., description="Supabase project URL")
    supabase_anon_key: str = Field(..., description="Supabase anon/public key")
    supabase_service_role_key: str = Field(
        ..., description="Supabase service-role key (used by backend only)"
    )

    # ── Apify ─────────────────────────────────────────────────────────────────
    apify_api_token: str = Field(..., description="Apify API token")
    apify_actor_id: str = Field(
        "curious_coder/linkedin-jobs-scraper",
        description="Apify actor ID for LinkedIn Jobs scraper",
    )

    # ── Public URL (single-container / Render deploy) ─────────────────────────
    public_base_url: str | None = Field(
        None,
        description="Single public URL for nginx deploy; overrides the three URL settings below",
    )

    # ── FastAPI / internal ────────────────────────────────────────────────────
    fastapi_base_url: str = Field(
        "http://localhost:8000",
        description="Base URL Streamlit uses to call FastAPI internally",
    )
    streamlit_base_url: str = Field(
        "http://localhost:8501",
        description="Streamlit app URL shown on the email verification welcome page",
    )
    auth_confirm_url: str = Field(
        "http://localhost:8000/auth/confirm",
        description="Supabase email confirmation redirect URL (must match Supabase Auth settings)",
    )

    # ── Scheduler ─────────────────────────────────────────────────────────────
    scheduler_timezone: str = Field(
        "Asia/Dhaka", description="IANA timezone string for APScheduler cron jobs"
    )

    # ── Observability (LangSmith) — optional ──────────────────────────────────
    langchain_tracing_v2: bool = Field(
        False, description="Enable LangSmith tracing for all LLM/agent steps"
    )
    langchain_api_key: str | None = Field(None, description="LangSmith API key")
    langchain_project: str = Field(
        "cv-optimizer-agent", description="LangSmith project name for traces"
    )

    @model_validator(mode="after")
    def apply_single_public_url(self) -> "Settings":
        """Apply PUBLIC_BASE_URL or Render's RENDER_EXTERNAL_URL for one-URL deploys."""
        base = (self.public_base_url or os.getenv("RENDER_EXTERNAL_URL", "")).rstrip("/")
        if not base:
            return self
        # Streamlit and FastAPI share a container — keep API calls on localhost.
        self.fastapi_base_url = "http://127.0.0.1:8000"
        self.streamlit_base_url = base
        self.auth_confirm_url = f"{base}/auth/confirm"
        return self

    @model_validator(mode="after")
    def export_langsmith_env(self) -> "Settings":
        """Bridge LangSmith settings into env vars so LangChain auto-tracing picks them up.

        Lets tracing work whether keys come from Render env vars or a local .env.
        """
        if self.langchain_api_key:
            os.environ.setdefault("LANGCHAIN_API_KEY", self.langchain_api_key)
            os.environ.setdefault(
                "LANGCHAIN_TRACING_V2", "true" if self.langchain_tracing_v2 else "false"
            )
            os.environ.setdefault("LANGCHAIN_PROJECT", self.langchain_project)
        return self


settings = Settings()
