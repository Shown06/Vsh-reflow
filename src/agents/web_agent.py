"""
Vsh-reflow - Web-Agent (Webサイト構築・デプロイ)
ホームページ・LP・Webアプリの生成。Dev-Agent・Deploy-Agentと連携。
"""

import logging
import os
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/app/projects")


class WebAgent(BaseAgent):
    """Webサイト構築エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.CONTENT, name="Web-Agent")

    def _ensure_dirs(self, project_dir: str):
        try:
            os.makedirs(project_dir, exist_ok=True)
        except OSError:
            pass

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "website_generation":
            return await self._generate_website(task_code, payload)
        elif task_type == "landing_page":
            return await self._generate_landing_page(task_code, payload)
        elif task_type == "page_edit":
            return await self._edit_page(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _generate_website(self, task_code: str, payload: dict) -> dict:
        """Webサイト一式を生成"""
        description = payload.get("description", "")
        total_cost = 0.0

        # Step 1: サイト設計
        plan_result = await self.call_llm(
            prompt=f"""以下の説明に基づいてWebサイトの設計書を作成してください。

説明: {description}

以下を含めてください:
1. ページ構成（どのページが必要か）
2. 各ページの主要セクション
3. カラースキーム（hex値）
4. フォント推奨
5. レスポンシブ対応方針""",
            system_prompt="あなたはUX/UIデザイナーです。モダンで美しいWebサイトを設計してください。",
            tier=LLMTier.DEFAULT,
            task_hint="code html css",
        )
        total_cost += plan_result.get("cost_yen", 0.0)

        # Step 2: HTML生成
        html_result = await self.call_llm(
            prompt=f"""以下の設計に基づいて、完全に動作するHTML/CSS/JSファイルを生成してください。

サイト説明: {description}
設計書:
{plan_result.get('text', '')}

要件:
- シングルページまたはマルチページ（適切な方を選択）
- レスポンシブ対応（モバイル/タブレット/デスクトップ）
- モダンなデザイン（グラデーション、影、アニメーション）
- SEO基本対応（meta tags, semantic HTML）
- 日本語対応

HTMLファイルの内容を出力してください。CSSはインラインまたは<style>タグ内に含めてください。""",
            system_prompt="フロントエンド開発のエキスパートとして、美しく高品質なWebサイトを構築してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="code html css js",
            max_tokens=4000,
        )
        total_cost += html_result.get("cost_yen", 0.0)

        # ファイル保存
        project_dir = os.path.join(PROJECTS_DIR, task_code)
        self._ensure_dirs(project_dir)

        html_code = self._extract_html(html_result.get("text", ""))
        filepath = os.path.join(project_dir, "index.html")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_code)
        except Exception:
            filepath = "保存不可（Docker外実行中）"

        # Deploy-Agentにデプロイを指示
        try:
            from src.workers.celery_app import dispatch_agent_task
            dispatch_agent_task.delay(
                "deploy", task_code, "deploy_static",
                {"project_dir": project_dir, "task_code": task_code}
            )
        except Exception as e:
            logger.debug(f"Deploy指示スキップ: {e}")

        return {
            "success": True,
            "result": {
                "plan": plan_result.get("text", ""),
                "html": html_code[:1000] + "..." if len(html_code) > 1000 else html_code,
                "filepath": filepath,
                "project_dir": project_dir,
            },
            "cost_yen": total_cost,
            "require_approval": True,
        }

    async def _generate_landing_page(self, task_code: str, payload: dict) -> dict:
        """ランディングページを生成"""
        theme = payload.get("theme", "")
        target_audience = payload.get("target", "一般")

        result = await self.call_llm(
            prompt=f"""以下のテーマでランディングページを生成してください。

テーマ: {theme}
ターゲット: {target_audience}

必須セクション:
1. ヒーローセクション（キャッチコピー + CTA）
2. 特徴・メリット（3-4つ）
3. 導入事例・実績
4. FAQ
5. CTA（お問い合わせ or 購入ボタン）

完全なHTMLファイルを生成してください。
モダンで美しいデザイン、レスポンシブ対応、アニメーション付き。""",
            system_prompt="コンバージョン率が高いLPを作成するプロフェッショナルです。",
            tier=LLMTier.IMPORTANT,
            task_hint="code html css landing",
            max_tokens=4000,
        )

        html_code = self._extract_html(result.get("text", ""))

        project_dir = os.path.join(PROJECTS_DIR, f"{task_code}_lp")
        self._ensure_dirs(project_dir)
        filepath = os.path.join(project_dir, "index.html")
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(html_code)
        except Exception:
            filepath = "保存不可"

        return {
            "success": True,
            "result": {
                "html": html_code[:1000] + "..." if len(html_code) > 1000 else html_code,
                "filepath": filepath,
            },
            "cost_yen": result.get("cost_yen", 0.0),
            "require_approval": True,
        }

    async def _edit_page(self, task_code: str, payload: dict) -> dict:
        """既存ページを修正"""
        filepath = payload.get("filepath", "")
        edit_instruction = payload.get("instruction", "")

        # ファイル読み込み
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                current_html = f.read()
        except Exception as e:
            return {"success": False, "error": f"ファイル読み込みエラー: {e}"}

        result = await self.call_llm(
            prompt=f"""以下のHTMLファイルを修正してください。

修正指示: {edit_instruction}

現在のHTML:
{current_html[:5000]}

修正後のHTMLファイル全体を出力してください。""",
            system_prompt="Web開発者として、指示に正確に従ってコードを修正してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="code html fix",
            max_tokens=4000,
        )

        edited_html = self._extract_html(result.get("text", ""))
        try:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write(edited_html)
        except Exception:
            pass

        return {
            "success": True,
            "result": {"filepath": filepath, "edited": True},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    def _extract_html(self, text: str) -> str:
        """LLM出力からHTMLコードを抽出"""
        import re
        match = re.search(r"```html\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        match = re.search(r"```\n(.*?)```", text, re.DOTALL)
        if match:
            return match.group(1).strip()
        if "<html" in text.lower() or "<!doctype" in text.lower():
            return text.strip()
        return text.strip()


# エージェントインスタンス
web_agent = WebAgent()
