"""
Vsh-reflow - コスト管理 テスト
"""

import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from src.cost_manager import CostManager, CostLevel, LLMTier, COST_PER_1K_TOKENS


class TestCostManager:
    def setup_method(self):
        self.manager = CostManager()

    def test_estimate_llm_cost_gpt4o_mini(self):
        cost = self.manager.estimate_llm_cost("gpt-4o-mini", 1000, 500)
        expected = (1000 / 1000) * 0.02 + (500 / 1000) * 0.08
        assert abs(cost - expected) < 0.001

    def test_estimate_llm_cost_gpt4o(self):
        cost = self.manager.estimate_llm_cost("gpt-4o", 1000, 500)
        expected = (1000 / 1000) * 0.38 + (500 / 1000) * 1.13
        assert abs(cost - expected) < 0.001

    def test_estimate_llm_cost_claude_opus(self):
        cost = self.manager.estimate_llm_cost("claude-3-opus-20240229", 1000, 500)
        expected = (1000 / 1000) * 2.25 + (500 / 1000) * 6.75
        assert abs(cost - expected) < 0.001

    def test_estimate_llm_cost_unknown_model(self):
        cost = self.manager.estimate_llm_cost("unknown-model", 1000, 500)
        # デフォルトレート使用
        expected = (1000 / 1000) * 0.5 + (500 / 1000) * 1.5
        assert abs(cost - expected) < 0.001

    def test_select_model_default_openai(self):
        model = self.manager.select_model(LLMTier.DEFAULT, "openai")
        assert model == "gpt-4o-mini"

    def test_select_model_important_openai(self):
        model = self.manager.select_model(LLMTier.IMPORTANT, "openai")
        assert model == "gpt-4o"

    def test_select_model_max_anthropic(self):
        model = self.manager.select_model(LLMTier.MAX, "anthropic")
        assert model == "claude-3-opus-20240229"

    def test_select_model_default_anthropic(self):
        model = self.manager.select_model(LLMTier.DEFAULT, "anthropic")
        assert model == "claude-3-haiku-20240307"

    def test_cost_per_1k_tokens_has_expected_models(self):
        expected_models = [
            "gpt-4o-mini", "gpt-4o",
            "claude-3-haiku-20240307", "claude-3-5-sonnet-20241022",
            "claude-3-opus-20240229",
        ]
        for model in expected_models:
            assert model in COST_PER_1K_TOKENS
            assert "input" in COST_PER_1K_TOKENS[model]
            assert "output" in COST_PER_1K_TOKENS[model]


class TestCostLevel:
    def test_cost_levels(self):
        assert CostLevel.NORMAL == "normal"
        assert CostLevel.WARNING == "warning"
        assert CostLevel.ALERT == "alert"
        assert CostLevel.CRITICAL == "critical"


class TestLLMTier:
    def test_llm_tiers(self):
        assert LLMTier.DEFAULT == "default"
        assert LLMTier.IMPORTANT == "important"
        assert LLMTier.MAX == "max"
