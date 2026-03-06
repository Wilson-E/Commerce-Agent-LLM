"""Configuration management."""
from pathlib import Path
from pydantic_settings import BaseSettings

# Walk up from this file to find the .env at project root
_HERE = Path(__file__).resolve()
_ENV_FILE = next(
    (p / ".env" for p in [_HERE.parent, *_HERE.parents] if (p / ".env").exists()),
    ".env",
)


class Settings(BaseSettings):
    """Application settings loaded from .env."""

    # OpenAI
    OPENAI_API_KEY: str
    LLM_MODEL: str = "gpt-4o-mini"
    EMBEDDING_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 1536

    # Stripe (sandbox)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Application
    MAX_CONTEXT_TOKENS: int = 8000
    MAX_REACT_ITERATIONS: int = 5
    TAX_RATE: float = 0.08
    ENVIRONMENT: str = "development"

    class Config:
        env_file = str(_ENV_FILE)
        case_sensitive = True


settings = Settings()
