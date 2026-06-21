from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    # Database / infra
    database_url: str
    redis_url: str
    jwt_secret: str
    supabase_url: str
    supabase_service_key: str
    supabase_source_bucket: str = "source-files"
    supabase_docs_bucket: str = "generated-docs"
    cors_allowed_origins: str = "http://localhost:3000"
    document_ttl_hours: int = 2

    # LLM provider selection: "anthropic" or "gemini"
    llm_provider: str = "anthropic"

    # Anthropic
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-opus-4-5"

    # Gemini
    gemini_api_key: str = ""
    gemini_model: str = "gemini-2.0-flash-lite"


    # Delay in seconds between section generation phases.
    # Increase if hitting Anthropic rate limits (default: 0 = no delay).
    # For Tier-1 accounts (4k tokens/min): set to 65
    phase_delay_seconds: int = 0

    class Config:
        env_file = ".env"


settings = Settings()
