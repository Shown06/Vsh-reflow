"""
Vsh-reflow - SEO-Agent (SEO分析・キーワード調査・メタタグ最適化)
サイトのSEOスコアリング、改善提案、キーワードリサーチを提供。
"""

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class SEOAgent(BaseAgent):
    """SEO分析・最適化エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.ANALYST, name="SEO-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "seo_audit":
            return await self._seo_audit(task_code, payload)
        elif task_type == "keyword_research":
            return await self._keyword_research(task_code, payload)
        elif task_type == "meta_optimize":
            return await self._meta_optimize(task_code, payload)
        elif task_type == "competitor_seo":
            return await self._competitor_seo(task_code, payload)
        elif task_type == "content_seo":
            return await self._content_seo(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _seo_audit(self, task_code: str, payload: dict) -> dict:
        """サイトSEO監査"""
        url = payload.get("url", "")

        # Browser-Agentでページを取得
        page_data = await self._fetch_page(url)

        result = await self.call_llm(
            prompt=f"""以下のWebサイトのSEO監査を実施してください。

URL: {url}
ページ内容:
{page_data[:5000]}

以下の項目を分析し、100点満点でスコアリングしてください:

1. **タイトルタグ** (10点) - 適切な長さ、キーワード含有
2. **メタディスクリプション** (10点) - 適切な長さ、魅力的な説明
3. **見出し構造** (10点) - H1の存在、見出し階層の適切性
4. **コンテンツ品質** (15点) - 文字数、キーワード密度、読みやすさ
5. **内部リンク** (10点) - リンク構造の適切性
6. **画像最適化** (10点) - alt属性、ファイルサイズ
7. **モバイル対応** (10点) - viewport設定
8. **ページ速度要因** (10点) - CSS/JS最適化
9. **構造化データ** (10点) - Schema.org対応
10. **技術的SEO** (5点) - canonical, robots等

各項目の詳細分析と改善アクションを提示してください。""",
            system_prompt="SEOスペシャリストとして、技術的かつ実用的なSEO監査レポートを作成してください。スコアは厳格に評価してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="analysis report",
        )

        return {
            "success": True,
            "result": {"audit_report": result.get("text", ""), "url": url},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _keyword_research(self, task_code: str, payload: dict) -> dict:
        """キーワードリサーチ"""
        topic = payload.get("topic", "")
        market = payload.get("market", "日本")

        result = await self.call_llm(
            prompt=f"""以下のトピックについて包括的なキーワードリサーチを実施してください。

トピック: {topic}
ターゲット市場: {market}

以下を含めてください:
1. **メインキーワード** (5-10個) - 検索ボリューム予測、競合度（高/中/低）
2. **ロングテールキーワード** (15-20個) - 具体的な検索クエリ
3. **関連キーワード** (10個) - LSIキーワード
4. **質問型キーワード** (10個) - 「〜とは」「〜のやり方」等
5. **トレンドキーワード** - 最近注目されているワード
6. **キーワードマッピング** - コンテンツ戦略への落とし込み
7. **推奨コンテンツタイトル** (5個) - クリック率を最大化するタイトル案""",
            system_prompt="SEOキーワードリサーチのプロフェッショナルとして、データ駆動の分析を行ってください。",
            tier=LLMTier.IMPORTANT,
            task_hint="analysis research",
        )

        return {
            "success": True,
            "result": {"keyword_report": result.get("text", ""), "topic": topic},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _meta_optimize(self, task_code: str, payload: dict) -> dict:
        """メタタグ最適化"""
        url = payload.get("url", "")
        target_keyword = payload.get("keyword", "")

        page_data = await self._fetch_page(url)

        result = await self.call_llm(
            prompt=f"""以下のページのメタタグを最適化してください。

URL: {url}
ターゲットキーワード: {target_keyword}
現在のページ:
{page_data[:3000]}

以下を生成してください:
1. 最適化された <title> タグ（30-60文字）
2. 最適化された <meta description>（120-160文字）
3. OGPタグ一式（og:title, og:description, og:image, og:type）
4. Twitter Cardタグ
5. 構造化データ（JSON-LD）のサンプル
6. canonical URL設定
7. HTMLヘッダーにコピペ可能な完全なコード""",
            system_prompt="SEO技術者として、検索エンジンに最適化されたメタタグを生成してください。",
            tier=LLMTier.DEFAULT,
            task_hint="code html",
        )

        return {
            "success": True,
            "result": {"meta_tags": result.get("text", ""), "keyword": target_keyword},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _competitor_seo(self, task_code: str, payload: dict) -> dict:
        """競合SEO分析"""
        competitors = payload.get("competitors", [])
        my_url = payload.get("my_url", "")

        result = await self.call_llm(
            prompt=f"""以下の競合サイトのSEO戦略を分析してください。

自社サイト: {my_url}
競合サイト: {', '.join(competitors) if competitors else '(未指定)'}

以下の観点で分析:
1. タイトル・メタディスクリプション比較
2. コンテンツ戦略の違い
3. バックリンク戦略の推測
4. キーワード戦略の推測
5. 自社が取るべき差別化戦略""",
            system_prompt="競合分析のプロフェッショナルとして、実行可能な戦略提案を行ってください。",
            tier=LLMTier.IMPORTANT,
            task_hint="analysis research",
        )

        return {
            "success": True,
            "result": {"competitor_analysis": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _content_seo(self, task_code: str, payload: dict) -> dict:
        """コンテンツSEO最適化"""
        content = payload.get("content", "")
        keyword = payload.get("keyword", "")

        result = await self.call_llm(
            prompt=f"""以下のコンテンツをSEO最適化してください。

ターゲットキーワード: {keyword}
現在のコンテンツ:
{content[:5000]}

改善後のコンテンツと、以下の分析を提供してください:
1. キーワード密度の調整
2. 見出し構造の最適化
3. 内部リンクの提案
4. 読みやすさの改善
5. E-E-A-T（経験、専門性、権威性、信頼性）の強化""",
            system_prompt="コンテンツSEOのエキスパートとして、検索順位向上に直結する改善を行ってください。",
            tier=LLMTier.DEFAULT,
            task_hint="analysis",
        )

        return {
            "success": True,
            "result": {"optimized_content": result.get("text", ""), "keyword": keyword},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _fetch_page(self, url: str) -> str:
        """ページコンテンツを取得"""
        if not url:
            return ""
        try:
            import httpx
            async with httpx.AsyncClient(timeout=15) as client:
                resp = await client.get(url, follow_redirects=True)
                return resp.text[:10000]
        except Exception as e:
            return f"(ページ取得エラー: {e})"


# エージェントインスタンス
seo_agent = SEOAgent()
