"""
Vsh-reflow - Growth-Agent (グロースマーケター)
トレンド・競合リサーチ、企画立案。
"""

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class GrowthAgent(BaseAgent):
    """グロースマーケターエージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.GROWTH, name="Growth-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "idea_generation":
            return await self._generate_ideas(task_code, payload)
        elif task_type == "research":
            return await self._conduct_research(task_code, payload)
        elif task_type == "meeting_research":
            return await self._meeting_research(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _generate_ideas(self, task_code: str, payload: dict) -> dict:
        """アイデア出し・企画立案"""
        theme = payload.get("theme", "")

        result = await self.call_llm(
            prompt=f"""あなたはデジタルマーケティングのグロースハッカーです。
以下のテーマで、SNSマーケティングのアイデアを5つ提案してください。

テーマ: {theme}

各アイデアには以下を含めてください:
1. アイデア名
2. 概要（50文字以内）
3. ターゲットSNSプラットフォーム
4. 期待効果
5. 必要リソース（コンテンツ種別・量）

最新のトレンドとバイラル要素を考慮してください。""",
            system_prompt="あなたは実績のあるグロースマーケターです。具体的で実行可能なアイデアを提案してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"ideas": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _conduct_research(self, task_code: str, payload: dict) -> dict:
        """競合・トレンド調査"""
        keyword = payload.get("keyword", "")

        result = await self.call_llm(
            prompt=f"""あなたはマーケティングリサーチャーです。
以下のキーワードで競合・トレンド調査を行ってください。

キーワード: {keyword}

以下の項目をレポートしてください:
1. 【市場トレンド】現在の市場動向・話題
2. 【競合分析】主要競合の戦略・コンテンツ傾向
3. 【バズコンテンツ】最近バズっている関連コンテンツ（構造・要因分析）
4. 【推奨ハッシュタグ】効果的なハッシュタグ候補10個
5. 【最適投稿タイミング】プラットフォーム別の推奨時間帯
6. 【差別化ポイント】競合と差別化できる角度3つ

データに基づいた具体的な分析をお願いします。""",
            system_prompt="あなたは経験豊富なマーケティングアナリストです。定量的かつ実用的なレポートを作成してください。",
            tier=LLMTier.IMPORTANT,
        )

        return {
            "success": True,
            "result": {"research_report": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _meeting_research(self, task_code: str, payload: dict) -> dict:
        """会議用トレンド・競合データ提供"""
        topic = payload.get("topic", "")

        result = await self.call_llm(
            prompt=f"""AI社内会議のため、以下のテーマに関するトレンド・競合データを提供してください。

テーマ: {topic}

簡潔に以下を報告してください:
- 最新トレンド3つ
- 競合の動向（主要3社）
- おすすめの方向性""",
            system_prompt="簡潔で要点を押さえた報告をしてください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"research": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
growth_agent = GrowthAgent()
