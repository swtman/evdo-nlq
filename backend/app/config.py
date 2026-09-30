"""
Application settings — all configuration values the backend needs to run.

HOW CONFIGURATION WORKS IN THIS PROJECT
----------------------------------------
All settings are read from environment variables (or from the `.env` file in
the `backend/` folder). You never hard-code secrets like API keys directly,
instead you put them in `.env`, and this file reads them
automatically at startup.

Example `.env` (see `.env.example` for the full template):

    API_KEY=<your API key here>
    LLM_PROVIDER=claude
    LLM_MODEL=claude-haiku-4-5


HOW TO USE SETTINGS ELSEWHERE IN THE CODE
------------------------------------------
    from app.config import settings   # import the single shared instance


"""

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All runtime configuration for the backend, sourced from environment variables.

    Fields
    ------
    llm_provider : str
        Which LLM service to use. Accepted values: "claude", "gemini",
        "ollama", "fake". "fake" runs without any network calls.
    llm_model : str
        The specific model name within the chosen provider, e.g. "claude-haiku-4-5".
        Passed verbatim to the provider SDK.
    anthropic_api_key : SecretStr
        Secret API key for the Anthropic (Claude) service. Required when
        `llm_provider` is "claude". Stored as SecretStr so it never leaks into
        logs; read the raw value with `.get_secret_value()`. Never commit it.
    gemini_api_key : SecretStr
        Secret API key for Google Gemini. Required when `llm_provider` is
        "gemini". Also a SecretStr; also never committed.
    ollama_base_url : str
        Base URL for the local Ollama service. Default is localhost:11434.
        In Docker Compose, compose overrides this to http://ollama:11434 so
        the backend container can reach the ollama service by its service name.
        Only used when LLM_PROVIDER=ollama.
    graphdb_endpoint : str
        Full URL of the GraphDB SPARQL endpoint. The pipeline sends validated
        SPARQL queries here to get results.
    llm_cache_dir : str
        Directory (relative to `backend/`) where LLM responses are cached on
        disk. Reusing cached responses avoids repeated API costs during
        development. The directory is gitignored.
    llm_cache_disabled : bool
        Set to True (or `LLM_CACHE_DISABLED=1` in .env) to force fresh LLM
        calls, ignoring any cached responses. Useful when you change a prompt
        and want to see the real model output.
    frontend_origin : str
        The URL of the frontend. The backend uses this for CORS, it
        tells the browser "yes, requests from this origin are allowed."
    log_level : str
        Controls how verbose the server's log output is. Common values:
        "DEBUG" (everything), "INFO" (normal), "WARNING" (problems only). 
    grounding_enabled : bool
        When True (default), the grounding module runs before each LLM call:
        it resolves entity aliases (e.g. "ΑΠΘ" → canonical evdx:name) and
        computes Greek word stems, then injects the hints into the system prompt.
    course_linking_enabled : bool
        When True (default), span-based title linking (``title_index.spans``,
        ADR-035) looks for course titles named in the question and offers them
        as exact KG title literals next to the topic stems.
        Set to False (COURSE_LINKING_ENABLED=0) to disable and always use stems.
    book_linking_enabled : bool
        Same as course_linking_enabled, but for book titles. Separate flag
        (not shared with course_linking_enabled) so either corpus can be
        disabled independently for an A/B comparison.
    title_span_threshold : float
        Minimum rapidfuzz token_sort_ratio similarity (0..1 — the value in
        TitleMatch.score) between a span of the question and a course/book
        title. Default 0.85, measured on the frozen dev split (S45): 0.80 let
        every nonexistent dev title through, 0.90 lost recall. Replaces the
        per-class 0.7 thresholds of the whole-phrase ranking (removed with it,
        branch 6): a span holds only the title's words, so a stricter cut-off
        is possible (F7 had already found 0.85 for windows).
    """

    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL")
    anthropic_api_key: SecretStr = Field(default=SecretStr(""), alias="ANTHROPIC_API_KEY")
    gemini_api_key: SecretStr = Field(default=SecretStr(""), alias="GEMINI_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    graphdb_endpoint: str = Field(
        default="http://lod.csd.auth.gr:7200/repositories/EvdoGraph",
        alias="GRAPHDB_ENDPOINT",
    )
    llm_cache_dir: str = Field(default=".llm_cache", alias="LLM_CACHE_DIR")
    llm_cache_disabled: bool = Field(default=False, alias="LLM_CACHE_DISABLED")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")
    grounding_enabled: bool = Field(default=True, alias="GROUNDING_ENABLED")
    course_linking_enabled: bool = Field(default=True, alias="COURSE_LINKING_ENABLED")
    book_linking_enabled: bool = Field(default=True, alias="BOOK_LINKING_ENABLED")
    title_span_threshold: float = Field(default=0.85, alias="TITLE_SPAN_THRESHOLD")

    # `env_file` tells Pydantic to also look for values inside `.env` (not
    # just in the shell environment). `populate_by_name` allows using the
    # Python field name (e.g. `llm_provider`) as a fallback in addition to
    # the alias (`LLM_PROVIDER`).
    model_config = {"env_file": ".env", "populate_by_name": True}


# A single shared instance created once when this module is first imported.
# Every other module does `from app.config import settings` and reads from
# this same object
settings = Settings()
