"""
Vsh-reflow - エージェントテスト
各エージェントの基本動作テスト（LLM外部呼び出しはモック）。
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.models import AgentRole


class TestAgentRoles:
    def test_all_roles_defined(self):
        """§4.1 の全ロールが定義されていることを確認"""
        expected_roles = ["PM", "GROWTH", "CONTENT", "DESIGN", "ANALYST", "GUARD", "PUB"]
        for role in expected_roles:
            assert hasattr(AgentRole, role), f"AgentRole.{role} が未定義"

    def test_role_values(self):
        assert AgentRole.PM.value == "PM-Agent"
        assert AgentRole.GROWTH.value == "Growth-Agent"
        assert AgentRole.CONTENT.value == "Content-Agent"
        assert AgentRole.DESIGN.value == "Design-Agent"
        assert AgentRole.ANALYST.value == "Analyst-Agent"
        assert AgentRole.GUARD.value == "Guard-Agent"
        assert AgentRole.PUB.value == "Pub-Agent"


class TestAgentImports:
    """各エージェントがインポート可能であることを確認"""

    def test_import_pm_agent(self):
        from src.agents.pm_agent import PMAgent, pm_agent
        assert pm_agent.name == "PM-Agent"

    def test_import_growth_agent(self):
        from src.agents.growth_agent import GrowthAgent, growth_agent
        assert growth_agent.name == "Growth-Agent"

    def test_import_content_agent(self):
        from src.agents.content_agent import ContentAgent, content_agent
        assert content_agent.name == "Content-Agent"

    def test_import_design_agent(self):
        from src.agents.design_agent import DesignAgent, design_agent
        assert design_agent.name == "Design-Agent"

    def test_import_guard_agent(self):
        from src.agents.guard_agent import GuardAgent, guard_agent
        assert guard_agent.name == "Guard-Agent"

    def test_import_analyst_agent(self):
        from src.agents.analyst_agent import AnalystAgent, analyst_agent
        assert analyst_agent.name == "Analyst-Agent"

    def test_import_pub_agent(self):
        from src.agents.pub_agent import PubAgent, pub_agent
        assert pub_agent.name == "Pub-Agent"


class TestContentAgentConstraints:
    """Content-Agentのプラットフォーム制約テスト"""

    def test_platform_constraints_exist(self):
        from src.agents.content_agent import PLATFORM_CONSTRAINTS
        platforms = ["X", "Instagram", "TikTok", "LinkedIn", "Facebook"]
        for platform in platforms:
            assert platform in PLATFORM_CONSTRAINTS, f"{platform} の制約が未定義"

    def test_x_constraints(self):
        from src.agents.content_agent import PLATFORM_CONSTRAINTS
        x = PLATFORM_CONSTRAINTS["X"]
        assert x["max_chars"] == 280

    def test_instagram_constraints(self):
        from src.agents.content_agent import PLATFORM_CONSTRAINTS
        insta = PLATFORM_CONSTRAINTS["Instagram"]
        assert insta["max_chars"] == 2200


class TestGuardAgentProhibitions:
    """Guard-Agentの禁止事項テスト"""

    def test_prohibited_keywords_exist(self):
        from src.agents.guard_agent import PROHIBITED_KEYWORDS
        assert len(PROHIBITED_KEYWORDS) >= 7

    def test_prohibited_keywords_include_required(self):
        from src.agents.guard_agent import PROHIBITED_KEYWORDS
        required = ["スパム", "不正アクセス", "著作権違反"]
        for keyword in required:
            assert keyword in PROHIBITED_KEYWORDS, f"禁止キーワード「{keyword}」が未定義"
