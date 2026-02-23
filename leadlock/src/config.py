"""
Application configuration using pydantic-settings.
All config is validated at startup - fail fast if anything is missing.
"""
from pydantic_settings import BaseSettings
from pydantic import Field
from functools import lru_cache


class Settings(BaseSettings):
    # Application
    app_env: str = "development"
    app_host: str = "0.0.0.0"
    app_port: int = 8000
    app_base_url: str = "http://localhost:8000"
    app_secret_key: str
    log_level: str = "INFO"

    # Database
    database_url: str
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # Anthropic (legacy; no longer used in primary routing)
    anthropic_api_key: str = ""
    anthropic_model_fast: str = "claude-haiku-4-5-20251001"
    anthropic_model_smart: str = "claude-sonnet-4-5-20250929"
    anthropic_max_tokens_fast: int = 300
    anthropic_max_tokens_smart: int = 500
    anthropic_timeout_seconds: int = 10

    # OpenAI (primary)
    openai_api_key: str = ""
    openai_model_fast: str = "gpt-4o-mini"
    openai_model_smart: str = "gpt-4o-mini"

    # Twilio
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_messaging_service_sid: str = ""

    # Telnyx (fallback)
    telnyx_api_key: str = ""
    telnyx_messaging_profile_id: str = ""

    # SendGrid
    sendgrid_api_key: str = ""
    sendgrid_from_email: str = "reports@leadlock.io"
    sendgrid_from_name: str = "LeadLock"
    sendgrid_webhook_verification_key: str = ""  # SendGrid Event Webhook signing key

    # Webhook secrets
    webhook_secret_google: str = ""
    webhook_secret_angi: str = ""
    webhook_secret_facebook: str = ""
    webhook_signing_key: str = ""

    # Encryption
    encryption_key: str = ""

    # Sentry
    sentry_dsn: str = ""

    # Dashboard
    dashboard_jwt_secret: str = ""
    dashboard_jwt_expiry_hours: int = 24
    dashboard_base_url: str = "https://leadlock.org"
    allowed_origins: str = ""  # Comma-separated CORS origins (auto-includes localhost in dev)

    # Sales Engine
    brave_api_key: str = ""
    hunter_api_key: str = ""  # DEPRECATED: Hunter.io removed, using website scraping + pattern guessing
    sales_engine_enabled: bool = False
    sales_daily_email_limit: int = 50
    sales_daily_scrape_limit: int = 100

    # Agent feature flags (toggle without code deploys)
    agent_ab_test_engine: bool = True
    agent_winback_agent: bool = True
    agent_referral_agent: bool = False      # Disabled: crash bugs, needs fix
    agent_reflection_agent: bool = False    # Disabled: writes to unread table

    # Transactional Email (auth flows, billing notifications)
    sendgrid_transactional_key: str = ""  # Separate key for transactional emails
    from_email_transactional: str = "noreply@leadlock.org"

    # Stripe Billing
    stripe_secret_key: str = ""
    stripe_publishable_key: str = ""
    stripe_webhook_secret: str = ""
    stripe_price_starter: str = ""
    stripe_price_pro: str = ""
    stripe_price_business: str = ""

    # Alerting
    alert_webhook_url: str = ""  # Discord/Slack webhook URL for critical alerts

    # Operational limits
    max_cold_followups: int = 3
    max_conversation_turns: int = 10
    lead_response_deadline_ms: int = 60000
    lead_response_target_ms: int = 10000

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    return Settings()
