"""
Vsh-reflow - Pub-Agent (パブリッシャー)
承認後の投稿実行、スケジュール投稿。承認なしでは実行不可。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.database import get_session
from src.models import AgentRole, ApprovalStatus, Task, TaskStatus

logger = logging.getLogger(__name__)


class PubAgent(BaseAgent):
    """パブリッシャーエージェント（承認後のみ実行）"""

    def __init__(self):
        super().__init__(role=AgentRole.PUB, name="Pub-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "execute_approved":
            return await self._execute_approved_task(task_code, payload)
        elif task_type == "schedule_post":
            return await self._schedule_post(task_code, payload)
        elif task_type == "publish":
            return await self._publish(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _verify_approval(self, task_code: str) -> bool:
        """承認が完了しているか確認"""
        try:
            from sqlalchemy import select
            from src.models import ApprovalRequest

            async with get_session() as session:
                task_result = await session.execute(
                    select(Task).where(Task.task_code == task_code)
                )
                task = task_result.scalar_one_or_none()
                if not task:
                    return False

                # タスクが承認済みか確認
                if task.status == TaskStatus.APPROVED:
                    return True

                # 承認リクエストの状態を確認
                result = await session.execute(
                    select(ApprovalRequest).where(
                        ApprovalRequest.task_id == task.id,
                        ApprovalRequest.status == ApprovalStatus.APPROVED,
                    )
                )
                return result.scalar_one_or_none() is not None
        except Exception as e:
            logger.error(f"承認確認エラー: {e}")
            return False

    async def _execute_approved_task(self, task_code: str, payload: dict) -> dict:
        """承認済みタスクの実行"""
        # 承認確認（必須チェック）
        is_approved = await self._verify_approval(task_code)
        if not is_approved:
            logger.warning(f"⚠️ 未承認タスクの実行をブロック: {task_code}")
            return {
                "success": False,
                "error": "このタスクはまだ承認されていません。/approve でまず承認してください。",
            }

        # タスクの内容を取得
        async with get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Task).where(Task.task_code == task_code)
            )
            task = result.scalar_one_or_none()
            if not task:
                return {"success": False, "error": "タスクが見つかりません"}

        # 投稿実行（SNS API連携）
        publish_result = await self._publish_to_sns(task)

        return {
            "success": True,
            "result": {
                "published": True,
                "task_code": task_code,
                "publish_result": publish_result,
                "published_at": datetime.now(timezone.utc).isoformat(),
            },
            "cost_yen": 0.0,
        }

    async def _publish_to_sns(self, task: Task) -> dict:
        """
        SNSに投稿を実行
        注意: 実際のSNS APIは将来実装。現在はシミュレーション。
        """
        platform = task.payload.get("platform", "X")
        content = task.result.get("content", "") or task.result.get("drafts", "")

        logger.info(
            f"📢 投稿実行 (シミュレーション)\n"
            f"  プラットフォーム: {platform}\n"
            f"  タスク: {task.task_code}\n"
            f"  コンテンツ: {str(content)[:100]}..."
        )

        # 実際のAPI実装時にここを拡張
        # if platform == "X":
        #     return await self._post_to_twitter(content)
        # elif platform == "Instagram":
        #     return await self._post_to_instagram(content)

        # 完了通知
        try:
            from src.bot.discord_bot import send_log_notification
            await send_log_notification(
                f"✅ 投稿完了\n"
                f"📋 タスクID: {task.task_code}\n"
                f"📱 プラットフォーム: {platform}\n"
                f"⏰ 実行時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
            )
        except Exception as e:
            logger.debug(f"Discord通知エラー (非致命的): {e}")

        return {
            "platform": platform,
            "status": "published_simulation",
            "note": "SNS API統合後に実際の投稿が実行されます",
        }

    async def _schedule_post(self, task_code: str, payload: dict) -> dict:
        """スケジュール投稿"""
        scheduled_at = payload.get("scheduled_at", "")
        platform = payload.get("platform", "X")
        content = payload.get("content", "")

        # 承認確認
        is_approved = await self._verify_approval(task_code)
        if not is_approved:
            return {
                "success": False,
                "error": "スケジュール投稿にも承認が必要です。",
            }

        logger.info(
            f"📅 スケジュール投稿設定\n"
            f"  タスク: {task_code}\n"
            f"  予定時刻: {scheduled_at}\n"
            f"  プラットフォーム: {platform}"
        )

        # Celery ETAで遅延実行をスケジュール
        # from src.workers.celery_app import dispatch_agent_task
        # dispatch_agent_task.apply_async(
        #     args=["pub", task_code, "publish", payload],
        #     eta=datetime.fromisoformat(scheduled_at),
        # )

        return {
            "success": True,
            "result": {
                "scheduled": True,
                "scheduled_at": scheduled_at,
                "platform": platform,
            },
            "cost_yen": 0.0,
        }

    async def _publish(self, task_code: str, payload: dict) -> dict:
        """即時投稿"""
        is_approved = await self._verify_approval(task_code)
        if not is_approved:
            return {
                "success": False,
                "error": "投稿には承認が必要です。",
            }

        async with get_session() as session:
            from sqlalchemy import select
            result = await session.execute(
                select(Task).where(Task.task_code == task_code)
            )
            task = result.scalar_one_or_none()
            if not task:
                return {"success": False, "error": "タスクが見つかりません"}

        publish_result = await self._publish_to_sns(task)

        return {
            "success": True,
            "result": publish_result,
            "cost_yen": 0.0,
        }


# エージェントインスタンス
pub_agent = PubAgent()
