"""
Vsh-reflow - PM-Agent (会議進行・タスク割当)
§4.2 AI会議フローの全11ステップを実装。
"""

import logging
import os
from typing import Any
from datetime import datetime

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.models import AgentRole, Task, TaskStatus
from src.database import get_session

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

        # Step 2-7: 各エージェントに逐次的にタスクを投入し、結果を待つ
        from src.workers.celery_app import dispatch_agent_task
        from sqlalchemy import select
        import asyncio
        
        discord_channel_id = payload.get("discord_channel_id")
        meeting_results = {}

        async with get_session() as session:
            # 1. Growth-Agent (リサーチ)
            sub_task_code = f"{task_code}-G"
            growth_payload = {"topic": topic, "meeting_code": task_code}
            new_task = Task(
                task_code=sub_task_code,
                title=f"【会議】リサーチ取得",
                description=f"会議 '{topic}' のためのリサーチ",
                task_type="meeting_research",
                assigned_agent=AgentRole.GROWTH,
                status=TaskStatus.PENDING,
                payload=growth_payload,
                discord_channel_id=discord_channel_id
            )
            session.add(new_task)
            await session.commit() # 登録を確定
            
            dispatch_agent_task.apply_async(args=("growth", sub_task_code, "meeting_research", growth_payload), queue="growth_queue")
            
            # 完了を待機
            growth_res = await self._wait_for_subtask(sub_task_code)
            meeting_results["research"] = growth_res.get("research", "取得失敗")

            # 2. Content-Agent (コンテンツ案)
            sub_task_code = f"{task_code}-C"
            content_payload = {
                "topic": topic, 
                "meeting_code": task_code, 
                "num_proposals": 3,
                "research_context": meeting_results["research"] # リサーチ結果を渡す！
            }
            new_task = Task(
                task_code=sub_task_code,
                title=f"【会議】コンテンツ作成",
                description=f"会議 '{topic}' のためのコンテンツ案作成",
                task_type="meeting_content",
                assigned_agent=AgentRole.CONTENT,
                status=TaskStatus.PENDING,
                payload=content_payload,
                discord_channel_id=discord_channel_id
            )
            session.add(new_task)
            await session.commit()
            
            dispatch_agent_task.apply_async(args=("content", sub_task_code, "meeting_content", content_payload), queue="content_queue")
            content_res = await self._wait_for_subtask(sub_task_code)
            meeting_results["content_proposals"] = content_res.get("content_proposals", "作成失敗")

            # 3. Design-Agent / Guard-Agent / Analyst-Agent (並列でも良いが、実況感を出すため逐次)
            # デザイン
            sub_task_code = f"{task_code}-D"
            design_payload = {"topic": topic, "meeting_code": task_code, "content_context": meeting_results["content_proposals"]}
            new_task = Task(task_code=sub_task_code, title=f"【会議】デザイン案作成", task_type="meeting_design", assigned_agent=AgentRole.DESIGN, status=TaskStatus.PENDING, payload=design_payload, discord_channel_id=discord_channel_id)
            session.add(new_task); await session.commit()
            dispatch_agent_task.apply_async(args=("design", sub_task_code, "meeting_design", design_payload), queue="design_queue")
            design_res = await self._wait_for_subtask(sub_task_code)
            meeting_results["design_proposals"] = design_res.get("design_proposals", "作成失敗")

            # ガード (リスク審査)
            sub_task_code = f"{task_code}-U"
            guard_payload = {"topic": topic, "meeting_code": task_code, "content_context": meeting_results["content_proposals"]}
            new_task = Task(task_code=sub_task_code, title=f"【会議】リスク審査", task_type="meeting_review", assigned_agent=AgentRole.GUARD, status=TaskStatus.PENDING, payload=guard_payload, discord_channel_id=discord_channel_id)
            session.add(new_task); await session.commit()
            dispatch_agent_task.apply_async(args=("guard", sub_task_code, "meeting_review", guard_payload), queue="guard_queue")
            guard_res = await self._wait_for_subtask(sub_task_code)
            meeting_results["guard_review"] = guard_res.get("guard_review", "審査失敗")

            # アナリスト (最終分析)
            sub_task_code = f"{task_code}-A"
            analyst_payload = {"topic": topic, "meeting_code": task_code, "full_context": str(meeting_results)}
            new_task = Task(task_code=sub_task_code, title=f"【会議】最終分析", task_type="meeting_analysis", assigned_agent=AgentRole.ANALYST, status=TaskStatus.PENDING, payload=analyst_payload, discord_channel_id=discord_channel_id)
            session.add(new_task); await session.commit()
            dispatch_agent_task.apply_async(args=("analyst", sub_task_code, "meeting_analysis", analyst_payload), queue="analyst_queue")
            analyst_res = await self._wait_for_subtask(sub_task_code)
            meeting_results["analysis"] = analyst_res.get("analysis", "分析失敗")

            # 4. 最終報告: 10枚のスライド構成案を作成し、PDF化する
            logger.info("プレゼン資料の構成を作成中...")
            slides_result = await self.call_llm(
                prompt=f"""これまでのAI会議の結果を元に、初心者向けの「10枚のプレゼン資料スライド」の構成を作成してください。
                
                テーマ: {topic}
                会議結果サマリー: {str(meeting_results)}
                
                以下のJSON形式で、ちょうど10枚分のスライド内容を出力してください:
                [
                  {{"title": "スライドのタイトル", "content": "スライドの本文（箇条書き等、簡潔に）"}},
                  ...
                ]
                """,
                system_prompt="あなたは優秀なプレゼン資料作成のスペシャリストです。10枚のスライドで、会議の成果を分かりやすく伝えてください。JSONリスト形式のみを返却してください。",
                tier=LLMTier.IMPORTANT
            )
            
            import json
            import re
            slides_text = slides_result.get("text", "[]")
            try:
                match = re.search(r'\[.*\]', slides_text, re.DOTALL)
                if match:
                    slides_data = json.loads(match.group())
                    if not isinstance(slides_data, list) or not slides_data:
                        raise ValueError("Empty or invalid slides list")
                else:
                    raise ValueError("No JSON array found in LLM response")
            except (json.JSONDecodeError, ValueError) as e:
                logger.warning(f"スライドJSON解析失敗 ({e}), フォールバック使用")
                slides_data = [
                    {"title": topic, "content": "会議の成果サマリー"},
                    {"title": "リサーチ結果", "content": str(meeting_results.get("research", ""))[:500]},
                    {"title": "コンテンツ案", "content": str(meeting_results.get("content_proposals", ""))[:500]},
                    {"title": "デザイン案", "content": str(meeting_results.get("design_proposals", ""))[:500]},
                    {"title": "リスク審査", "content": str(meeting_results.get("guard_review", ""))[:500]},
                    {"title": "分析結果", "content": str(meeting_results.get("analysis", ""))[:500]},
                ]

            # PDF生成
            output_dir = "/app/generated_reports"
            os.makedirs(output_dir, exist_ok=True)
            output_filename = f"Report_{task_code}.pdf"
            output_path = os.path.join(output_dir, output_filename)
            
            from src.utils.pdf_generator import generate_presentation_pdf
            pdf_success = await generate_presentation_pdf(topic, slides_data, output_path)

        return {
            "success": True,
            "result": {
                "agenda": agenda_result.get("text", ""),
                "meeting_report": "会議全工程が完了しました。プレゼン資料（PDF）を作成しました。",
                "pdf_path": output_path if pdf_success else None,
                "status": "COMPLETED",
                "participants": participants,
            },
            "cost_yen": agenda_result.get("cost_yen", 0.0) + slides_result.get("cost_yen", 0.0),
        }

    async def _wait_for_subtask(self, sub_task_code: str, timeout: int = 300) -> dict:
        """サブタスクの完了を待機するヘルパー"""
        from sqlalchemy import select
        import asyncio
        start_time = datetime.now()
        while (datetime.now() - start_time).total_seconds() < timeout:
            async with get_session() as session:
                stmt = select(Task).where(Task.task_code == sub_task_code)
                res = await session.execute(stmt)
                task = res.scalar_one_or_none()
                if task and task.status == TaskStatus.COMPLETED:
                    return task.result or {}
                if task and task.status == TaskStatus.FAILED:
                    return {"error": task.error_message or "Unknown failure"}
            await asyncio.sleep(5)
        return {"error": "Timeout"}

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
