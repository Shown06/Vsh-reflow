"""
Vsh-reflow - Analyst-Agent (アナリスト)
パフォーマンス分析、改善提案、週次レポート生成。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import func, select

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier, cost_manager
from src.database import get_session
from src.models import AgentRole, AuditLog, CostRecord, Task, TaskStatus

logger = logging.getLogger(__name__)


class AnalystAgent(BaseAgent):
    """アナリストエージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.ANALYST, name="Analyst-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "weekly_report":
            return await self._generate_weekly_report(task_code, payload)
        elif task_type == "meeting_analysis":
            return await self._meeting_analysis(task_code, payload)
        elif task_type == "performance_analysis":
            return await self._analyze_performance(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _generate_weekly_report(self, task_code: str, payload: dict) -> dict:
        """週次パフォーマンスレポート生成"""
        now = datetime.now(timezone.utc)
        week_ago = now - timedelta(days=7)

        # DB集計
        stats = await self._gather_weekly_stats(week_ago, now)
        cost_report = await cost_manager.get_cost_report()

        # LLMでレポート生成
        result = await self.call_llm(
            prompt=f"""以下のデータをもとに、週次パフォーマンスレポートを作成してください。

期間: {week_ago.strftime('%Y-%m-%d')} ～ {now.strftime('%Y-%m-%d')}

【タスク統計】
- 総タスク数: {stats['total_tasks']}
- 完了: {stats['completed_tasks']}
- 失敗: {stats['failed_tasks']}
- 承認待ち: {stats['pending_approvals']}

【コスト統計】
- 月間累計: ¥{cost_report['total_yen']:,.0f}
- 予算残: ¥{cost_report['remaining_yen']:,.0f}
- 使用率: {cost_report['usage_percent']}%

【エージェント別実行数】
{stats.get('agent_stats', 'データなし')}

以下の形式でレポートを作成:
1. 📊 週間サマリー
2. 🎯 KPI達成状況
3. 💰 コスト分析
4. 📈 改善提案（3つ）
5. 📋 来週の推奨アクション""",
            system_prompt="あなたはデータアナリストです。KPIに基づいた客観的なレポートを作成してください。",
            tier=LLMTier.IMPORTANT,
        )

        return {
            "success": True,
            "result": {
                "weekly_report": result.get("text", ""),
                "stats": stats,
                "cost_report": cost_report,
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _gather_weekly_stats(self, start: datetime, end: datetime) -> dict:
        """週間統計データを収集"""
        try:
            async with get_session() as session:
                # 総タスク数
                total = await session.execute(
                    select(func.count(Task.id)).where(
                        Task.created_at >= start,
                        Task.created_at <= end,
                    )
                )
                total_tasks = total.scalar_one()

                # 完了タスク
                completed = await session.execute(
                    select(func.count(Task.id)).where(
                        Task.status == TaskStatus.COMPLETED,
                        Task.completed_at >= start,
                        Task.completed_at <= end,
                    )
                )
                completed_tasks = completed.scalar_one()

                # 失敗タスク
                failed = await session.execute(
                    select(func.count(Task.id)).where(
                        Task.status == TaskStatus.FAILED,
                        Task.created_at >= start,
                        Task.created_at <= end,
                    )
                )
                failed_tasks = failed.scalar_one()

                # 承認待ち
                pending = await session.execute(
                    select(func.count(Task.id)).where(
                        Task.status == TaskStatus.AWAITING_APPROVAL,
                    )
                )
                pending_approvals = pending.scalar_one()

                # エージェント別
                agent_result = await session.execute(
                    select(
                        Task.assigned_agent,
                        func.count(Task.id).label("count"),
                    )
                    .where(
                        Task.created_at >= start,
                        Task.created_at <= end,
                    )
                    .group_by(Task.assigned_agent)
                )
                agent_lines = []
                for row in agent_result.all():
                    agent_lines.append(f"  - {row.assigned_agent}: {row.count}件")

                return {
                    "total_tasks": total_tasks,
                    "completed_tasks": completed_tasks,
                    "failed_tasks": failed_tasks,
                    "pending_approvals": pending_approvals,
                    "agent_stats": "\n".join(agent_lines) or "データなし",
                }
        except Exception as e:
            logger.error(f"統計データ収集エラー: {e}")
            return {
                "total_tasks": 0,
                "completed_tasks": 0,
                "failed_tasks": 0,
                "pending_approvals": 0,
                "agent_stats": "データ収集エラー",
            }

    async def _meeting_analysis(self, task_code: str, payload: dict) -> dict:
        """会議用パフォーマンス分析・推薦"""
        topic = payload.get("topic", "")

        result = await self.call_llm(
            prompt=f"""AI社内会議のため、パフォーマンス分析と推薦を行ってください。

テーマ: {topic}

以下を分析してください:
1. 過去の類似テーマのパフォーマンス
2. 最もエンゲージメントが高かったコンテンツの特徴
3. 推奨する方向性と理由
4. 避けるべきアプローチ""",
            system_prompt="あなたはデータ駆動型のマーケティングアナリストです。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"analysis": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _analyze_performance(self, task_code: str, payload: dict) -> dict:
        """一般的なパフォーマンス分析"""
        target = payload.get("target", "")

        result = await self.call_llm(
            prompt=f"以下のターゲットに対するパフォーマンス分析を行ってください: {target}",
            system_prompt="データに基づいた客観的な分析をしてください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"analysis": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
analyst_agent = AnalystAgent()
