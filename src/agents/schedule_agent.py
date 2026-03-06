"""
Vsh-reflow - Schedule-Agent (Google Calendar連携・予定管理・リマインド)
Google Calendar API を使った予定の自動管理。
"""

import logging
import os
from datetime import datetime, timezone, timedelta
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class ScheduleAgent(BaseAgent):
    """スケジュール管理エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.PM, name="Schedule-Agent")
        self._google_api_key = os.environ.get("GOOGLE_API_KEY", "")
        self._calendar_id = os.environ.get("GOOGLE_CALENDAR_ID", "primary")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "list_events":
            return await self._list_events(task_code, payload)
        elif task_type == "create_event":
            return await self._create_event(task_code, payload)
        elif task_type == "suggest_schedule":
            return await self._suggest_schedule(task_code, payload)
        elif task_type == "daily_summary":
            return await self._daily_summary(task_code, payload)
        elif task_type == "reschedule":
            return await self._reschedule(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _list_events(self, task_code: str, payload: dict) -> dict:
        """予定一覧取得"""
        days = payload.get("days", 7)

        if not self._google_api_key:
            # LLMでサンプルスケジュール提示
            return {
                "success": True,
                "result": {
                    "events": [],
                    "note": "GOOGLE_API_KEY 未設定のためカレンダー接続不可",
                },
                "cost_yen": 0.0,
            }

        try:
            import httpx
            now = datetime.now(timezone.utc)
            time_min = now.isoformat()
            time_max = (now + timedelta(days=days)).isoformat()

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(
                    f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id}/events",
                    params={
                        "key": self._google_api_key,
                        "timeMin": time_min,
                        "timeMax": time_max,
                        "singleEvents": "true",
                        "orderBy": "startTime",
                        "maxResults": 50,
                    },
                )
                data = resp.json()

            events = []
            for item in data.get("items", []):
                events.append({
                    "id": item.get("id", ""),
                    "summary": item.get("summary", "(無題)"),
                    "start": item.get("start", {}).get("dateTime", item.get("start", {}).get("date", "")),
                    "end": item.get("end", {}).get("dateTime", item.get("end", {}).get("date", "")),
                    "location": item.get("location", ""),
                    "description": item.get("description", "")[:200],
                })

            return {
                "success": True,
                "result": {"events": events, "total": len(events), "period_days": days},
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"カレンダー取得エラー: {e}"}

    async def _create_event(self, task_code: str, payload: dict) -> dict:
        """予定作成"""
        title = payload.get("title", "")
        date = payload.get("date", "")
        start_time = payload.get("start_time", "10:00")
        end_time = payload.get("end_time", "11:00")
        description = payload.get("description", "")
        location = payload.get("location", "")

        if not self._google_api_key:
            return {"success": False, "error": "GOOGLE_API_KEY 未設定"}

        try:
            import httpx

            start_dt = f"{date}T{start_time}:00+09:00"
            end_dt = f"{date}T{end_time}:00+09:00"

            event = {
                "summary": title,
                "description": description,
                "location": location,
                "start": {"dateTime": start_dt, "timeZone": "Asia/Tokyo"},
                "end": {"dateTime": end_dt, "timeZone": "Asia/Tokyo"},
                "reminders": {
                    "useDefault": False,
                    "overrides": [
                        {"method": "popup", "minutes": 30},
                    ],
                },
            }

            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.post(
                    f"https://www.googleapis.com/calendar/v3/calendars/{self._calendar_id}/events",
                    params={"key": self._google_api_key},
                    json=event,
                )
                data = resp.json()

            return {
                "success": True,
                "result": {
                    "event_id": data.get("id", ""),
                    "title": title,
                    "start": start_dt,
                    "link": data.get("htmlLink", ""),
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {"success": False, "error": f"予定作成エラー: {e}"}

    async def _suggest_schedule(self, task_code: str, payload: dict) -> dict:
        """スケジュール提案"""
        task_description = payload.get("task", "")
        duration = payload.get("duration", "1時間")
        preferred_time = payload.get("preferred_time", "午前中")

        # 既存予定を取得
        events_result = await self._list_events(task_code, {"days": 7})
        existing = events_result.get("result", {}).get("events", [])

        result = await self.call_llm(
            prompt=f"""以下の条件でスケジュールを提案してください。

やること: {task_description}
所要時間: {duration}
希望時間帯: {preferred_time}

既存の予定:
{[f"- {e['summary']} ({e['start']})" for e in existing[:20]]}

以下を提案してください:
1. 最適な日時の候補3つ
2. 予定の前後にバッファを設けた提案
3. 生産性を考慮したアドバイス""",
            system_prompt="タイムマネジメントのコンサルタントとして、効率的なスケジュールを提案してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"suggestions": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _daily_summary(self, task_code: str, payload: dict) -> dict:
        """1日のスケジュールまとめ"""
        date = payload.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d"))

        events_result = await self._list_events(task_code, {"days": 1})
        events = events_result.get("result", {}).get("events", [])

        if not events:
            return {
                "success": True,
                "result": {
                    "summary": f"📅 {date}\n予定なし 🎉\n自由に使える1日です！",
                    "event_count": 0,
                },
                "cost_yen": 0.0,
            }

        result = await self.call_llm(
            prompt=f"""以下の1日のスケジュールをまとめてください。

日付: {date}
予定:
{chr(10).join([f"- {e['start']}: {e['summary']}" for e in events])}

以下を含めてください:
1. 📅 1日のタイムライン
2. 🎯 主要なタスク/会議
3. 💡 合間の空き時間でできること
4. ⚠️ 注意事項（移動時間等）""",
            system_prompt="秘書として、見やすく整理されたスケジュールサマリーを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"summary": result.get("text", ""), "event_count": len(events)},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _reschedule(self, task_code: str, payload: dict) -> dict:
        """予定変更提案"""
        reason = payload.get("reason", "")

        result = await self.call_llm(
            prompt=f"""予定の調整が必要になりました。

理由: {reason}

以下を提案してください:
1. 影響を受ける予定の特定
2. 代替日時の候補
3. 関係者への連絡テンプレート""",
            system_prompt="スケジュール調整の専門家として、スムーズなリスケジュールを提案してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"suggestions": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
schedule_agent = ScheduleAgent()
