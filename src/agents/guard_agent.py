"""
Vsh-reflow - Guard-Agent (コンプライアンス / 財務)
コスト監視（§8.2）、リスク審査、STOP権限、禁止事項チェック。
"""

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import CostLevel, LLMTier, cost_manager
from src.config import settings
from src.models import AgentRole

logger = logging.getLogger(__name__)

# §9.2 禁止事項リスト
PROHIBITED_KEYWORDS = [
    "大量アカウント自動作成",
    "スパム",
    "フォロー爆撃",
    "認証突破",
    "不正アクセス",
    "個人情報",
    "著作権違反",
]


class GuardAgent(BaseAgent):
    """コンプライアンス / 財務エージェント（STOP権限あり）"""

    def __init__(self):
        super().__init__(role=AgentRole.GUARD, name="Guard-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "cost_check":
            return await self._check_cost(task_code, payload)
        elif task_type == "risk_review":
            return await self._review_risk(task_code, payload)
        elif task_type == "meeting_review":
            return await self._meeting_review(task_code, payload)
        elif task_type == "content_review":
            return await self._review_content(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _check_cost(self, task_code: str, payload: dict) -> dict:
        """コスト状態チェック（§8.2準拠）"""
        report = await cost_manager.get_cost_report()
        level = CostLevel(report["level"])
        alerts = []

        if level == CostLevel.WARNING:
            alerts.append({
                "level": "warning",
                "message": f"⚠️ 月間コスト ¥{report['total_yen']:,.0f} に到達（注意）",
                "action": "Discord通知送信",
            })
        elif level == CostLevel.ALERT:
            alerts.append({
                "level": "alert",
                "message": f"🟠 月間コスト ¥{report['total_yen']:,.0f} に到達（警告）",
                "action": "Discord+Telegram通知 + 低コストモード切替",
            })
        elif level == CostLevel.CRITICAL:
            alerts.append({
                "level": "critical",
                "message": f"🔴 月間コスト ¥{report['total_yen']:,.0f} に到達（危険）",
                "action": "新規タスク受付停止 + 緊急承認要求",
            })

        # 通知送信
        if alerts:
            for alert in alerts:
                await self._send_cost_alert(alert)

        return {
            "success": True,
            "result": {
                "cost_report": report,
                "alerts": alerts,
                "status": level.value,
            },
            "cost_yen": 0.0,
        }

    async def _send_cost_alert(self, alert: dict):
        """コストアラートを送信"""
        try:
            from src.bot.telegram_bot import send_cost_alert
            await send_cost_alert(
                alert["level"],
                0,  # 個別呼び出し時は0
                settings.cost.monthly_budget_limit,
            )
        except Exception as e:
            logger.error(f"コストアラート送信エラー: {e}")

    async def _review_risk(self, task_code: str, payload: dict) -> dict:
        """リスク審査"""
        content = payload.get("content", "")
        action_type = payload.get("action_type", "")

        # 禁止事項チェック
        violations = []
        for keyword in PROHIBITED_KEYWORDS:
            if keyword in content:
                violations.append(keyword)

        if violations:
            return {
                "success": True,
                "result": {
                    "approved": False,
                    "risk_level": "HIGH",
                    "reason": f"禁止事項に該当: {', '.join(violations)}",
                    "recommendation": "STOP - このコンテンツは公開できません",
                },
                "cost_yen": 0.0,
            }

        # LLMによるリスク評価
        result = await self.call_llm(
            prompt=f"""以下のコンテンツのリスク評価を行ってください。

コンテンツ: {content}
アクション種別: {action_type}

以下の観点で評価してください:
1. 炎上リスク (LOW/MEDIUM/HIGH)
2. 法的リスク (LOW/MEDIUM/HIGH)
3. ブランドリスク (LOW/MEDIUM/HIGH)
4. 総合リスク評価 (LOW/MEDIUM/HIGH)
5. 改善提案（あれば）

JSON形式で回答してください。""",
            system_prompt="あなたはSNSマーケティングのコンプライアンス専門家です。厳格にリスクを評価してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "approved": True,
                "risk_assessment": result.get("text", ""),
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _meeting_review(self, task_code: str, payload: dict) -> dict:
        """会議用リスク・コスト審査"""
        topic = payload.get("topic", "")

        # コストチェック
        report = await cost_manager.get_cost_report()

        result = await self.call_llm(
            prompt=f"""AI社内会議のリスク・コスト審査を行ってください。

会議テーマ: {topic}

現在のコスト状況:
- 月間累計: ¥{report['total_yen']:,.0f}
- 予算上限: ¥{report['budget_limit_yen']:,}
- 残り: ¥{report['remaining_yen']:,.0f}

以下を報告してください:
1. コスト面の懸念事項
2. リスク面の懸念事項
3. 承認推奨度 (GO / CAUTION / STOP)
4. 条件付き承認の場合の条件""",
            system_prompt="あなたは厳格なコンプライアンス担当者です。リスクを見逃さないでください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "guard_review": result.get("text", ""),
                "cost_report": report,
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _review_content(self, task_code: str, payload: dict) -> dict:
        """コンテンツの安全性レビュー"""
        content = payload.get("content", "")

        result = await self.call_llm(
            prompt=f"""以下のSNS投稿コンテンツの安全性を審査してください。

コンテンツ: {content}

チェック項目:
- 著作権侵害の可能性
- 誹謗中傷・差別的表現
- 虚偽・誤解を招く表現
- センシティブな話題への配慮
- プラットフォーム規約違反の可能性

結果: PASS / REVIEW_NEEDED / REJECT""",
            system_prompt="あなたはSNSコンテンツの安全性審査の専門家です。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"content_review": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
guard_agent = GuardAgent()
