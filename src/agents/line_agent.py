"""
Vsh-reflow - LINE-Agent (LINE公式アカウント連携・メッセージ配信)
LINE Messaging API を使った自動メッセージ配信・応答。
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class LINEAgent(BaseAgent):
    """LINE公式アカウント連携エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.PUB, name="LINE-Agent")
        self._channel_token = os.environ.get("LINE_CHANNEL_ACCESS_TOKEN", "")
        self._channel_secret = os.environ.get("LINE_CHANNEL_SECRET", "")
        self._api_base = "https://api.line.me/v2/bot"

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"Bearer {self._channel_token}",
            "Content-Type": "application/json",
        }

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "push_message":
            return await self._push_message(task_code, payload)
        elif task_type == "broadcast":
            return await self._broadcast(task_code, payload)
        elif task_type == "rich_menu":
            return await self._create_rich_menu(task_code, payload)
        elif task_type == "draft_message":
            return await self._draft_message(task_code, payload)
        elif task_type == "follower_stats":
            return await self._follower_stats(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _push_message(self, task_code: str, payload: dict) -> dict:
        """特定ユーザーにプッシュメッセージ送信"""
        user_id = payload.get("user_id", "")
        message = payload.get("message", "")
        message_type = payload.get("type", "text")

        if not self._channel_token:
            return {"success": False, "error": "LINE_CHANNEL_ACCESS_TOKEN が未設定"}

        messages = []
        if message_type == "text":
            messages.append({"type": "text", "text": message})
        elif message_type == "flex":
            messages.append(payload.get("flex_message", {"type": "text", "text": message}))

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._api_base}/message/push",
                    headers=self._get_headers(),
                    json={"to": user_id, "messages": messages},
                )
                if resp.status_code >= 400:
                    return {"success": False, "error": f"LINE API Error: {resp.text}"}

            return {
                "success": True,
                "result": {"user_id": user_id, "sent_at": datetime.now(timezone.utc).isoformat()},
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"LINE送信エラー: {e}"}

    async def _broadcast(self, task_code: str, payload: dict) -> dict:
        """全フォロワーにブロードキャスト送信"""
        message = payload.get("message", "")

        if not self._channel_token:
            return {"success": False, "error": "LINE_CHANNEL_ACCESS_TOKEN が未設定"}

        try:
            import httpx
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"{self._api_base}/message/broadcast",
                    headers=self._get_headers(),
                    json={"messages": [{"type": "text", "text": message}]},
                )
                if resp.status_code >= 400:
                    return {"success": False, "error": f"LINE API Error: {resp.text}"}

            return {
                "success": True,
                "result": {
                    "broadcast": True,
                    "message_preview": message[:100],
                    "sent_at": datetime.now(timezone.utc).isoformat(),
                },
                "cost_yen": 0.0,
                "require_approval": True,
            }
        except Exception as e:
            return {"success": False, "error": f"LINE配信エラー: {e}"}

    async def _create_rich_menu(self, task_code: str, payload: dict) -> dict:
        """リッチメニューテンプレート生成"""
        purpose = payload.get("purpose", "")

        result = await self.call_llm(
            prompt=f"""LINE公式アカウントのリッチメニューを設計してください。

目的: {purpose}

以下を含めてください:
1. リッチメニューのレイアウト（6分割推奨）
2. 各ボタンのラベルとアクション
3. 各ボタンのアイコン提案
4. カラースキーム
5. LINE Messaging APIのリッチメニュー作成用JSONサンプル""",
            system_prompt="LINEマーケティングの専門家として、ユーザーエンゲージメントを最大化するリッチメニューを設計してください。",
            tier=LLMTier.DEFAULT,
            task_hint="code json",
        )

        return {
            "success": True,
            "result": {"rich_menu_design": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _draft_message(self, task_code: str, payload: dict) -> dict:
        """LINE配信メッセージ生成"""
        purpose = payload.get("purpose", "")
        target = payload.get("target", "全フォロワー")
        tone = payload.get("tone", "親しみやすい")

        result = await self.call_llm(
            prompt=f"""LINE公式アカウントから配信するメッセージを作成してください。

目的: {purpose}
ターゲット: {target}
トーン: {tone}

LINEメッセージの制約:
- 1メッセージ500文字以内
- 絵文字を適切に使用
- 簡潔で読みやすい
- CTAを含める

3パターン作成してください。""",
            system_prompt="LINEマーケティングのプロとして、開封率とCTRが高いメッセージを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"draft_messages": result.get("text", ""), "purpose": purpose},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _follower_stats(self, task_code: str, payload: dict) -> dict:
        """フォロワー統計取得"""
        if not self._channel_token:
            return {"success": False, "error": "LINE_CHANNEL_ACCESS_TOKEN が未設定"}

        try:
            import httpx
            date = payload.get("date", datetime.now(timezone.utc).strftime("%Y%m%d"))
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"{self._api_base}/insight/followers",
                    headers=self._get_headers(),
                    params={"date": date},
                )
                data = resp.json()

            return {
                "success": True,
                "result": {
                    "followers": data.get("followers", 0),
                    "targeted_reaches": data.get("targetedReaches", 0),
                    "blocks": data.get("blocks", 0),
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"統計取得エラー: {e}"}


# エージェントインスタンス
line_agent = LINEAgent()
