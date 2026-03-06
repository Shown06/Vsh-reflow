"""
Vsh-reflow - Content-Agent (コンテンツクリエイター)
テキスト・コピー・スクリプト生成。プラットフォーム別制約対応。3案提出機能。
"""

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)

# プラットフォーム別制約
PLATFORM_CONSTRAINTS = {
    "X": {"max_chars": 280, "tone": "casual_professional", "features": "ハッシュタグ、メンション、絵文字"},
    "Instagram": {"max_chars": 2200, "tone": "visual_storytelling", "features": "ハッシュタグ30個以内、キャプション、CTA"},
    "TikTok": {"max_chars": 300, "tone": "trendy_casual", "features": "ハッシュタグ、BGM提案、フック構造"},
    "LinkedIn": {"max_chars": 3000, "tone": "professional", "features": "要点箇条書き、業界用語"},
    "Facebook": {"max_chars": 63206, "tone": "friendly_informative", "features": "リンク、画像、CTA"},
}


class ContentAgent(BaseAgent):
    """コンテンツクリエイターエージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.CONTENT, name="Content-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "content_draft":
            return await self._create_draft(task_code, payload)
        elif task_type == "meeting_content":
            return await self._meeting_content(task_code, payload)
        elif task_type == "content_generation":
            return await self._generate_content(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _create_draft(self, task_code: str, payload: dict) -> dict:
        """投稿下書き生成"""
        platform = payload.get("platform", "X")
        theme = payload.get("theme", "")
        constraints = PLATFORM_CONSTRAINTS.get(platform, PLATFORM_CONSTRAINTS["X"])

        result = await self.call_llm(
            prompt=f"""あなたはSNSコンテンツクリエイターです。
以下の条件で投稿の下書きを3案作成してください。

プラットフォーム: {platform}
テーマ: {theme}
文字数上限: {constraints['max_chars']}文字
トーン: {constraints['tone']}
使用可能な機能: {constraints['features']}

各案について:
- 投稿本文
- ハッシュタグ
- 最適な投稿時間帯（推奨）
- 画像/動画の推奨（あれば）

3案それぞれ異なるアプローチで作成してください:
案1: バズ狙い（インパクト重視）
案2: エンゲージメント重視（質問・議論誘導）
案3: 情報提供型（有益な内容共有）""",
            system_prompt=f"あなたは{platform}のトップクリエイターです。エンゲージメントの高い投稿を作成してください。",
            tier=LLMTier.IMPORTANT,
        )

        return {
            "success": True,
            "result": {
                "drafts": result.get("text", ""),
                "platform": platform,
                "theme": theme,
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _meeting_content(self, task_code: str, payload: dict) -> dict:
        """会議用コンテンツ案3案提出"""
        topic = payload.get("topic", "")
        num_proposals = payload.get("num_proposals", 3)

        result = await self.call_llm(
            prompt=f"""AI社内会議のため、以下のテーマでコンテンツ案を{num_proposals}案提出してください。

テーマ: {topic}

各案の形式:
- 案名
- コンセプト（30文字以内）
- 対象プラットフォーム
- 投稿文（プラットフォームに適した長さ）
- ビジュアルイメージ提案
- 予想エンゲージメント""",
            system_prompt="クリエイティブで差別化されたコンテンツ案を提案してください。",
            tier=LLMTier.IMPORTANT,
        )

        return {
            "success": True,
            "result": {"content_proposals": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _generate_content(self, task_code: str, payload: dict) -> dict:
        """汎用コンテンツ生成"""
        context = payload.get("context", "")
        constraints = payload.get("constraints", {})

        platform = constraints.get("platform", "X")
        tone = constraints.get("tone", "casual_professional")
        max_length = constraints.get("length", "max_280chars")

        result = await self.call_llm(
            prompt=f"""以下のコンテキストに基づいてコンテンツを生成してください。

コンテキスト: {context}
プラットフォーム: {platform}
トーン: {tone}
長さ制約: {max_length}

魅力的でエンゲージメントの高いコンテンツを作成してください。""",
            system_prompt="プロのコンテンツクリエイターとして、効果的なコンテンツを生成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"content": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
content_agent = ContentAgent()
