"""Configuration management."""
from pathlib import Path
from pydantic import AliasChoices, Field
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

    # RapidAPI — Real-Time Product Search
    RAPIDAPI_KEY: str = ""

    # SerpAPI — Google Shopping
    SERPAPI_KEY: str = Field(
        default="",
        validation_alias=AliasChoices("SERPAPI_KEY", "SERP_API_KEY", "SERPAPI_API_KEY"),
    )

    # Rainforest API — Amazon product data (https://www.rainforestapi.com)
    RAINFOREST_API_KEY: str = ""

    # ScraperAPI — Amazon structured data (https://www.scraperapi.com)
    SCRAPERAPI_KEY: str = ""

    # Open Food Facts — no key required, opt-in via this flag
    OPENFOODFACTS_ENABLED: bool = False

    # Category-specific APIs (both use RAPIDAPI_KEY — no new keys needed)
    ASOS_ENABLED: bool = False          # Fashion: ASOS via RapidAPI
    HOMEDEPOT_ENABLED: bool = False     # Home: Home Depot via RapidAPI

    # Stripe (sandbox)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Auth / JWT
    JWT_SECRET: str = "change-me-in-production-use-a-long-random-secret"
    GOOGLE_CLIENT_ID: str = ""
    MICROSOFT_CLIENT_ID: str = ""

    # Frontend URL (used for Stripe redirect URLs)
    FRONTEND_URL: str = "http://localhost:3000"

    # Application
    MAX_CONTEXT_TOKENS: int = 8000
    MAX_REACT_ITERATIONS: int = 5
    TAX_RATE: float = 0.08
    ENVIRONMENT: str = "development"
    ALLOW_RAPIDAPI_FALLBACK: bool = False  # deprecated — kept for backward compat
    PARALLEL_SEARCH_LIMIT: int = 10

    class Config:
        env_file = str(_ENV_FILE)
        case_sensitive = True
        extra = "ignore"   # ignore VITE_* and other frontend-only vars


settings = Settings()
