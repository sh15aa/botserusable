from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Application
    APP_NAME: str = "BotProductFactory"
    ENVIRONMENT: str = "development"
    DEBUG: bool = True
    HOST: str = "0.0.0.0"
    PORT: int = 8000
    SECRET_KEY: str = Field(default="change-this-to-a-secure-random-32-byte-hex-string")

    # Redis & ARQ Worker
    REDIS_URL: str = Field(default="redis://localhost:6379/0")

    # Database
    DATABASE_URL: str = Field(
        default="postgresql+asyncpg://postgres:postgres@localhost:5432/bot_factory"
    )

    # WhatsApp Cloud API
    WHATSAPP_PHONE_NUMBER_ID: Optional[str] = None
    WHATSAPP_ACCESS_TOKEN: Optional[str] = None
    WHATSAPP_APP_SECRET: Optional[str] = None
    WHATSAPP_VERIFY_TOKEN: Optional[str] = None
    WHATSAPP_API_VERSION: str = "v19.0"

    # Telegram Bot API
    TELEGRAM_BOT_TOKEN: Optional[str] = None
    TELEGRAM_SECRET_TOKEN: Optional[str] = None

    # Chatwoot Integration
    CHATWOOT_BASE_URL: str = "https://app.chatwoot.com"
    CHATWOOT_API_ACCESS_TOKEN: Optional[str] = None
    CHATWOOT_ACCOUNT_ID: int = 1
    CHATWOOT_INBOX_ID: int = 1
    CHATWOOT_WEBHOOK_SECRET: Optional[str] = None

    # AI Brain
    OPENAI_API_KEY: Optional[str] = None
    OPENAI_MODEL: str = "gpt-4o-mini"
    AI_CANARY_SECRET: str = "default-canary-secret-salt"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )


settings = Settings()
