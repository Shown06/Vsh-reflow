"""
Vsh-reflow - Browser-Agent (Web閲覧・データ収集)
Playwright でヘッドレスブラウザを操作。ページ閲覧、データ抽出、スクリーンショット。
"""

import logging
import os
import uuid
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)

SCREENSHOTS_DIR = os.environ.get("SCREENSHOTS_DIR", "/app/screenshots")


class BrowserAgent(BaseAgent):
    """Web閲覧・データ収集エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.GROWTH, name="Browser-Agent")

    def _ensure_dirs(self):
        try:
            os.makedirs(SCREENSHOTS_DIR, exist_ok=True)
        except OSError:
            pass

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "browse":
            return await self._browse_page(task_code, payload)
        elif task_type == "screenshot":
            return await self._take_screenshot(task_code, payload)
        elif task_type == "scrape":
            return await self._scrape_data(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _get_page_content(self, url: str) -> dict:
        """Playwrightでページ内容を取得"""
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(
                    user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                )
                page = await context.new_page()
                await page.goto(url, timeout=30000, wait_until="networkidle")

                title = await page.title()
                content = await page.content()

                # テキスト内容を抽出
                text_content = await page.evaluate("""
                    () => {
                        const body = document.body;
                        const clone = body.cloneNode(true);
                        const scripts = clone.querySelectorAll('script, style, noscript');
                        scripts.forEach(s => s.remove());
                        return clone.innerText.substring(0, 10000);
                    }
                """)

                await browser.close()
                return {
                    "title": title,
                    "text": text_content,
                    "html_length": len(content),
                    "url": url,
                }
        except ImportError:
            logger.warning("Playwright未インストール - httpxフォールバック")
            return await self._fallback_fetch(url)
        except Exception as e:
            logger.error(f"ブラウザエラー: {e}")
            return await self._fallback_fetch(url)

    async def _fallback_fetch(self, url: str) -> dict:
        """Playwright利用不可時のhttpxフォールバック"""
        try:
            import httpx
            async with httpx.AsyncClient(follow_redirects=True, timeout=30) as client:
                response = await client.get(url)
                text = response.text[:10000]
                return {
                    "title": url,
                    "text": text,
                    "html_length": len(response.text),
                    "url": url,
                }
        except Exception as e:
            return {"title": url, "text": f"取得エラー: {e}", "html_length": 0, "url": url}

    async def _browse_page(self, task_code: str, payload: dict) -> dict:
        """ページを閲覧して要約"""
        url = payload.get("url", "")
        if not url:
            return {"success": False, "error": "URLが指定されていません"}

        page_data = await self._get_page_content(url)

        # LLMでページ内容を要約
        result = await self.call_llm(
            prompt=f"""以下のWebページの内容を日本語で要約してください。

URL: {url}
タイトル: {page_data['title']}

ページ内容:
{page_data['text'][:5000]}

以下の形式で要約:
1. 📋 ページ概要（2-3文）
2. 🔑 主要ポイント（箇条書き3-5個）
3. 💡 重要な情報・データ""",
            system_prompt="Webページの内容を正確かつ簡潔に要約してください。",
            tier=LLMTier.DEFAULT,
            task_hint="research browse",
        )

        return {
            "success": True,
            "result": {
                "url": url,
                "title": page_data["title"],
                "summary": result.get("text", ""),
                "html_length": page_data["html_length"],
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _take_screenshot(self, task_code: str, payload: dict) -> dict:
        """ページのスクリーンショットを撮影"""
        self._ensure_dirs()
        url = payload.get("url", "")
        if not url:
            return {"success": False, "error": "URLが指定されていません"}

        filepath = None
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                page = await browser.new_page(viewport={"width": 1920, "height": 1080})
                await page.goto(url, timeout=30000, wait_until="networkidle")

                filename = f"{task_code}_{uuid.uuid4().hex[:8]}.png"
                filepath = os.path.join(SCREENSHOTS_DIR, filename)
                await page.screenshot(path=filepath, full_page=True)
                await browser.close()

        except Exception as e:
            logger.warning(f"スクリーンショットエラー: {e}")

        return {
            "success": True,
            "result": {
                "url": url,
                "screenshot_path": filepath or "Playwright未利用 - スクリーンショット不可",
            },
            "cost_yen": 0.0,
        }

    async def _scrape_data(self, task_code: str, payload: dict) -> dict:
        """ページからデータを抽出"""
        url = payload.get("url", "")
        target_items = payload.get("items", "")

        page_data = await self._get_page_content(url)

        result = await self.call_llm(
            prompt=f"""以下のWebページから指定されたデータを抽出してください。

URL: {url}
抽出対象: {target_items}

ページ内容:
{page_data['text'][:5000]}

JSON形式で抽出結果を返してください。""",
            system_prompt="正確にデータを抽出してください。見つからない場合はnullとしてください。",
            tier=LLMTier.DEFAULT,
            task_hint="research browse",
        )

        return {
            "success": True,
            "result": {
                "url": url,
                "extracted_data": result.get("text", ""),
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
browser_agent = BrowserAgent()
