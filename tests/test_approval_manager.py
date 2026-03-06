"""
Vsh-reflow - 承認マネージャー テスト
"""

import pytest
from src.approval_manager import (
    ApprovalManager,
    APPROVAL_REQUIRED_ACTIONS,
)
from src.models import RiskLevel


class TestApprovalManager:
    def setup_method(self):
        self.manager = ApprovalManager()

    def test_high_risk_actions_require_approval(self):
        high_risk_actions = [
            "sns_account_creation",
            "sns_post",
            "sns_publish",
            "dm_broadcast",
            "ad_placement",
            "ad_budget_setting",
            "api_plan_change",
            "controversial_content",
        ]
        for action in high_risk_actions:
            assert self.manager.requires_approval(action) is True, f"{action} should require approval"

    def test_medium_risk_actions_require_approval(self):
        assert self.manager.requires_approval("cost_overrun_response") is True

    def test_low_risk_actions_do_not_require_approval(self):
        low_risk_actions = [
            "periodic_report",
            "content_draft",
            "competitor_research",
            "image_generation",
        ]
        for action in low_risk_actions:
            assert self.manager.requires_approval(action) is False, f"{action} should not require approval"

    def test_unknown_actions_default_to_high_risk(self):
        assert self.manager.requires_approval("unknown_action") is True
        assert self.manager.get_risk_level("unknown_action") == RiskLevel.HIGH

    def test_get_risk_level(self):
        assert self.manager.get_risk_level("sns_post") == RiskLevel.HIGH
        assert self.manager.get_risk_level("cost_overrun_response") == RiskLevel.MEDIUM
        assert self.manager.get_risk_level("content_draft") == RiskLevel.LOW

    def test_approval_required_actions_complete(self):
        """§6.1 の全アクションが定義されていることを確認"""
        assert len(APPROVAL_REQUIRED_ACTIONS) >= 12

    def test_format_approval_notification(self):
        """通知フォーマット生成のテスト"""
        from unittest.mock import MagicMock

        mock_request = MagicMock()
        mock_request.requester_agent = "Pub-Agent"
        mock_request.summary = "X（Twitter）への投稿"
        mock_request.preview_content = "テスト投稿文"
        mock_request.preview_image_url = None
        mock_request.estimated_impact = "約2,500imp"
        mock_request.risk_level = RiskLevel.LOW
        mock_request.guard_review = "Guard-Agent審査済み"

        mock_task = MagicMock()
        mock_task.task_code = "TASK-2026-0301-001"

        notification = self.manager.format_approval_notification(mock_request, mock_task)

        assert "🔔 【承認リクエスト】" in notification
        assert "TASK-2026-0301-001" in notification
        assert "Pub-Agent" in notification
        assert "/approve" in notification
        assert "/reject" in notification
        assert "/edit" in notification
