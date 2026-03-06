"""
Vsh-reflow - SaaS-Agent (SaaS管理画面のブラウザ自動操作)
Playwright で SaaS の管理画面にログインし、自動操作を実行。
Google Sheets/Docs/Analytics, Shopify, Notion 等に対応。
"""

import logging
import os
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


# SaaS サービス定義
SAAS_SERVICES = {
    "google_sheets": {
        "name": "Google Sheets",
        "api_available": True,
        "api_base": "https://sheets.googleapis.com/v4/spreadsheets",
    },
    "google_analytics": {
        "name": "Google Analytics",
        "api_available": True,
        "api_base": "https://analyticsdata.googleapis.com/v1beta",
    },
    "notion": {
        "name": "Notion",
        "api_available": True,
        "api_base": "https://api.notion.com/v1",
    },
    "shopify": {
        "name": "Shopify",
        "api_available": True,
        "api_base": None,  # store-specific
    },
    "slack": {
        "name": "Slack",
        "api_available": True,
        "api_base": "https://slack.com/api",
    },
    "generic": {
        "name": "汎用ブラウザ操作",
        "api_available": False,
    },
}


class SaaSAgent(BaseAgent):
    """SaaS管理画面操作エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.ANALYST, name="SaaS-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "google_sheets":
            return await self._operate_google_sheets(task_code, payload)
        elif task_type == "notion":
            return await self._operate_notion(task_code, payload)
        elif task_type == "slack_message":
            return await self._send_slack_message(task_code, payload)
        elif task_type == "google_analytics":
            return await self._get_analytics(task_code, payload)
        elif task_type == "saas_browse":
            return await self._browse_saas(task_code, payload)
        elif task_type == "shopify":
            return await self._operate_shopify(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    # ============================================
    # Google Sheets API
    # ============================================
    async def _operate_google_sheets(self, task_code: str, payload: dict) -> dict:
        """Google Sheets 操作"""
        action = payload.get("action", "read")  # read, write, create
        spreadsheet_id = payload.get("spreadsheet_id", "")
        sheet_range = payload.get("range", "Sheet1!A1:Z100")
        values = payload.get("values", [])
        api_key = os.environ.get("GOOGLE_API_KEY", "")
        service_account = os.environ.get("GOOGLE_SERVICE_ACCOUNT_KEY", "")

        if not api_key and not service_account:
            return {"success": False, "error": "GOOGLE_API_KEY または GOOGLE_SERVICE_ACCOUNT_KEY が未設定"}

        try:
            import httpx
            headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}

            if action == "read":
                async with httpx.AsyncClient(timeout=30) as client:
                    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_range}"
                    resp = await client.get(url, headers=headers, params={"key": api_key})
                    data = resp.json()

                return {
                    "success": True,
                    "result": {
                        "values": data.get("values", []),
                        "range": data.get("range", ""),
                    },
                    "cost_yen": 0.0,
                }

            elif action == "write":
                async with httpx.AsyncClient(timeout=30) as client:
                    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{sheet_range}"
                    resp = await client.put(url, headers=headers, params={
                        "key": api_key,
                        "valueInputOption": "USER_ENTERED",
                    }, json={"values": values})
                    data = resp.json()

                return {
                    "success": True,
                    "result": {
                        "updated_cells": data.get("updatedCells", 0),
                        "updated_range": data.get("updatedRange", ""),
                    },
                    "cost_yen": 0.0,
                }

        except Exception as e:
            return {"success": False, "error": f"Google Sheets操作エラー: {e}"}

    # ============================================
    # Notion API
    # ============================================
    async def _operate_notion(self, task_code: str, payload: dict) -> dict:
        """Notion 操作"""
        action = payload.get("action", "search")  # search, create_page, update_page
        notion_token = os.environ.get("NOTION_API_KEY", "")

        if not notion_token:
            return {"success": False, "error": "NOTION_API_KEY が未設定"}

        headers = {
            "Authorization": f"Bearer {notion_token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        }

        try:
            import httpx

            if action == "search":
                query = payload.get("query", "")
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.notion.com/v1/search",
                        headers=headers,
                        json={"query": query},
                    )
                    data = resp.json()

                pages = []
                for result in data.get("results", [])[:10]:
                    title = ""
                    if result.get("properties", {}).get("title", {}).get("title"):
                        title = result["properties"]["title"]["title"][0].get("plain_text", "")
                    elif result.get("properties", {}).get("Name", {}).get("title"):
                        title = result["properties"]["Name"]["title"][0].get("plain_text", "")
                    pages.append({
                        "id": result.get("id", ""),
                        "title": title or result.get("url", ""),
                        "type": result.get("object", ""),
                        "url": result.get("url", ""),
                    })

                return {
                    "success": True,
                    "result": {"pages": pages, "count": len(pages)},
                    "cost_yen": 0.0,
                }

            elif action == "create_page":
                parent_id = payload.get("parent_id", "")
                title = payload.get("title", "")
                content = payload.get("content", "")

                page_data = {
                    "parent": {"database_id": parent_id},
                    "properties": {
                        "Name": {"title": [{"text": {"content": title}}]},
                    },
                    "children": [
                        {
                            "object": "block",
                            "type": "paragraph",
                            "paragraph": {
                                "rich_text": [{"type": "text", "text": {"content": content}}]
                            },
                        }
                    ],
                }

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        "https://api.notion.com/v1/pages",
                        headers=headers,
                        json=page_data,
                    )
                    data = resp.json()

                return {
                    "success": True,
                    "result": {
                        "page_id": data.get("id", ""),
                        "url": data.get("url", ""),
                    },
                    "cost_yen": 0.0,
                }

        except Exception as e:
            return {"success": False, "error": f"Notion操作エラー: {e}"}

    # ============================================
    # Slack API
    # ============================================
    async def _send_slack_message(self, task_code: str, payload: dict) -> dict:
        """Slackメッセージ送信"""
        channel = payload.get("channel", "")
        text = payload.get("text", "")
        slack_token = os.environ.get("SLACK_BOT_TOKEN", "")

        if not slack_token:
            return {"success": False, "error": "SLACK_BOT_TOKEN が未設定"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    "https://slack.com/api/chat.postMessage",
                    headers={"Authorization": f"Bearer {slack_token}"},
                    json={"channel": channel, "text": text},
                )
                data = resp.json()

            if not data.get("ok"):
                return {"success": False, "error": f"Slackエラー: {data.get('error', '')}"}

            return {
                "success": True,
                "result": {
                    "channel": channel,
                    "ts": data.get("ts", ""),
                    "message": "Slack送信完了",
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"Slack送信エラー: {e}"}

    # ============================================
    # Google Analytics API
    # ============================================
    async def _get_analytics(self, task_code: str, payload: dict) -> dict:
        """Google Analyticsのデータ取得・分析"""
        property_id = payload.get("property_id", "")
        period = payload.get("period", "7")  # 日数
        api_key = os.environ.get("GOOGLE_API_KEY", "")

        if not api_key:
            # LLMでダミーレポート生成
            result = await self.call_llm(
                prompt=f"Google Analyticsのサンプルレポートを生成してください。期間: {period}日間",
                system_prompt="デジタルマーケティングの分析レポートを作成してください。",
                tier=LLMTier.DEFAULT,
                task_hint="analysis report",
            )
            return {
                "success": True,
                "result": {"report": result.get("text", ""), "note": "API未設定のためサンプルデータ"},
                "cost_yen": result.get("cost_yen", 0.0),
            }

        # 実際のGA4 Data API呼び出し
        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://analyticsdata.googleapis.com/v1beta/properties/{property_id}:runReport",
                    headers={"Authorization": f"Bearer {api_key}"},
                    json={
                        "dateRanges": [{"startDate": f"{period}daysAgo", "endDate": "today"}],
                        "metrics": [
                            {"name": "activeUsers"},
                            {"name": "sessions"},
                            {"name": "screenPageViews"},
                        ],
                        "dimensions": [{"name": "date"}],
                    },
                )
                data = resp.json()

            # LLMで分析
            analysis = await self.call_llm(
                prompt=f"以下のGoogle Analyticsデータを分析してください:\n{data}",
                system_prompt="デジタルマーケティングアナリストとしてデータを解釈し、アクション推奨を含めてください。",
                tier=LLMTier.DEFAULT,
                task_hint="analysis report",
            )

            return {
                "success": True,
                "result": {
                    "raw_data": data,
                    "analysis": analysis.get("text", ""),
                },
                "cost_yen": analysis.get("cost_yen", 0.0),
            }
        except Exception as e:
            return {"success": False, "error": f"GA4取得エラー: {e}"}

    # ============================================
    # 汎用ブラウザ操作（Playwright）
    # ============================================
    async def _browse_saas(self, task_code: str, payload: dict) -> dict:
        """汎用SaaS管理画面のブラウザ操作"""
        url = payload.get("url", "")
        actions = payload.get("actions", [])
        login_url = payload.get("login_url", "")
        username = payload.get("username", "")
        password = payload.get("password", "")

        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context()
                page = await context.new_page()

                # ログイン処理
                if login_url and username:
                    await page.goto(login_url, wait_until="networkidle")
                    # 汎用ログインフォーム操作
                    try:
                        await page.fill('input[type="email"], input[name="email"], input[name="username"]', username)
                        await page.fill('input[type="password"]', password)
                        await page.click('button[type="submit"], input[type="submit"]')
                        await page.wait_for_load_state("networkidle")
                    except Exception as e:
                        logger.warning(f"ログインフォーム操作失敗: {e}")

                # 対象ページに移動
                await page.goto(url, wait_until="networkidle")

                # アクション実行
                results = []
                for action in actions:
                    act_type = action.get("type", "")
                    selector = action.get("selector", "")
                    value = action.get("value", "")

                    try:
                        if act_type == "click":
                            await page.click(selector)
                        elif act_type == "fill":
                            await page.fill(selector, value)
                        elif act_type == "select":
                            await page.select_option(selector, value)
                        elif act_type == "screenshot":
                            path = f"/app/screenshots/saas_{task_code}.png"
                            await page.screenshot(path=path)
                            results.append({"action": "screenshot", "path": path})
                        elif act_type == "extract":
                            text = await page.text_content(selector)
                            results.append({"action": "extract", "selector": selector, "text": text})

                        await page.wait_for_timeout(1000)
                    except Exception as e:
                        results.append({"action": act_type, "error": str(e)})

                # ページの内容を取得
                page_text = await page.evaluate("() => document.body.innerText.substring(0, 5000)")
                await browser.close()

            return {
                "success": True,
                "result": {
                    "url": url,
                    "actions_results": results,
                    "page_content_preview": page_text[:1000],
                },
                "cost_yen": 0.0,
            }

        except ImportError:
            return {"success": False, "error": "Playwright未インストール"}
        except Exception as e:
            return {"success": False, "error": f"ブラウザ操作エラー: {e}"}

    # ============================================
    # Shopify API
    # ============================================
    async def _operate_shopify(self, task_code: str, payload: dict) -> dict:
        """Shopify Admin API 操作"""
        action = payload.get("action", "list_products")
        shop_url = os.environ.get("SHOPIFY_SHOP_URL", "")
        access_token = os.environ.get("SHOPIFY_ACCESS_TOKEN", "")

        if not shop_url or not access_token:
            return {"success": False, "error": "SHOPIFY_SHOP_URL/SHOPIFY_ACCESS_TOKEN が未設定"}

        headers = {
            "X-Shopify-Access-Token": access_token,
            "Content-Type": "application/json",
        }

        try:
            import httpx

            if action == "list_products":
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.get(
                        f"https://{shop_url}/admin/api/2024-01/products.json",
                        headers=headers,
                    )
                    data = resp.json()

                products = []
                for p in data.get("products", [])[:20]:
                    products.append({
                        "id": p.get("id"),
                        "title": p.get("title"),
                        "status": p.get("status"),
                        "price": p.get("variants", [{}])[0].get("price", "0") if p.get("variants") else "0",
                    })

                return {
                    "success": True,
                    "result": {"products": products, "count": len(products)},
                    "cost_yen": 0.0,
                }

            elif action == "create_product":
                title = payload.get("title", "")
                description = payload.get("description", "")
                price = payload.get("price", "0")

                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        f"https://{shop_url}/admin/api/2024-01/products.json",
                        headers=headers,
                        json={
                            "product": {
                                "title": title,
                                "body_html": description,
                                "variants": [{"price": price}],
                            }
                        },
                    )
                    data = resp.json()

                return {
                    "success": True,
                    "result": {
                        "product_id": data.get("product", {}).get("id"),
                        "title": title,
                    },
                    "cost_yen": 0.0,
                }

        except Exception as e:
            return {"success": False, "error": f"Shopify操作エラー: {e}"}


# エージェントインスタンス
saas_agent = SaaSAgent()
