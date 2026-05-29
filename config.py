from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Optional


class Settings(BaseSettings):
    # Required
    anthropic_api_key: str = ""

    # Store
    store_name: str = "VendosDeals"
    store_url: str = "http://localhost:8000"
    secret_key: str = "change-me-in-production"

    # Database
    database_url: str = "sqlite+aiosqlite:///./dropshipping.db"

    # Supplier APIs
    aliexpress_app_key: str = ""
    aliexpress_app_secret: str = ""
    cjdropshipping_api_key: str = ""
    cjdropshipping_email: str = ""

    # Payment
    stripe_api_key: str = ""
    stripe_webhook_secret: str = ""

    # Email (Resend)
    resend_api_key: str = ""
    from_email: str = "vendo@vendosdeals.com"

    # Search
    serp_api_key: str = ""

    # Agent models
    product_agent_model: str = "claude-opus-4-8"
    pricing_agent_model: str = "claude-sonnet-4-6"
    ordering_agent_model: str = "claude-sonnet-4-6"
    website_agent_model: str = "claude-sonnet-4-6"
    manager_agent_model: str = "claude-opus-4-8"

    # Agent schedules (seconds between runs)
    product_agent_interval: int = 3600       # 1 hour
    pricing_agent_interval: int = 1800       # 30 minutes
    ordering_agent_interval: int = 300       # 5 minutes
    website_agent_interval: int = 7200       # 2 hours
    manager_agent_interval: int = 14400      # 4 hours
    image_validation_agent_interval: int = 600  # 10 minutes

    class Config:
        env_file = ".env"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
