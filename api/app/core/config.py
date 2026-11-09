from functools import lru_cache
from pathlib import Path
from urllib.parse import quote

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SECRETS_DIR = Path("/run/secrets")


class Settings(BaseSettings):
    """Configuração lida do ambiente e dos secrets do Swarm (/run/secrets/<nome>).

    Senhas nunca vão em `environment` da stack: chegam como arquivo de secret e as
    URLs de conexão são montadas aqui, para não aparecerem em `docker service inspect`.
    """

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
        secrets_dir=str(SECRETS_DIR) if SECRETS_DIR.is_dir() else None,
    )

    env: str = "dev"
    log_level: str = "INFO"
    # Vazias = integração desligada. Sentry é SaaS; Langfuse é outra stack, fora desta.
    sentry_dsn: str | None = None
    langfuse_public_key: str | None = None
    langfuse_secret_key: str | None = None
    langfuse_host: str | None = None
    langfuse_base_url: str | None = None
    # Vazio = sem telemetria. Aponta para o coletor (gRPC), por exemplo http://otel-collector:4317.
    otel_exporter_otlp_endpoint: str | None = None

    database_host: str = "localhost"
    database_port: int = 5432
    database_name: str = "cobranca"
    # Role da aplicação: sem superuser e sem ser dona das tabelas, para o RLS valer.
    database_user: str = "cobranca_app"
    postgres_app_password: str = "cobranca_app"
    # Role dona do schema, usada só pelo job de migração.
    database_admin_user: str = "cobranca"
    postgres_password: str = "cobranca"

    redis_host: str = "localhost"
    redis_port: int = 6379
    redis_password: str = ""

    s3_endpoint: str = "http://localhost:9000"
    s3_bucket: str = "comprovantes"
    s3_access_key: str = "cobranca"
    minio_root_password: str = "cobranca-dev"

    evolution_base_url: str = "http://localhost:8080"
    evolution_api_key: str = ""

    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str = ""
    smtp_from: str = "cobranca@example.com"

    jwt_secret: str = "dev-secret-change-me"
    jwt_audience: str = "authenticated"
    webhook_hmac: str = "dev-webhook-secret"
    # Vazio em produção impede ativar o tenant. O valor aponta o parecer registrado no SETL-15.
    legal_opinion_ref: str = ""

    llm_model: str = "openai:gpt-4o-mini"
    llm_api_key: str = ""

    cors_origins: list[str] = Field(default_factory=lambda: ["http://localhost:3000"])
    panel_base_url: str = "http://localhost:3000"

    # O gateway encaminha para estes processos. No Swarm são os nomes DNS da rede backend.
    cobranca_url: str = "http://127.0.0.1:8001"
    conciliacao_url: str = "http://127.0.0.1:8002"
    cadastro_url: str = "http://127.0.0.1:8003"

    inbound_debounce_seconds: int = 8
    dunning_interval_minutes: int = 15
    statement_interval_minutes: int = 30
    statement_lookback_days: int = 7
    receipt_min_confidence: float = 0.8
    identity_max_attempts: int = 3

    @field_validator(
        "sentry_dsn",
        "langfuse_public_key",
        "langfuse_secret_key",
        "langfuse_host",
        "langfuse_base_url",
        "otel_exporter_otlp_endpoint",
        mode="before",
    )
    @classmethod
    def _blank_optional(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip():
            return None
        return value

    def _pg_url(self, user: str, password: str, driver: str = "postgresql+psycopg") -> str:
        return (
            f"{driver}://{user}:{quote(password, safe='')}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )

    @property
    def database_url(self) -> str:
        return self._pg_url(self.database_user, self.postgres_app_password)

    @property
    def database_admin_url(self) -> str:
        return self._pg_url(self.database_admin_user, self.postgres_password)

    @property
    def checkpointer_dsn(self) -> str:
        return self._pg_url(self.database_user, self.postgres_app_password, driver="postgresql")

    @property
    def checkpointer_admin_dsn(self) -> str:
        return self._pg_url(self.database_admin_user, self.postgres_password, driver="postgresql")

    def redis_url(self, db: int) -> str:
        auth = f":{quote(self.redis_password, safe='')}@" if self.redis_password else ""
        return f"redis://{auth}{self.redis_host}:{self.redis_port}/{db}"

    @property
    def redis_app_url(self) -> str:
        return self.redis_url(0)

    @property
    def celery_broker_url(self) -> str:
        return self.redis_url(1)

    @property
    def celery_result_url(self) -> str:
        return self.redis_url(2)


@lru_cache
def get_settings() -> Settings:
    return Settings()
