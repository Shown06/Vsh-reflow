"""
Vsh-reflow - Finance-Agent (経費記録・請求書生成・売上管理)
経費・売上の記録管理、請求書PDF生成、財務レポート作成。
"""

import logging
import json
import os
from datetime import datetime, timezone
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class FinanceAgent(BaseAgent):
    """財務管理エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.ANALYST, name="Finance-Agent")
        self._finance_dir = os.environ.get("FINANCE_DATA_DIR", "/app/finance_data")
        try:
            os.makedirs(self._finance_dir, exist_ok=True)
        except OSError:
            self._finance_dir = "/tmp/finance_data"
            os.makedirs(self._finance_dir, exist_ok=True)

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "add_expense":
            return await self._add_expense(task_code, payload)
        elif task_type == "add_income":
            return await self._add_income(task_code, payload)
        elif task_type == "create_invoice":
            return await self._create_invoice(task_code, payload)
        elif task_type == "monthly_report":
            return await self._monthly_report(task_code, payload)
        elif task_type == "tax_summary":
            return await self._tax_summary(task_code, payload)
        elif task_type == "budget_plan":
            return await self._budget_plan(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    def _get_ledger_path(self) -> str:
        return os.path.join(self._finance_dir, "ledger.json")

    def _load_ledger(self) -> dict:
        path = self._get_ledger_path()
        if os.path.exists(path):
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        return {"expenses": [], "incomes": [], "invoices": []}

    def _save_ledger(self, ledger: dict):
        path = self._get_ledger_path()
        with open(path, "w", encoding="utf-8") as f:
            json.dump(ledger, f, ensure_ascii=False, indent=2)

    async def _add_expense(self, task_code: str, payload: dict) -> dict:
        """経費追加"""
        expense = {
            "id": f"EXP-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "date": payload.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "category": payload.get("category", "その他"),
            "description": payload.get("description", ""),
            "amount": payload.get("amount", 0),
            "tax_included": payload.get("tax_included", True),
            "receipt": payload.get("receipt", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        ledger = self._load_ledger()
        ledger["expenses"].append(expense)
        self._save_ledger(ledger)

        return {
            "success": True,
            "result": {
                "expense_id": expense["id"],
                "category": expense["category"],
                "amount": f"¥{expense['amount']:,}",
            },
            "cost_yen": 0.0,
        }

    async def _add_income(self, task_code: str, payload: dict) -> dict:
        """売上追加"""
        income = {
            "id": f"INC-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}",
            "date": payload.get("date", datetime.now(timezone.utc).strftime("%Y-%m-%d")),
            "source": payload.get("source", ""),
            "description": payload.get("description", ""),
            "amount": payload.get("amount", 0),
            "client": payload.get("client", ""),
            "invoice_id": payload.get("invoice_id", ""),
            "created_at": datetime.now(timezone.utc).isoformat(),
        }

        ledger = self._load_ledger()
        ledger["incomes"].append(income)
        self._save_ledger(ledger)

        return {
            "success": True,
            "result": {
                "income_id": income["id"],
                "source": income["source"],
                "amount": f"¥{income['amount']:,}",
            },
            "cost_yen": 0.0,
        }

    async def _create_invoice(self, task_code: str, payload: dict) -> dict:
        """請求書生成"""
        client_name = payload.get("client_name", "")
        items = payload.get("items", [])
        due_date = payload.get("due_date", "")
        notes = payload.get("notes", "")

        invoice_id = f"INV-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M')}"

        # 合計計算
        subtotal = sum(item.get("amount", 0) * item.get("quantity", 1) for item in items)
        tax = int(subtotal * 0.1)
        total = subtotal + tax

        # LLMでHTML請求書を生成
        items_text = "\n".join([
            f"- {item.get('name', '')}: ¥{item.get('amount', 0):,} × {item.get('quantity', 1)}"
            for item in items
        ])

        result = await self.call_llm(
            prompt=f"""以下の情報でHTML形式の請求書を生成してください。

請求書番号: {invoice_id}
発行日: {datetime.now(timezone.utc).strftime('%Y年%m月%d日')}
支払期限: {due_date}

請求先: {client_name}

品目:
{items_text}

小計: ¥{subtotal:,}
消費税 (10%): ¥{tax:,}
合計: ¥{total:,}

備考: {notes}

振込先:
（振込先は翔が後から記入するためプレースホルダーにしてください）

