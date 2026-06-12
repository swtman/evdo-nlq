"""
Application settings — all configuration values the backend needs to run.

HOW CONFIGURATION WORKS IN THIS PROJECT
----------------------------------------
All settings are read from environment variables (or from the `.env` file in
the `backend/` folder). You never hard-code secrets like API keys directly in
Python — instead you put them in `.env`, and this file reads them
automatically at startup.

Example `.env` (see `.env.example` for the full template):

    ANTHROPIC_API_KEY=sk-ant-...
    LLM_PROVIDER=claude
    LLM_MODEL=claude-haiku-4-5

WHAT IS Pydantic / BaseSettings?
---------------------------------
Pydantic is a library that validates data. `BaseSettings` is a special
Pydantic class designed specifically for configuration: it reads values from
environment variables, validates their types (e.g. ensures a bool really is
True/False), and exposes them as a plain Python object.

WHAT IS `Field(..., alias=...)`?
---------------------------------
Each setting has a Python-friendly name (e.g. `llm_provider`, lower_snake_case)
and an environment-variable alias (e.g. `LLM_PROVIDER`, UPPER_SNAKE_CASE).
The alias is what you write in `.env`; the Python name is what you use in code.
`Field(default=...)` sets the fallback value when the variable is not set.

HOW TO USE SETTINGS ELSEWHERE IN THE CODE
------------------------------------------
    from app.config import settings   # import the single shared instance

    print(settings.llm_provider)      # "claude" (or whatever is in .env)
    print(settings.anthropic_api_key) # the key from .env, kept out of code
"""

from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """All runtime configuration for the backend, sourced from environment variables.

    Fields
    ------
    llm_provider : str
        Which LLM service to use. Accepted values: "claude", "gemini", "fake".
        "fake" runs without any network calls — useful for tests and UI work.
    llm_model : str
        The specific model name within the chosen provider, e.g. "claude-haiku-4-5".
        Passed verbatim to the provider SDK.
    anthropic_api_key : str
        Secret API key for the Anthropic (Claude) service. Required when
        `llm_provider` is "claude". Never commit this value to git.
    gemini_api_key : str
        Secret API key for Google Gemini. Required when `llm_provider` is
        "gemini". Also never committed.
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
        The URL of the React frontend. The backend uses this for CORS — it
        tells the browser "yes, requests from this origin are allowed."
    log_level : str
        Controls how verbose the server's log output is. Common values:
        "DEBUG" (everything), "INFO" (normal), "WARNING" (problems only).
    """

    llm_provider: str = Field(default="claude", alias="LLM_PROVIDER")
    llm_model: str = Field(default="claude-haiku-4-5", alias="LLM_MODEL")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    ollama_base_url: str = Field(default="http://localhost:11434", alias="OLLAMA_BASE_URL")
    graphdb_endpoint: str = Field(
        default="http://lod.csd.auth.gr:7200/repositories/EvdoGraph",
        alias="GRAPHDB_ENDPOINT",
    )
    llm_cache_dir: str = Field(default=".llm_cache", alias="LLM_CACHE_DIR")
    llm_cache_disabled: bool = Field(default=False, alias="LLM_CACHE_DISABLED")
    frontend_origin: str = Field(default="http://localhost:5173", alias="FRONTEND_ORIGIN")
    log_level: str = Field(default="INFO", alias="LOG_LEVEL")

    # `env_file` tells Pydantic to also look for values inside `.env` (not
    # just in the shell environment). `populate_by_name` allows using the
    # Python field name (e.g. `llm_provider`) as a fallback in addition to
    # the alias (`LLM_PROVIDER`).
    model_config = {"env_file": ".env", "populate_by_name": True}


# A single shared instance created once when this module is first imported.
# Every other module does `from app.config import settings` and reads from
# this same object — there is no need to create a new Settings() anywhere else.
settings = Settings()
