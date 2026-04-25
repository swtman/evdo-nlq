"""Application settings — all values are env-backed via .env."""
from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    graphdb_endpoint: str = Field(
        default="http://lod.csd.auth.gr:7200/repositories/Evdoxus",
        alias="GRAPHDB_ENDPOINT",
    )
    llm_cache_dir: str = Field(default=".llm_cache", alias="LLM_CACHE_DIR")
    llm_cache_disabled: bool = Field(default=False, alias="LLM_CACHE_DISABLED")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    model_config = {"env_file": ".env", "populate_by_name": True}


settings = Settings()