要件:
- 印刷可能なHTML
- プロフェッショナルなデザイン
- A4サイズに最適化
- 日本の商慣習に準拠""",
            system_prompt="経理のプロフェッショナルとして、正確で美しい請求書を作成してください。",
            tier=LLMTier.DEFAULT,
            task_hint="html code",
        )

        # 保存
        invoice_path = os.path.join(self._finance_dir, f"{invoice_id}.html")
        with open(invoice_path, "w", encoding="utf-8") as f:
            f.write(result.get("text", ""))

        ledger = self._load_ledger()
        ledger["invoices"].append({
            "id": invoice_id,
            "client": client_name,
            "total": total,
            "status": "未払い",
            "due_date": due_date,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "file": invoice_path,
        })
        self._save_ledger(ledger)

        return {
            "success": True,
            "result": {
                "invoice_id": invoice_id,
                "client": client_name,
                "total": f"¥{total:,}",
                "file": invoice_path,
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _monthly_report(self, task_code: str, payload: dict) -> dict:
        """月次財務レポート"""
        month = payload.get("month", datetime.now(timezone.utc).strftime("%Y-%m"))
        ledger = self._load_ledger()

        # 月のデータを抽出
        expenses = [e for e in ledger["expenses"] if e["date"].startswith(month)]
        incomes = [i for i in ledger["incomes"] if i["date"].startswith(month)]

        total_expense = sum(e.get("amount", 0) for e in expenses)
        total_income = sum(i.get("amount", 0) for i in incomes)
        profit = total_income - total_expense

        # カテゴリ別集計
        by_category = {}
        for e in expenses:
            cat = e.get("category", "その他")
            by_category[cat] = by_category.get(cat, 0) + e.get("amount", 0)

        result = await self.call_llm(
            prompt=f"""以下の財務データで月次レポートを作成してください。

期間: {month}
売上合計: ¥{total_income:,}
経費合計: ¥{total_expense:,}
利益: ¥{profit:,}

経費内訳:
{json.dumps(by_category, ensure_ascii=False, indent=2)}

売上件数: {len(incomes)}件
経費件数: {len(expenses)}件

以下を含めてください:
1. 📊 月次サマリー
2. 📈 売上分析
3. 📉 コスト分析
4. 💡 改善提案
5. 📋 次月の予測""",
            system_prompt="財務アドバイザーとして、簡潔で実用的なレポートを作成してください。",
            tier=LLMTier.DEFAULT,
            task_hint="analysis report",
        )

        return {
            "success": True,
            "result": {
                "report": result.get("text", ""),
                "summary": {
                    "month": month,
                    "income": total_income,
                    "expense": total_expense,
                    "profit": profit,
                },
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _tax_summary(self, task_code: str, payload: dict) -> dict:
        """確定申告用サマリー"""
        year = payload.get("year", datetime.now(timezone.utc).strftime("%Y"))
        ledger = self._load_ledger()

        expenses = [e for e in ledger["expenses"] if e["date"].startswith(year)]
        incomes = [i for i in ledger["incomes"] if i["date"].startswith(year)]

        total_income = sum(i.get("amount", 0) for i in incomes)
        total_expense = sum(e.get("amount", 0) for e in expenses)

        by_category = {}
        for e in expenses:
            cat = e.get("category", "その他")
            by_category[cat] = by_category.get(cat, 0) + e.get("amount", 0)

        result = await self.call_llm(
            prompt=f"""以下のデータで確定申告用のサマリーを作成してください。

年度: {year}年
総売上: ¥{total_income:,}
総経費: ¥{total_expense:,}
所得: ¥{total_income - total_expense:,}

経費カテゴリ別:
{json.dumps(by_category, ensure_ascii=False, indent=2)}

⚠️ 注意: これは参考情報です。正式な申告は税理士にご相談ください。

以下を含めてください:
1. 年間サマリー
2. 経費カテゴリ別集計
3. 控除の注意点
4. 税理士に相談すべきポイント""",
            system_prompt="税務の知識を持つアシスタントとして、参考情報を提供してください。必ず「正式な申告は税理士にご相談ください」と付記してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="analysis report",
        )

        return {
            "success": True,
            "result": {
                "tax_summary": result.get("text", ""),
                "year": year,
                "warning": "⚠️ 正式な申告は税理士にご相談ください",
            },
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _budget_plan(self, task_code: str, payload: dict) -> dict:
        """予算計画"""
        period = payload.get("period", "次月")
        goal = payload.get("goal", "")

        ledger = self._load_ledger()
        recent_expenses = ledger["expenses"][-30:]

        result = await self.call_llm(
            prompt=f"""以下のデータに基づいて予算計画を作成してください。

期間: {period}
目標: {goal}

直近の支出傾向:
{json.dumps([{
    'category': e.get('category', ''), 
    'amount': e.get('amount', 0),
    'date': e.get('date', ''),
} for e in recent_expenses], ensure_ascii=False, indent=2)}

以下を含めてください:
1. 📊 推奨予算配分
2. 🎯 コスト削減可能な項目
3. 📈 投資すべき項目
4. ⚠️ リスク""",
            system_prompt="ファイナンシャルプランナーとして、実行可能な予算計画を作成してください。",
            tier=LLMTier.DEFAULT,
            task_hint="analysis",
        )

        return {
            "success": True,
            "result": {"budget_plan": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
finance_agent = FinanceAgent()
