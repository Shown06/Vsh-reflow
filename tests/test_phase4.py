"""
Vsh-reflow Phase 4 - 業務拡張テスト
"""

import pytest


class TestPhase4AgentImports:
    """Phase 4エージェントのインポートテスト"""

    def test_import_seo_agent(self):
        from src.agents.seo_agent import SEOAgent, seo_agent
        assert seo_agent.name == "SEO-Agent"

    def test_import_crm_agent(self):
        from src.agents.crm_agent import CRMAgent, crm_agent
        assert crm_agent.name == "CRM-Agent"

    def test_import_line_agent(self):
        from src.agents.line_agent import LINEAgent, line_agent
        assert line_agent.name == "LINE-Agent"

    def test_import_schedule_agent(self):
        from src.agents.schedule_agent import ScheduleAgent, schedule_agent
        assert schedule_agent.name == "Schedule-Agent"

    def test_import_finance_agent(self):
        from src.agents.finance_agent import FinanceAgent, finance_agent
        assert finance_agent.name == "Finance-Agent"


class TestClaudeDefault:
    """デフォルトLLMがClaudeに変更されたことを確認"""

    def test_default_provider_is_anthropic(self):
        from src.agents.seo_agent import seo_agent
        assert seo_agent.auto_select_provider("") == "anthropic"
        assert seo_agent.auto_select_provider("generic task") == "anthropic"

    def test_code_still_selects_anthropic(self):
        from src.agents.seo_agent import seo_agent
        assert seo_agent.auto_select_provider("code generation") == "anthropic"

    def test_analysis_without_gemini_selects_anthropic(self):
        from src.agents.seo_agent import seo_agent
        provider = seo_agent.auto_select_provider("analysis report")
        assert provider in ("anthropic", "gemini")


class TestSEOAgentMethods:
    """SEO-Agent メソッド確認"""

    def test_has_seo_methods(self):
        from src.agents.seo_agent import seo_agent
        assert hasattr(seo_agent, "_seo_audit")
        assert hasattr(seo_agent, "_keyword_research")
        assert hasattr(seo_agent, "_meta_optimize")
        assert hasattr(seo_agent, "_competitor_seo")
        assert hasattr(seo_agent, "_content_seo")


class TestCRMAgentOperations:
    """CRM-Agent 基本操作テスト"""

    def test_crm_has_methods(self):
        from src.agents.crm_agent import crm_agent
        assert hasattr(crm_agent, "_add_contact")
        assert hasattr(crm_agent, "_list_contacts")
        assert hasattr(crm_agent, "_generate_follow_up")
        assert hasattr(crm_agent, "_lead_scoring")
        assert hasattr(crm_agent, "_pipeline_report")


class TestFinanceAgentOperations:
    """Finance-Agent 基本操作テスト"""

    def test_finance_has_methods(self):
        from src.agents.finance_agent import finance_agent
        assert hasattr(finance_agent, "_add_expense")
        assert hasattr(finance_agent, "_add_income")
        assert hasattr(finance_agent, "_create_invoice")
        assert hasattr(finance_agent, "_monthly_report")
        assert hasattr(finance_agent, "_tax_summary")
        assert hasattr(finance_agent, "_budget_plan")


class TestPhase4WorkerRegistry:
    """Phase 4ワーカーレジストリテスト"""

    def test_phase4_agents_registered(self):
        try:
            from src.workers.celery_app import AGENT_MAP
        except ImportError:
            pytest.skip("celery not installed")
        assert "seo" in AGENT_MAP
        assert "crm" in AGENT_MAP
        assert "line" in AGENT_MAP
        assert "schedule" in AGENT_MAP
        assert "finance" in AGENT_MAP

    def test_total_agents_count_with_phase4(self):
        try:
            from src.workers.celery_app import AGENT_MAP
        except ImportError:
            pytest.skip("celery not installed")
        assert len(AGENT_MAP) == 20  # 7 + 5 + 3 + 5
