from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    openai_api_key: str = ""
    model: str = "gpt-4o-mini"
    temperature: float = 0.0
    request_timeout: int = 30
    max_retries: int = 2
    allowed_origins: str = "*"
    app_host: str = "0.0.0.0"
    app_port: int = 8000

    # Rate limiting
    enable_rate_limit: bool = True
    rate_limit_per_minute: int = 60

    # Observability
    enable_metrics: bool = True
    enable_tracing: bool = False
    otel_service_name: str = "projeto_codex"
    otel_exporter_otlp_endpoint: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


def get_settings() -> Settings:
    return Settings()
