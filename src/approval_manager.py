"""
Vsh-reflow - 承認ゲート管理モジュール
§6 準拠。承認必須アクションの管理、タイムアウト、リマインド通知。
"""

import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import select, update

from src.config import settings
from src.database import get_session
from src.models import (
    ApprovalRequest,
    ApprovalStatus,
    RiskLevel,
    Task,
    TaskStatus,
)

logger = logging.getLogger(__name__)


# §6.1 承認必須アクション定義
APPROVAL_REQUIRED_ACTIONS = {
    # 🔴 High - 翔の承認必須
    "sns_account_creation": RiskLevel.HIGH,
    "sns_post": RiskLevel.HIGH,
    "sns_publish": RiskLevel.HIGH,
    "dm_broadcast": RiskLevel.HIGH,
    "ad_placement": RiskLevel.HIGH,
    "ad_budget_setting": RiskLevel.HIGH,
    "api_plan_change": RiskLevel.HIGH,
    "controversial_content": RiskLevel.HIGH,
    # 🟠 Medium - 翔の承認推奨
    "cost_overrun_response": RiskLevel.MEDIUM,
    # 🟢 Low - 自動実行OK
    "periodic_report": RiskLevel.LOW,
    "content_draft": RiskLevel.LOW,
    "competitor_research": RiskLevel.LOW,
    "image_generation": RiskLevel.LOW,
}


