"""
Vsh-reflow - コスト管理モジュール
月額¥30,000上限管理。閾値ベースの通知・制御。LLMモデル自動選択。
§8 準拠。
"""

import logging
from datetime import datetime, timezone
from enum import Enum
from typing import Optional

from sqlalchemy import func, select

from src.config import settings
from src.database import get_session
from src.models import CostRecord

logger = logging.getLogger(__name__)


class CostLevel(str, Enum):
    """コスト状態レベル"""
    NORMAL = "normal"          # ¥0 ~ ¥19,999
    WARNING = "warning"        # ¥20,000 ~ ¥24,999
    ALERT = "alert"            # ¥25,000 ~ ¥28,999
    CRITICAL = "critical"      # ¥29,000+


class LLMTier(str, Enum):
    """LLMモデルティア"""
    DEFAULT = "default"        # Claude Opus 4.6
    IMPORTANT = "important"    # Claude Opus 4.6
    MAX = "max"                # Claude Opus 4.6


# LLM APIコスト概算 (円/1Kトークン) ※為替レートは概算値
COST_PER_1K_TOKENS = {
    # OpenAI
    "gpt-4o-mini": {"input": 0.02, "output": 0.08},
    "gpt-5.4": {"input": 0.30, "output": 0.90},
    # Anthropic (2026-02 Claude 4.6)
    "claude-sonnet-4-6": {"input": 0.45, "output": 2.25},
    "claude-opus-4-6": {"input": 0.75, "output": 3.75},
    # Anthropic (legacy)
    "claude-3-5-sonnet-20241022": {"input": 0.45, "output": 1.35},
    "claude-3-5-haiku-20241022": {"input": 0.12, "output": 0.60},
    # Gemini
    "gemini-2.5-flash": {"input": 0.01, "output": 0.04},
    "gemini-3.1-pro-preview": {"input": 0.19, "output": 0.75},
    # Gemini (legacy)
    "gemini-2.0-flash": {"input": 0.01, "output": 0.04},
    "gemini-2.5-pro": {"input": 0.19, "output": 0.75},
}

# 画像生成コスト概算 (円/枚)
IMAGE_GEN_COST = {
    "dall-e-3": 6.0,         # ~$0.04/image
    "fal_ai_flux": 0.5,      # ~$0.003/image
}


class CostManager:
    """コスト管理マネージャー"""

    def __init__(self):
        self._budget_limit = settings.cost.monthly_budget_limit
        self._warning = settings.cost.warning_threshold
        self._alert = settings.cost.alert_threshold
        self._critical = settings.cost.critical_threshold

    @staticmethod
    def _current_period() -> str:
        """現在の期間文字列を取得 (YYYY-MM)"""
        return datetime.now(timezone.utc).strftime("%Y-%m")

    async def get_monthly_total(self, period: Optional[str] = None) -> float:
        """月間累計コストを取得"""
        period = period or self._current_period()
        async with get_session() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(CostRecord.cost_yen), 0.0)).where(
                    CostRecord.period_month == period
                )
            )
            return float(result.scalar_one())

    async def get_remaining_budget(self) -> float:
        """残り予算を取得"""
        total = await self.get_monthly_total()
        return max(0, self._budget_limit - total)

    async def get_cost_level(self) -> CostLevel:
        """現在のコスト状態レベルを取得"""
        total = await self.get_monthly_total()
        if total >= self._critical:
            return CostLevel.CRITICAL
        elif total >= self._alert:
            return CostLevel.ALERT
        elif total >= self._warning:
            return CostLevel.WARNING
        return CostLevel.NORMAL

    async def can_execute_task(self) -> bool:
        """タスク実行可能かどうか (CRITICAL時はブロック)"""
        level = await self.get_cost_level()
        return level != CostLevel.CRITICAL

    async def record_cost(
        self,
        service: str,
        operation: str,
        cost_yen: float,
        model: Optional[str] = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        agent: Optional[str] = None,
        task_id: Optional[str] = None,
    ) -> CostRecord:
        """コストを記録"""
        async with get_session() as session:
            record = CostRecord(
                service=service,
                model=model,
                operation=operation,
                cost_yen=cost_yen,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                agent=agent,
                task_id=task_id,
                period_month=self._current_period(),
            )
            session.add(record)
            await session.flush()
            logger.info(
                f"コスト記録: {service}/{operation} ¥{cost_yen:.2f} "
                f"(agent={agent}, task={task_id})"
            )
            return record

    def estimate_llm_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
    ) -> float:
        """LLMコストを概算"""
        rates = COST_PER_1K_TOKENS.get(model, {"input": 0.5, "output": 1.5})
        return (
            (input_tokens / 1000) * rates["input"]
            + (output_tokens / 1000) * rates["output"]
        )

    def select_model(
        self,
        tier: LLMTier = LLMTier.DEFAULT,
        provider: str = "openai",
    ) -> str:
        """コスト状態とティアに応じてモデルを自動選択"""
        if provider == "anthropic":
            cfg = settings.anthropic
        elif provider == "gemini":
            cfg = settings.gemini
        else:
            cfg = settings.openai

        if tier == LLMTier.MAX:
            return cfg.max_model
        elif tier == LLMTier.IMPORTANT:
            return cfg.important_model
        return cfg.default_model

    async def get_cost_report(self) -> dict:
        """コストレポートを生成"""
        period = self._current_period()
        total = await self.get_monthly_total(period)
        level = await self.get_cost_level()
        remaining = self._budget_limit - total

        # サービス別コスト集計
        async with get_session() as session:
            result = await session.execute(
                select(
                    CostRecord.service,
                    func.sum(CostRecord.cost_yen).label("total"),
                    func.count(CostRecord.id).label("count"),
                )
                .where(CostRecord.period_month == period)
                .group_by(CostRecord.service)
            )
            by_service = {
                row.service: {"total": float(row.total), "count": int(row.count)}
                for row in result.all()
            }

        return {
            "period": period,
            "total_yen": total,
            "budget_limit_yen": self._budget_limit,
            "remaining_yen": remaining,
            "usage_percent": round((total / self._budget_limit) * 100, 1),
            "level": level.value,
            "by_service": by_service,
        }


# グローバルインスタンス
cost_manager = CostManager()
