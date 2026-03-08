"""
Vsh-reflow - 設定管理モジュール
環境変数から全設定をロードし、一元管理する。
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from dotenv import load_dotenv

load_dotenv()


def _get_env(key: str, default: str = "") -> str:
    return os.getenv(key, default)


def _get_env_int(key: str, default: int = 0) -> int:
    val = os.getenv(key, "")
    if not val:
        return default
    try:
        return int(val)
    except (ValueError, TypeError):
        return default


@dataclass(frozen=True)
class DatabaseConfig:
    host: str = _get_env("POSTGRES_HOST", "postgres")
    port: int = _get_env_int("POSTGRES_PORT", 5432)
    db: str = _get_env("POSTGRES_DB", "vsh-reflow")
    user: str = _get_env("POSTGRES_USER", "vsh-reflow")
    password: str = _get_env("POSTGRES_PASSWORD", "changeme")

    @property
    def url(self) -> str:
        return f"postgresql+asyncpg://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"

    @property
    def sync_url(self) -> str:
        return f"postgresql://{self.user}:{self.password}@{self.host}:{self.port}/{self.db}"


@dataclass(frozen=True)
class RedisConfig:
    host: str = _get_env("REDIS_HOST", "redis")
    port: int = _get_env_int("REDIS_PORT", 6379)

    @property
    def url(self) -> str:
        return f"redis://{self.host}:{self.port}/0"

    @property
    def celery_broker_url(self) -> str:
        return f"redis://{self.host}:{self.port}/1"

    @property
    def celery_result_backend(self) -> str:
        return f"redis://{self.host}:{self.port}/2"


@dataclass(frozen=True)
class DiscordConfig:
    bot_token: str = _get_env("DISCORD_BOT_TOKEN")
    guild_id: Optional[int] = _get_env_int("DISCORD_GUILD_ID", 0) or None
    owner_id: Optional[int] = _get_env_int("DISCORD_OWNER_ID", 0) or None
    approvals_channel_id: Optional[int] = _get_env_int("DISCORD_APPROVALS_CHANNEL_ID", 0) or None
    alerts_channel_id: Optional[int] = _get_env_int("DISCORD_ALERTS_CHANNEL_ID", 0) or None
    reports_channel_id: Optional[int] = _get_env_int("DISCORD_REPORTS_CHANNEL_ID", 0) or None
    logs_channel_id: Optional[int] = _get_env_int("DISCORD_LOGS_CHANNEL_ID", 0) or None


@dataclass(frozen=True)
class TelegramConfig:
    bot_token: str = _get_env("TELEGRAM_BOT_TOKEN")
    chat_id: str = _get_env("TELEGRAM_CHAT_ID")


@dataclass(frozen=True)
class OpenAIConfig:
    api_key: str = _get_env("OPENAI_API_KEY")
    default_model: str = _get_env("OPENAI_DEFAULT_MODEL", "gpt-4o-mini")
    important_model: str = _get_env("OPENAI_IMPORTANT_MODEL", "gpt-5.4")
    max_model: str = _get_env("OPENAI_MAX_MODEL", "gpt-5.4")
    image_model: str = _get_env("OPENAI_IMAGE_MODEL", "dall-e-3")


@dataclass(frozen=True)
class AnthropicConfig:
    api_key: str = _get_env("ANTHROPIC_API_KEY")
    default_model: str = _get_env("ANTHROPIC_DEFAULT_MODEL", "claude-opus-4-6")
    important_model: str = _get_env("ANTHROPIC_IMPORTANT_MODEL", "claude-opus-4-6")
    max_model: str = _get_env("ANTHROPIC_MAX_MODEL", "claude-opus-4-6")


@dataclass(frozen=True)
class GeminiConfig:
    api_key: str = _get_env("GEMINI_API_KEY")
    default_model: str = _get_env("GEMINI_DEFAULT_MODEL", "gemini-2.5-flash")
    important_model: str = _get_env("GEMINI_IMPORTANT_MODEL", "gemini-3.1-pro-preview")
    max_model: str = _get_env("GEMINI_MAX_MODEL", "gemini-3.1-pro-preview")


@dataclass(frozen=True)
class SandboxConfig:
    image: str = _get_env("SANDBOX_IMAGE", "vsh-reflow-sandbox")
    timeout_seconds: int = _get_env_int("SANDBOX_TIMEOUT", 120)
    memory_limit: str = _get_env("SANDBOX_MEMORY_LIMIT", "512m")
    network_disabled: bool = True


@dataclass(frozen=True)
class ImageGenConfig:
    fal_key: str = _get_env("FAL_KEY")
    monthly_limit: int = _get_env_int("MONTHLY_IMAGE_GENERATION_LIMIT", 100)


@dataclass(frozen=True)
class CostConfig:
    monthly_budget_limit: int = _get_env_int("MONTHLY_BUDGET_LIMIT", 30000)
    warning_threshold: int = _get_env_int("COST_WARNING_THRESHOLD", 20000)
    alert_threshold: int = _get_env_int("COST_ALERT_THRESHOLD", 25000)
    critical_threshold: int = _get_env_int("COST_CRITICAL_THRESHOLD", 29000)


@dataclass(frozen=True)
class ApprovalConfig:
    reminder_minutes: int = _get_env_int("APPROVAL_REMINDER_MINUTES", 30)
    second_reminder_minutes: int = _get_env_int("APPROVAL_SECOND_REMINDER_MINUTES", 120)
    timeout_hours: int = _get_env_int("APPROVAL_TIMEOUT_HOURS", 24)


@dataclass(frozen=True)
class Settings:
    project_name: str = _get_env("PROJECT_NAME", "Vsh-reflow")
    environment: str = _get_env("ENVIRONMENT", "development")
    log_level: str = _get_env("LOG_LEVEL", "INFO")
    owner_name: str = _get_env("OWNER_NAME", "翔")
    health_check_port: int = _get_env_int("HEALTH_CHECK_PORT", 8080)

    database: DatabaseConfig = field(default_factory=DatabaseConfig)
    redis: RedisConfig = field(default_factory=RedisConfig)
    discord: DiscordConfig = field(default_factory=DiscordConfig)
    telegram: TelegramConfig = field(default_factory=TelegramConfig)
    openai: OpenAIConfig = field(default_factory=OpenAIConfig)
    anthropic: AnthropicConfig = field(default_factory=AnthropicConfig)
    gemini: GeminiConfig = field(default_factory=GeminiConfig)
    image_gen: ImageGenConfig = field(default_factory=ImageGenConfig)
    cost: CostConfig = field(default_factory=CostConfig)
    approval: ApprovalConfig = field(default_factory=ApprovalConfig)
    sandbox: SandboxConfig = field(default_factory=SandboxConfig)


# グローバル設定インスタンス
settings = Settings()