class ApprovalManager:
    """承認ゲートマネージャー"""

    def __init__(self):
        self._reminder_minutes = settings.approval.reminder_minutes
        self._second_reminder_minutes = settings.approval.second_reminder_minutes
        self._timeout_hours = settings.approval.timeout_hours

    def requires_approval(self, action_type: str) -> bool:
        """アクションが承認必須かどうかを判定"""
        risk_level = APPROVAL_REQUIRED_ACTIONS.get(action_type, RiskLevel.HIGH)
        # HIGH/MEDIUMは承認必須、LOWは自動実行可
        return risk_level in (RiskLevel.HIGH, RiskLevel.MEDIUM)

    def get_risk_level(self, action_type: str) -> RiskLevel:
        """アクションのリスクレベルを取得"""
        return APPROVAL_REQUIRED_ACTIONS.get(action_type, RiskLevel.HIGH)

    async def create_approval_request(
        self,
        task_id: str,
        requester_agent: str,
        action_type: str,
        summary: str,
        details: Optional[dict] = None,
        preview_content: Optional[str] = None,
        preview_image_url: Optional[str] = None,
        estimated_impact: Optional[str] = None,
        guard_review: Optional[str] = None,
    ) -> ApprovalRequest:
        """承認リクエストを作成"""
        risk_level = self.get_risk_level(action_type)
        timeout_at = datetime.now(timezone.utc) + timedelta(hours=self._timeout_hours)

        async with get_session() as session:
            request = ApprovalRequest(
                task_id=task_id,
                requester_agent=requester_agent,
                action_type=action_type,
                risk_level=risk_level,
                status=ApprovalStatus.PENDING,
                summary=summary,
                details=details or {},
                preview_content=preview_content,
                preview_image_url=preview_image_url,
                estimated_impact=estimated_impact,
                guard_review=guard_review,
                timeout_at=timeout_at,
            )
            session.add(request)
            await session.flush()

            # タスクのステータスも更新
            await session.execute(
                update(Task)
                .where(Task.id == task_id)
                .values(status=TaskStatus.AWAITING_APPROVAL)
            )

            logger.info(
                f"承認リクエスト作成: {request.id} "
                f"(agent={requester_agent}, action={action_type}, risk={risk_level})"
            )
            return request

    async def approve(self, task_code: str) -> Optional[ApprovalRequest]:
        """承認を実行"""
        async with get_session() as session:
            # タスクコードでタスクを検索
            task_result = await session.execute(
                select(Task).where(Task.task_code == task_code)
            )
            task = task_result.scalar_one_or_none()
            if not task:
                return None

            # 承認リクエストを検索
            result = await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.task_id == task.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .order_by(ApprovalRequest.created_at.desc())
            )
            request = result.scalar_one_or_none()
            if not request:
                return None

            request.status = ApprovalStatus.APPROVED
            request.responded_at = datetime.now(timezone.utc)
            task.status = TaskStatus.APPROVED

            logger.info(f"承認完了: {request.id} (task={task_code})")
            return request

    async def reject(
        self,
        task_code: str,
        reason: str = "",
    ) -> Optional[ApprovalRequest]:
        """却下を実行"""
        async with get_session() as session:
            task_result = await session.execute(
                select(Task).where(Task.task_code == task_code)
            )
            task = task_result.scalar_one_or_none()
            if not task:
                return None

            result = await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.task_id == task.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .order_by(ApprovalRequest.created_at.desc())
            )
            request = result.scalar_one_or_none()
            if not request:
                return None

            request.status = ApprovalStatus.REJECTED
            request.rejection_reason = reason
            request.responded_at = datetime.now(timezone.utc)
            task.status = TaskStatus.REJECTED

            logger.info(f"却下完了: {request.id} (task={task_code}, reason={reason})")
            return request

    async def edit(
        self,
        task_code: str,
        instructions: str,
    ) -> Optional[ApprovalRequest]:
        """修正指示を送信"""
        async with get_session() as session:
            task_result = await session.execute(
                select(Task).where(Task.task_code == task_code)
            )
            task = task_result.scalar_one_or_none()
            if not task:
                return None

            result = await session.execute(
                select(ApprovalRequest)
                .where(
                    ApprovalRequest.task_id == task.id,
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                )
                .order_by(ApprovalRequest.created_at.desc())
            )
            request = result.scalar_one_or_none()
            if not request:
                return None

            request.status = ApprovalStatus.EDITED
            request.edit_instructions = instructions
            request.responded_at = datetime.now(timezone.utc)
            task.status = TaskStatus.PENDING  # 再作成のためPENDINGに戻す

            logger.info(f"修正指示: {request.id} (task={task_code})")
            return request

    async def get_pending_requests(self) -> list[ApprovalRequest]:
        """保留中の承認リクエスト一覧を取得"""
        async with get_session() as session:
            result = await session.execute(
                select(ApprovalRequest)
                .where(ApprovalRequest.status == ApprovalStatus.PENDING)
                .order_by(ApprovalRequest.created_at.asc())
            )
            return list(result.scalars().all())

    async def check_timeouts(self) -> list[ApprovalRequest]:
        """タイムアウトした承認リクエストを処理"""
        now = datetime.now(timezone.utc)
        timed_out = []

        async with get_session() as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.status == ApprovalStatus.PENDING,
                    ApprovalRequest.timeout_at <= now,
                )
            )
            for request in result.scalars().all():
                request.status = ApprovalStatus.TIMED_OUT
                request.responded_at = now

                # タスクもキャンセル
                await session.execute(
                    update(Task)
                    .where(Task.id == request.task_id)
                    .values(status=TaskStatus.CANCELLED)
                )
                timed_out.append(request)
                logger.warning(f"承認タイムアウト: {request.id}")

        return timed_out

    async def get_requests_needing_reminder(self) -> list[ApprovalRequest]:
        """リマインドが必要な承認リクエストを取得"""
        now = datetime.now(timezone.utc)
        needs_reminder = []

        async with get_session() as session:
            result = await session.execute(
                select(ApprovalRequest).where(
                    ApprovalRequest.status == ApprovalStatus.PENDING
                )
            )
            for request in result.scalars().all():
                elapsed = (now - request.created_at).total_seconds() / 60

                # 1回目のリマインド (30分)
                if (
                    elapsed >= self._reminder_minutes
                    and request.reminder_sent_at is None
                ):
                    needs_reminder.append(("first", request))

                # 2回目のリマインド (2時間)
                elif (
                    elapsed >= self._second_reminder_minutes
                    and request.second_reminder_sent_at is None
                ):
                    needs_reminder.append(("second", request))

        return needs_reminder

    def format_approval_notification(self, request: ApprovalRequest, task: Task) -> str:
        """§6.2 準拠の承認リクエスト通知フォーマットを生成"""
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S JST")
        risk_emoji = {
            RiskLevel.LOW: "🟢 LOW",
            RiskLevel.MEDIUM: "🟠 MEDIUM",
            RiskLevel.HIGH: "🔴 HIGH",
        }

        lines = [
            "🔔 【承認リクエスト】",
            "━━━━━━━━━━━━━━━━━━",
            f"📋 タスクID: {task.task_code}",
            f"🤖 申請者: {request.requester_agent}",
            f"⏰ 申請時刻: {now_str}",
            "━━━━━━━━━━━━━━━━━━",
            f"📣 実行内容: {request.summary}",
        ]

        if request.preview_content:
            lines.append(f"📝 内容:\n{request.preview_content}")

        if request.preview_image_url:
            lines.append(f"🖼 添付画像: {request.preview_image_url}")

        if request.estimated_impact:
            lines.append(f"📊 予測: {request.estimated_impact}")

        lines.extend([
            f"⚠️ リスク評価: {risk_emoji.get(request.risk_level, '🔴 HIGH')}",
        ])

        if request.guard_review:
            lines.append(f"🛡 Guard審査: {request.guard_review}")

        lines.extend([
            "━━━━━━━━━━━━━━━━━━",
            f"✅ `/approve {task.task_code}`",
            f"❌ `/reject {task.task_code} [理由]`",
            f"✏️ `/edit {task.task_code} [修正指示]`",
        ])

        return "\n".join(lines)


# グローバルインスタンス
approval_manager = ApprovalManager()
