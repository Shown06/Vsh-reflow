"""
Vsh-reflow - CRM-Agent (顧客管理・フォローアップ・リード管理)
顧客情報の管理、自動フォローアップ、リードスコアリングを提供。
"""

import logging
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class CRMAgent(BaseAgent):
    """CRM (顧客関係管理) エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.GROWTH, name="CRM-Agent")
        self._crm_dir = os.environ.get("CRM_DATA_DIR", "/app/crm_data")
        try:
            os.makedirs(self._crm_dir, exist_ok=True)
        except OSError:
            self._crm_dir = "/tmp/crm_data"
            os.makedirs(self._crm_dir, exist_ok=True)

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "add_contact":
            return await self._add_contact(task_code, payload)
        elif task_type == "list_contacts":
            return await self._list_contacts(task_code, payload)
        elif task_type == "follow_up":
            return await self._generate_follow_up(task_code, payload)
        elif task_type == "lead_score":
            return await self._lead_scoring(task_code, payload)
        elif task_type == "customer_analysis":
            return await self._customer_analysis(task_code, payload)
        elif task_type == "pipeline":
            return await self._pipeline_report(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    def _get_db_path(self) -> str:
        return os.path.join(self._crm_dir, "contacts.json")

    def _load_contacts(self) -> list:
        path = self._get_db_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return []

    def _save_contacts(self, contacts: list):
        path = self._get_db_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(contacts, f, ensure_ascii=False, indent=2)

    async def _add_contact(self, task_code: str, payload: dict) -> dict:
        """顧客追加"""
        contact = {
            "id": f"C-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "name": payload.get("name", ""),
            "email": payload.get("email", ""),
            "phone": payload.get("phone", ""),
            "company": payload.get("company", ""),
            "source": payload.get("source", "direct"),
            "status": payload.get("status", "lead"),
            "notes": payload.get("notes", ""),
            "tags": payload.get("tags", []),
            "score": 0,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "last_contact": datetime.now(timezone.utc).isoformat(),
            "interactions": [],
        }

        contacts = self._load_contacts()
        contacts.append(contact)
        self._save_contacts(contacts)

        return {
            "success": True,
            "result": {
                "contact_id": contact["id"],
                "name": contact["name"],
                "status": contact["status"],
            },
            "cost_yen": 0.0,
        }

    async def _list_contacts(self, task_code: str, payload: dict) -> dict:
        """顧客一覧"""
        contacts = self._load_contacts()
        status_filter = payload.get("status", None)
        tag_filter = payload.get("tag", None)

        if status_filter:
            contacts = [c for c in contacts if c.get("status") == status_filter]
        if tag_filter:
            contacts = [c for c in contacts if tag_filter in c.get("tags", [])]

        summary = []
        for c in contacts[:50]:
            summary.append({
                "id": c["id"],
                "name": c["name"],
                "email": c.get("email", ""),
                "status": c.get("status", ""),
                "score": c.get("score", 0),
                "tags": c.get("tags", []),
            })

        return {
            "success": True,
            "result": {"contacts": summary, "total": len(contacts)},
            "cost_yen": 0.0,
        }

    async def _generate_follow_up(self, task_code: str, payload: dict) -> dict:
        """フォローアップメッセージ生成"""
        contact_id = payload.get("contact_id", "")
        contacts = self._load_contacts()
        contact = next((c for c in contacts if c["id"] == contact_id), None)

        if not contact:
            return {"success": False, "error": f"顧客ID {contact_id} が見つかりません"}

        result = await self.call_llm(
            prompt=f"""以下の顧客へのフォローアップメッセージを作成してください。

顧客情報:
- 名前: {contact['name']}
- 会社: {contact.get('company', '(個人)')}
- ステータス: {contact.get('status', '')}
- 前回連絡: {contact.get('last_contact', '')}
- ノート: {contact.get('notes', '')}

適切なフォローアップメッセージ（メール本文）を3パターン作成してください:
1. カジュアルなフォロー
2. ビジネスライクなフォロー
3. 価値提供型のフォロー""",
            system_prompt="営業のプロフェッショナルとして、相手にとって価値のあるフォローアップメッセージを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {
                "follow_up_messages": result.get("text", ""),
                "contact": contact["name"],
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _lead_scoring(self, task_code: str, payload: dict) -> dict:
        """リードスコアリング"""
        contacts = self._load_contacts()

        result = await self.call_llm(
            prompt=f"""以下のリード一覧をスコアリングしてください。（0-100点）

リード一覧:
{json.dumps([{
    'name': c['name'], 'company': c.get('company', ''), 
    'source': c.get('source', ''), 'notes': c.get('notes', ''),
    'interactions': len(c.get('interactions', [])),
} for c in contacts[:30]], ensure_ascii=False, indent=2)}

各リードに以下の基準でスコアをつけてください:
- 企業規模・業界（20点）
- エンゲージメント度（インタラクション数）（30点）
- リードソース（20点）
- コンバージョン確率の推定（30点）

JSONフォーマットで結果を返してください。""",
            system_prompt="B2B営業のリードスコアリングの専門家として評価してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"scoring": result.get("text", ""), "total_leads": len(contacts)},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _customer_analysis(self, task_code: str, payload: dict) -> dict:
        """顧客分析"""
        contacts = self._load_contacts()

        stats = {
            "total": len(contacts),
            "by_status": {},
            "by_source": {},
        }
        for c in contacts:
            s = c.get("status", "unknown")
            stats["by_status"][s] = stats["by_status"].get(s, 0) + 1
            src = c.get("source", "unknown")
            stats["by_source"][src] = stats["by_source"].get(src, 0) + 1

        result = await self.call_llm(
            prompt=f"""以下の顧客データを分析し、ビジネスインサイトを提供してください。

統計:
{json.dumps(stats, ensure_ascii=False, indent=2)}

以下を含めてください:
1. 顧客ファネル分析
2. リードソース評価
3. 改善アクション（3-5個）
4. 次月の目標提案""",
            system_prompt="CRMアナリストとして、データ駆動の分析と提案を行ってください。",
            tier=LLMTier.DEFAULT,
            task_hint="analysis report",
        )

        return {
            "success": True,
            "result": {"analysis": result.get("text", ""), "stats": stats},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _pipeline_report(self, task_code: str, payload: dict) -> dict:
        """パイプラインレポート"""
        contacts = self._load_contacts()

        pipeline = {"lead": 0, "prospect": 0, "negotiation": 0, "closed": 0, "lost": 0}
        for c in contacts:
            s = c.get("status", "lead")
            if s in pipeline:
                pipeline[s] += 1

        lines = [
            "📊 【セールスパイプライン】",
            "━━━━━━━━━━━━━━━━━━",
            f"🟢 リード: {pipeline['lead']}件",
            f"🔵 見込み: {pipeline['prospect']}件",
            f"🟡 交渉中: {pipeline['negotiation']}件",
            f"🟣 成約: {pipeline['closed']}件",
            f"🔴 失注: {pipeline['lost']}件",
            f"📈 合計: {sum(pipeline.values())}件",
        ]

        return {
            "success": True,
            "result": {"report": "\n".join(lines), "pipeline": pipeline},
            "cost_yen": 0.0,
        }


# エージェントインスタンス
crm_agent = CRMAgent()
