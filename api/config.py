"""
Configuration management for API.
Loads environment variables with sane defaults for local development.
"""

from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings from environment variables"""

    # API Settings
    API_TITLE: str = "BarberScore POS API"
    API_VERSION: str = "1.0.0"
    DEBUG: bool = False

    # Stripe (optional - app starts without Stripe for local dev)
    STRIPE_SECRET_KEY: str = ""
    STRIPE_PUBLISHABLE_KEY: str = ""
    STRIPE_WEBHOOK_SECRET: str = ""

    # Supabase Auth (required for auth endpoints to work)
    SUPABASE_URL: str = ""
    SUPABASE_KEY: str = ""
    SUPABASE_JWT_SECRET: str = ""

    # Frontend URL (for Stripe redirect URLs, set per deployment)
    FRONTEND_URL: str = "http://localhost:3000"

    # CORS - allow all origins in dev, restrict in production via env
    CORS_ORIGINS: list[str] = [
        "http://localhost:3000",
        "http://localhost:5173",
        "http://localhost:8000",
    ]
    CORS_ALLOW_REGEX: str = r"https://.*\.(vercel\.app|onrender\.com)"

    # Security
    SECRET_KEY: str = "dev-secret-change-in-production"
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 30

    class Config:
        env_file = ".env"
        case_sensitive = True


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()
