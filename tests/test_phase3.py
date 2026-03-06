"""
Vsh-reflow Phase 3 - 統合拡張テスト
"""

import pytest


class TestPhase3AgentImports:
    """Phase 3エージェントのインポートテスト"""

    def test_import_github_agent(self):
        from src.agents.github_agent import GitHubAgent, github_agent
        assert github_agent.name == "GitHub-Agent"

    def test_import_email_agent(self):
        from src.agents.email_agent import EmailAgent, email_agent
        assert email_agent.name == "Email-Agent"

    def test_import_saas_agent(self):
        from src.agents.saas_agent import SaaSAgent, saas_agent
        assert saas_agent.name == "SaaS-Agent"


class TestGitHubAgentConfig:
    """GitHub-Agent設定テスト"""

    def test_github_agent_has_api_methods(self):
        from src.agents.github_agent import github_agent
        assert hasattr(github_agent, "_create_repo")
        assert hasattr(github_agent, "_create_pr")
        assert hasattr(github_agent, "_create_issue")
        assert hasattr(github_agent, "_review_pr")
        assert hasattr(github_agent, "_push_code")
        assert hasattr(github_agent, "_list_repos")

    def test_github_headers_format(self):
        from src.agents.github_agent import github_agent
        headers = github_agent._get_headers()
        assert "Authorization" in headers
        assert "Accept" in headers
        assert headers["Accept"] == "application/vnd.github+json"


class TestEmailAgentConfig:
    """Email-Agent設定テスト"""

    def test_email_agent_has_methods(self):
        from src.agents.email_agent import email_agent
        assert hasattr(email_agent, "_send_email")
        assert hasattr(email_agent, "_read_emails")
        assert hasattr(email_agent, "_draft_email")
        assert hasattr(email_agent, "_auto_reply")
        assert hasattr(email_agent, "_send_newsletter")


class TestSaaSAgentServices:
    """SaaS-Agent サービス対応テスト"""

    def test_saas_services_defined(self):
        from src.agents.saas_agent import SAAS_SERVICES
        assert "google_sheets" in SAAS_SERVICES
        assert "google_analytics" in SAAS_SERVICES
        assert "notion" in SAAS_SERVICES
        assert "shopify" in SAAS_SERVICES
        assert "slack" in SAAS_SERVICES

    def test_saas_agent_has_methods(self):
        from src.agents.saas_agent import saas_agent
        assert hasattr(saas_agent, "_operate_google_sheets")
        assert hasattr(saas_agent, "_operate_notion")
        assert hasattr(saas_agent, "_send_slack_message")
        assert hasattr(saas_agent, "_get_analytics")
        assert hasattr(saas_agent, "_browse_saas")
        assert hasattr(saas_agent, "_operate_shopify")


class TestPhase3WorkerRegistry:
    """Phase 3ワーカーレジストリテスト"""

    def test_phase3_agents_registered(self):
        try:
            from src.workers.celery_app import AGENT_MAP
        except ImportError:
            pytest.skip("celery not installed")
        assert "github" in AGENT_MAP
        assert "email" in AGENT_MAP
        assert "saas" in AGENT_MAP

    def test_total_agents_count_with_phase3(self):
        try:
            from src.workers.celery_app import AGENT_MAP
        except ImportError:
            pytest.skip("celery not installed")
        assert len(AGENT_MAP) == 20  # 7 + 5 + 3 + 5
