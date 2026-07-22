from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


_PLACEHOLDER_MARKERS = ("change-me", "changeme", "ChangeMe")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="AI Platform API", alias="APP_NAME")
    app_env: str = Field(default="production", alias="APP_ENV")
    app_debug: bool = Field(default=False, alias="APP_DEBUG")
    secret_key: str = Field(default="change-me", alias="SECRET_KEY")
    access_token_expire_minutes: int = Field(default=30, alias="ACCESS_TOKEN_EXPIRE_MINUTES")
    refresh_token_expire_days: int = Field(default=14, alias="REFRESH_TOKEN_EXPIRE_DAYS")
    cors_origins: str = Field(default="http://localhost", alias="CORS_ORIGINS")
    registration_enabled: bool = Field(default=False, alias="REGISTRATION_ENABLED")
    public_url: str = Field(default="http://localhost:8088", alias="PUBLIC_URL")
    cookie_secure: bool | None = Field(default=None, alias="COOKIE_SECURE")

    admin_email: str = Field(default="admin@example.com", alias="ADMIN_EMAIL")
    admin_password: str = Field(default="ChangeMeAdmin123!", alias="ADMIN_PASSWORD")
    admin_name: str = Field(default="Platform Admin", alias="ADMIN_NAME")

    database_url: str = Field(
        default="postgresql+asyncpg://aiplatform:change-me@postgres:5432/aiplatform",
        alias="DATABASE_URL",
    )
    postgres_password: str | None = Field(default=None, alias="POSTGRES_PASSWORD")
    ollama_keep_alive: str = Field(default="-1", alias="OLLAMA_KEEP_ALIVE")
    redis_url: str = Field(default="redis://redis:6379/0", alias="REDIS_URL")
    ollama_base_url: str = Field(default="http://ollama:11434", alias="OLLAMA_BASE_URL")
    qdrant_url: str = Field(default="http://qdrant:6333", alias="QDRANT_URL")
    qdrant_collection: str = Field(default="documents", alias="QDRANT_COLLECTION")

    rate_limit_per_minute: int = Field(default=60, alias="RATE_LIMIT_PER_MINUTE")
    rate_limit_admin_per_minute: int = Field(default=120, alias="RATE_LIMIT_ADMIN_PER_MINUTE")

    embedding_model: str = Field(default="nomic-embed-text", alias="EMBEDDING_MODEL")
    chunk_size: int = Field(default=800, alias="CHUNK_SIZE")
    chunk_overlap: int = Field(default=120, alias="CHUNK_OVERLAP")
    rag_top_k: int = Field(default=5, alias="RAG_TOP_K")

    upload_dir: str = Field(default="/data/uploads", alias="UPLOAD_DIR")
    max_upload_mb: int = Field(default=50, alias="MAX_UPLOAD_MB")

    default_chat_model: str = Field(default="llama3.2:1b", alias="DEFAULT_CHAT_MODEL")

    # --- Agents (Phase 7) ---
    agent_workspace_dir: str = Field(default="/data/agent-workspace", alias="AGENT_WORKSPACE_DIR")
    agent_terminal_allowlist: str = Field(
        default="ls,pwd,cat,head,tail,wc,echo,date,uname,df,du,find,grep,rg,git",
        alias="AGENT_TERMINAL_ALLOWLIST",
    )
    agent_terminal_timeout_sec: int = Field(default=30, alias="AGENT_TERMINAL_TIMEOUT_SEC")
    agent_max_iterations: int = Field(default=8, alias="AGENT_MAX_ITERATIONS")
    agent_db_url: str | None = Field(default=None, alias="AGENT_DB_URL")
    github_token: str | None = Field(default=None, alias="GITHUB_TOKEN")
    docker_host: str | None = Field(default=None, alias="DOCKER_HOST")
    docker_read_only: bool = Field(default=True, alias="DOCKER_READ_ONLY")
    smtp_host: str | None = Field(default=None, alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_password: str | None = Field(default=None, alias="SMTP_PASSWORD")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")
    smtp_use_tls: bool = Field(default=True, alias="SMTP_USE_TLS")
    aws_region: str = Field(default="us-east-1", alias="AWS_REGION")

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def terminal_allowlist(self) -> set[str]:
        return {p.strip() for p in self.agent_terminal_allowlist.split(",") if p.strip()}

    @property
    def is_production(self) -> bool:
        return self.app_env.lower() == "production"

    @property
    def cookies_secure(self) -> bool:
        if self.cookie_secure is not None:
            return self.cookie_secure
        return self.public_url.lower().startswith("https://")

    def validate_production_secrets(self) -> None:
        """Refuse weak placeholder secrets in production."""
        if not self.is_production:
            return
        weak: list[str] = []
        if _is_placeholder(self.secret_key):
            weak.append("SECRET_KEY")
        if _is_placeholder(self.admin_password):
            weak.append("ADMIN_PASSWORD")
        db_secret = self.postgres_password or self.database_url
        if _is_placeholder(db_secret):
            weak.append("POSTGRES_PASSWORD/DATABASE_URL")
        if weak:
            raise RuntimeError(
                "Production refuses placeholder secrets: "
                + ", ".join(weak)
                + ". Run scripts/rotate-secrets.sh (or aws-production-setup.sh) and update .env."
            )


def _is_placeholder(value: str) -> bool:
    lowered = value.lower()
    return any(marker.lower() in lowered for marker in _PLACEHOLDER_MARKERS)


@lru_cache
def get_settings() -> Settings:
    return Settings()
