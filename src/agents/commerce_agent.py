"""
Vsh-reflow - Commerce-Agent (EC・物販サポート)
メルカリ等の出品テンプレート自動生成（安全方式）。相場調査。
"""

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class CommerceAgent(BaseAgent):
    """EC・物販サポートエージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.CONTENT, name="Commerce-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "listing_template":
            return await self._create_listing(task_code, payload)
        elif task_type == "pricing_research":
            return await self._research_pricing(task_code, payload)
        elif task_type == "listing_optimize":
            return await self._optimize_listing(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _create_listing(self, task_code: str, payload: dict) -> dict:
        """出品テンプレート生成"""
        product_name = payload.get("product_name", "")
        description = payload.get("description", "")
        platform = payload.get("platform", "メルカリ")

        # プラットフォーム別制約
        platform_rules = {
            "メルカリ": {
                "title_max": 40,
                "desc_max": 1000,
                "tips": "送料込み推奨、即購入可推奨、フォロー割引アピール",
            },
            "ラクマ": {
                "title_max": 40,
                "desc_max": 1000,
                "tips": "楽天ポイント使用可アピール",
            },
            "PayPayフリマ": {
                "title_max": 65,
                "desc_max": 1000,
                "tips": "価格交渉機能あり、送料無料推奨",
            },
        }

        rules = platform_rules.get(platform, platform_rules["メルカリ"])

        result = await self.call_llm(
            prompt=f"""以下の商品の{platform}出品テンプレートを作成してください。

商品名: {product_name}
説明: {description}
プラットフォーム: {platform}

制約:
- タイトル: 最大{rules['title_max']}文字
- 説明文: 最大{rules['desc_max']}文字
- ヒント: {rules['tips']}

以下を出力してください:

【タイトル】
魅力的で検索されやすいタイトル

【説明文】
構造化された説明文:
- 商品の状態
- サイズ・スペック
- 購入時期（仮）
- 発送方法

【カテゴリ推奨】
最適なカテゴリパス

【推奨価格帯】
相場に基づく推奨価格（低・中・高の3パターン）

【ハッシュタグ】
検索されやすいタグ5-10個

【写真の撮り方アドバイス】
商品写真を魅力的に撮るためのアドバイス""",
            system_prompt=f"あなたは{platform}のトップセラーです。売れる出品テンプレートを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "listing_template": result.get("text", ""),
                "product_name": product_name,
                "platform": platform,
                "note": "💡 このテンプレートをコピーしてメルカリに手動で出品してください",
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _research_pricing(self, task_code: str, payload: dict) -> dict:
        """相場調査（Browser-Agent連携も可能）"""
        product_name = payload.get("product_name", "")

        # Browser-Agentにメルカリ検索を依頼
        try:
            from src.workers.celery_app import dispatch_agent_task
            dispatch_agent_task.delay(
                "browser", task_code, "scrape",
                {
                    "url": f"https://www.mercari.com/jp/search/?keyword={product_name}",
                    "items": "商品名、価格、状態",
                }
            )
        except Exception as e:
            logger.debug(f"Browser-Agent連携スキップ: {e}")

        # LLMで相場分析
        result = await self.call_llm(
            prompt=f"""以下の商品のフリマアプリでの相場を分析してください。

商品名: {product_name}

以下を推定してください:
1. 新品の相場価格帯
2. 中古（美品）の相場価格帯
3. 中古（良品）の相場価格帯
4. 売れやすい価格設定のアドバイス
5. 値下げ交渉を想定した初期価格の推奨""",
            system_prompt="フリマアプリの相場に詳しいアドバイザーとして回答してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "pricing_analysis": result.get("text", ""),
                "product_name": product_name,
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _optimize_listing(self, task_code: str, payload: dict) -> dict:
        """既存出品の最適化提案"""
        current_listing = payload.get("current_listing", "")

        result = await self.call_llm(
            prompt=f"""以下のフリマアプリ出品を最適化してください。

現在の出品内容:
{current_listing}

以下の観点で改善提案してください:
1. タイトルの改善（検索ヒット率向上）
2. 説明文の改善（購買意欲向上）
3. 価格見直し提案
4. 写真の改善アドバイス""",
            system_prompt="フリマアプリのコンバージョン率を上げる専門家として回答してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"optimization": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
commerce_agent = CommerceAgent()
