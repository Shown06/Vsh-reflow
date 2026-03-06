"""
Vsh-reflow Phase 2 - 新エージェントテスト
"""

import pytest


class TestPhase2AgentImports:
    """Phase 2エージェントのインポートテスト"""

    def test_import_browser_agent(self):
        from src.agents.browser_agent import BrowserAgent, browser_agent
        assert browser_agent.name == "Browser-Agent"

    def test_import_dev_agent(self):
        from src.agents.dev_agent import DevAgent, dev_agent
        assert dev_agent.name == "Dev-Agent"

    def test_import_web_agent(self):
        from src.agents.web_agent import WebAgent, web_agent
        assert web_agent.name == "Web-Agent"

    def test_import_commerce_agent(self):
        from src.agents.commerce_agent import CommerceAgent, commerce_agent
        assert commerce_agent.name == "Commerce-Agent"

    def test_import_deploy_agent(self):
        from src.agents.deploy_agent import DeployAgent, deploy_agent
        assert deploy_agent.name == "Deploy-Agent"


class TestGeminiIntegration:
    """Geminiプロバイダー統合テスト"""

    def test_gemini_config_exists(self):
        from src.config import settings
        assert hasattr(settings, "gemini")
        assert settings.gemini.default_model == "gemini-2.0-flash"
        assert settings.gemini.important_model == "gemini-2.5-pro"

    def test_gemini_cost_defined(self):
        from src.cost_manager import COST_PER_1K_TOKENS
        assert "gemini-2.0-flash" in COST_PER_1K_TOKENS
        assert "gemini-2.5-pro" in COST_PER_1K_TOKENS

    def test_gemini_model_selection(self):
        from src.cost_manager import CostManager, LLMTier
        mgr = CostManager()
        assert mgr.select_model(LLMTier.DEFAULT, "gemini") == "gemini-2.0-flash"
        assert mgr.select_model(LLMTier.IMPORTANT, "gemini") == "gemini-2.5-pro"
        assert mgr.select_model(LLMTier.MAX, "gemini") == "gemini-2.5-pro"

    def test_sandbox_config_exists(self):
        from src.config import settings
        assert hasattr(settings, "sandbox")
        assert settings.sandbox.timeout_seconds == 120


class TestAutoProviderSelection:
    """プロバイダー自動選択テスト"""

    def test_code_tasks_select_anthropic(self):
        from src.agents.browser_agent import browser_agent
        assert browser_agent.auto_select_provider("code generation") == "anthropic"
        assert browser_agent.auto_select_provider("html css dev") == "anthropic"
        assert browser_agent.auto_select_provider("python debug") == "anthropic"

    def test_research_tasks_select_openai_or_gemini(self):
        from src.agents.browser_agent import browser_agent
        provider = browser_agent.auto_select_provider("research analysis")
        assert provider in ("openai", "gemini")

    def test_default_selects_anthropic(self):
        from src.agents.browser_agent import browser_agent
        assert browser_agent.auto_select_provider("") == "anthropic"
        assert browser_agent.auto_select_provider("generic task") == "anthropic"


class TestCommerceAgentPlatforms:
    """Commerce-Agent プラットフォーム対応テスト"""

    def test_mercari_platform(self):
        from src.agents.commerce_agent import CommerceAgent
        agent = CommerceAgent()
        assert agent.name == "Commerce-Agent"


class TestDevAgentCodeExtraction:
    """Dev-Agent コード抽出テスト"""

    def test_extract_python_code(self):
        from src.agents.dev_agent import dev_agent
        text = '```python\nprint("hello")\n```'
        code = dev_agent._extract_code(text, "python")
        assert code == 'print("hello")'

    def test_extract_generic_code(self):
        from src.agents.dev_agent import dev_agent
        text = '```\nsome code\n```'
        code = dev_agent._extract_code(text, "python")
        assert code == "some code"

    def test_extract_plain_text(self):
        from src.agents.dev_agent import dev_agent
        text = "plain code without blocks"
        code = dev_agent._extract_code(text, "python")
        assert code == "plain code without blocks"


class TestCeleryWorkerRegistry:
    """Celeryワーカーレジストリテスト"""

    def test_all_agents_registered(self):
        try:
            from src.workers.celery_app import AGENT_MAP
        except ImportError:
            pytest.skip("celery not installed")
        # Phase 1
        assert "pm" in AGENT_MAP
        assert "growth" in AGENT_MAP
        assert "content" in AGENT_MAP
        assert "design" in AGENT_MAP
        assert "guard" in AGENT_MAP
        assert "analyst" in AGENT_MAP
        assert "pub" in AGENT_MAP
        # Phase 2
        assert "browser" in AGENT_MAP
        assert "dev" in AGENT_MAP
        assert "web" in AGENT_MAP
        assert "commerce" in AGENT_MAP
        assert "deploy" in AGENT_MAP

    def test_total_agents_count(self):
        try:
            from src.workers.celery_app import AGENT_MAP
        except ImportError:
            pytest.skip("celery not installed")
        assert len(AGENT_MAP) == 20  # 7 + 5 + 3 + 5
