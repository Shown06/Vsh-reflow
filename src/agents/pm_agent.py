"""
Vsh-reflow - PM-Agent (会議進行・タスク割当)
§4.2 AI会議フローの全11ステップを実装。
"""

import logging
from typing import Any

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole

logger = logging.getLogger(__name__)


class PMAgent(BaseAgent):
    """PM / 議長エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.PM, name="PM-Agent")

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        """タスクを実行"""
        if task_type == "conduct_meeting":
            return await self._conduct_meeting(task_code, payload)
        elif task_type == "create_agenda":
            return await self._create_agenda(task_code, payload)
        elif task_type == "compile_approval":
            return await self._compile_approval_request(task_code, payload)
        elif task_type == "heartbeat":
            return await self._process_heartbeat(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _process_heartbeat(self, task_code: str, payload: dict) -> dict:
        """
        Clawdbot Heartbeat 処理
        定期的に呼ばれ、必要なら他のエージェント(Email, Schedule等)に処理を委譲する。
        """
        context_prompt = payload.get("context", "Regular heartbeat check.")
        
        # LLMに現在の時間や状況を判断させ、行動を決定する
        # （今回はシンプルなプロンプトでシミュレーション）
        import datetime
        now_str = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        result = await self.call_llm(
            prompt=f"【Heartbeat】現在時刻: {now_str}\n指示: {context_prompt}\n必要ならスケジュール確認やメール確認を提案してください。",
            system_prompt="あなたは自律型AGIの司令塔です。定期チェックを行い、アクションが必要か判断してください。",
            tier=LLMTier.DEFAULT,
        )
        
        decision_text = result.get("text", "")
        
        logger.info(f"Heartbeat decision: {decision_text[:100]}...")
        
        if "HEARTBEAT_OK" in decision_text.upper():
            return {"success": True, "action": "none", "message": "HEARTBEAT_OK"}
            
        # 今後ここに「メール確認」や「スケジュール確認」などのCelery Task発行処理を追加可能
        
        return {
            "success": True, 
            "action": "processed", 
            "message": decision_text,
            "cost_yen": result.get("cost_yen", 0)
        }

    async def _conduct_meeting(self, task_code: str, payload: dict) -> dict:
        """
        §4.2 AI会議フロー実行
        1. アジェンダ作成
        2. 各エージェントへ配布
        3-7. 各エージェントのタスクをキューに投入
        8. 合意内容を承認申請書にまとめ
        """
        topic = payload.get("topic", "")
        participants = payload.get("participants", [])

        # Step 1: アジェンダ作成
        agenda_result = await self.call_llm(
            prompt=f"""あなたはAIマーケティングチームのPMです。
以下のテーマでAI社内会議のアジェンダを作成してください。

テーマ: {topic}
参加者: {', '.join(participants)}

以下の形式で出力してください:
1. 目的・ゴールの共有
2. データ収集報告（Growth-Agent）
3. コンテンツ案提出（Content-Agent x 3案）
4. デザイン案提出（Design-Agent）
5. リスク・コスト審査（Guard-Agent）
6. パフォーマンス分析・推薦（Analyst-Agent）
7. 合意形成・承認申請書作成""",
            system_prompt="あなたは優秀なプロジェクトマネージャーです。簡潔かつ実行可能なアジェンダを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        # Step 2-7: 各エージェントにタスクを投入
        from src.workers.celery_app import dispatch_agent_task

        # Growth-Agentにリサーチ指示
        dispatch_agent_task.apply_async(
            args=("growth", task_code, "meeting_research", {"topic": topic, "meeting_code": task_code}),
            queue="growth_queue"
        )

        # Content-Agentに3案作成指示
        dispatch_agent_task.apply_async(
            args=("content", task_code, "meeting_content", {"topic": topic, "meeting_code": task_code, "num_proposals": 3}),
            queue="content_queue"
        )

        # Design-Agentにデザインプロンプト作成指示
        dispatch_agent_task.apply_async(
            args=("design", task_code, "meeting_design", {"topic": topic, "meeting_code": task_code}),
            queue="design_queue"
        )

        # Guard-Agentにリスク審査指示
        dispatch_agent_task.apply_async(
            args=("guard", task_code, "meeting_review", {"topic": topic, "meeting_code": task_code}),
            queue="guard_queue"
        )

        # Analyst-Agentに分析・推薦指示
        dispatch_agent_task.apply_async(
            args=("analyst", task_code, "meeting_analysis", {"topic": topic, "meeting_code": task_code}),
            queue="analyst_queue"
        )

        return {
            "success": True,
            "result": {
                "agenda": agenda_result.get("text", ""),
                "status": "会議を開始しました。各エージェントにタスクを配布済み。",
                "participants": participants,
            },
            "cost_yen": agenda_result.get("cost_yen", 0.0),
        }

    async def _create_agenda(self, task_code: str, payload: dict) -> dict:
        """アジェンダ作成"""
        topic = payload.get("topic", "")

        result = await self.call_llm(
            prompt=f"テーマ「{topic}」に関するAI社内会議のアジェンダを作成してください。",
            system_prompt="PMとして簡潔で実行可能なアジェンダを作成してください。",
            tier=LLMTier.DEFAULT,
        )

        return {
            "success": True,
            "result": {"agenda": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _compile_approval_request(self, task_code: str, payload: dict) -> dict:
        """
        Step 8: 各エージェントの結果を合意内容としてまとめ、承認申請書を作成
        """
        meeting_results = payload.get("meeting_results", {})
        topic = payload.get("topic", "")

        result = await self.call_llm(
            prompt=f"""以下の会議結果をもとに、オーナー（翔）への承認申請書を作成してください。

テーマ: {topic}

リサーチ結果: {meeting_results.get('research', 'なし')}
コンテンツ案: {meeting_results.get('content', 'なし')}
デザイン案: {meeting_results.get('design', 'なし')}
リスク審査: {meeting_results.get('guard_review', 'なし')}
分析・推薦: {meeting_results.get('analysis', 'なし')}

承認申請書のフォーマット:
- 実行内容の要約
- 推奨案とその理由
- リスク評価
- 予測インパクト""",
            system_prompt="PMとして、明確で判断しやすい承認申請書を作成してください。",
            tier=LLMTier.IMPORTANT,
        )

        # 承認リクエストを作成
        from src.approval_manager import approval_manager
        await approval_manager.create_approval_request(
            task_id=task_code,
            requester_agent=self.name,
            action_type="sns_post",
            summary=f"AI会議結果: {topic}",
            details=meeting_results,
            preview_content=result.get("text", ""),
            estimated_impact="会議での合意内容に基づく投稿",
            guard_review=meeting_results.get("guard_review", ""),
        )

        return {
            "success": True,
            "result": {"approval_document": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
            "require_approval": True,
        }


# エージェントインスタンス
pm_agent = PMAgent()
