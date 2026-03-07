"""
Vsh-reflow - エージェント基底クラス
全AIエージェント共通の基底クラス。
タスク受信、LLM呼び出し（モデル自動選択）、監査ログ記録、ヘルスチェック。
"""

import logging
import time
from abc import ABC, abstractmethod
from datetime import datetime, timezone
from typing import Any, Optional

from src.config import settings
from src.cost_manager import CostManager, LLMTier, cost_manager
from src.database import get_session
from src.models import AgentRole, AuditLog, Task, TaskStatus

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """全エージェント共通の基底クラス"""

    def __init__(self, role: AgentRole, name: str):
        self.role = role
        self.name = name
        self._cost_manager = cost_manager
        self._logger = logging.getLogger(f"agent.{name}")
        self._redis = None
        # 初期状態を「待機中」として報告
        self._report_presence_sync(status="idle", thought="起動しました。待機中です。")

    def _report_presence_sync(self, status: str, task: str = "", thought: str = ""):
        """Redisにエージェントの現在状態を報告（同期版）"""
        try:
            import redis
            import json
            r = redis.Redis.from_url(settings.redis.url, socket_timeout=5)
            data = {
                "name": self.name,
                "role": self.role.value if hasattr(self.role, "value") else str(self.role),
                "status": status,
                "task": task,
                "thought": thought,
                "last_seen": datetime.now(timezone.utc).isoformat()
            }
            res = r.set(f"vsh:agent:{self.name}", json.dumps(data), ex=600)
            self._logger.info(f"Presence reported (sync): {status} -> {res}")
        except Exception as e:
            self._logger.warning(f"Failed to report presence (sync): {e}")

    def _get_redis(self):
        """Redisクライアントを遅延初期化"""
        if self._redis is None:
            try:
                import redis
                self._redis = redis.Redis.from_url(settings.redis.url)
            except Exception as e:
                self._logger.error(f"Redis初期化失敗: {e}")
        return self._redis

    async def _report_presence(self, status: str, task: str = "", thought: str = ""):
        """Redisにエージェントの現在状態を報告"""
        r = self._get_redis()
        if not r:
            return
            
        try:
            import json
            data = {
                "name": self.name,
                "role": self.role.value if hasattr(self.role, "value") else str(self.role),
                "status": status, # idle, working, thinking, error
                "task": task,
                "thought": thought,
                "last_seen": datetime.now(timezone.utc).isoformat()
            }
            # キー: vsh:agent:{name}, 有効期限 10分
            r.set(f"vsh:agent:{self.name}", json.dumps(data), ex=600)
        except Exception as e:
            self._logger.warning(f"Presence報告失敗: {e}")

    @abstractmethod
    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        """
        タスクを実行する（各エージェントで実装必須）

        Returns:
            dict: {
                "success": bool,
                "result": dict,  # 結果データ
                "cost_yen": float,
                "require_approval": bool,
            }
        """
        raise NotImplementedError

    async def run(self, task_code: str, task_type: str, payload: dict) -> dict:
        """タスク実行のメインエントリポイント"""
        start_time = time.time()
        self._logger.info(f"タスク開始: {task_code} ({task_type})")

        # コスト制限チェック
        can_execute = await self._cost_manager.can_execute_task()
        if not can_execute:
            self._logger.warning(f"コスト上限到達 - タスク {task_code} をブロック")
            await self._record_audit(
                task_code=task_code,
                action=f"{task_type}_blocked",
                success=False,
                error="月間コスト上限に到達しています",
            )
            return {
                "success": False,
                "error": "月間コスト上限に到達しています。/approve cost-extension で延長してください。",
            }

        # タスクステータス更新
        await self._update_task_status(task_code, TaskStatus.IN_PROGRESS)
        await self._report_presence(status="working", task=task_type, thought="タスクを開始します...")

        try:
            result = await self.execute_task(task_code, task_type, payload)
            elapsed = time.time() - start_time

            # 監査ログ記録
            await self._record_audit(
                task_code=task_code,
                action=task_type,
                input_data=payload,
                output_data=result.get("result", {}),
                success=result.get("success", True),
                cost_yen=result.get("cost_yen", 0.0),
            )

            # タスクステータス更新
            if result.get("require_approval"):
                await self._update_task_status(task_code, TaskStatus.AWAITING_APPROVAL)
            elif result.get("success"):
                await self._update_task_status(
                    task_code, TaskStatus.COMPLETED,
                    result=result.get("result", {}),
                )
            else:
                await self._update_task_status(
                    task_code, TaskStatus.FAILED,
                    error=result.get("error", "Unknown error"),
                )

            self._logger.info(
                f"タスク完了: {task_code} ({elapsed:.2f}s) "
                f"success={result.get('success')} cost=¥{result.get('cost_yen', 0):.2f}"
            )
            return result

        except Exception as e:
            elapsed = time.time() - start_time
            self._logger.error(f"タスクエラー: {task_code} - {e}")

            await self._record_audit(
                task_code=task_code,
                action=task_type,
                input_data=payload,
                success=False,
                error=str(e),
            )
            await self._update_task_status(task_code, TaskStatus.FAILED, error=str(e))
            await self._report_presence(status="error", task=task_type, thought=f"エラーが発生しました: {str(e)}")

            return {"success": False, "error": str(e)}
        finally:
            # 完了または失敗後、しばらくしてからidleに戻る（デモ用）
            await self._report_presence(status="idle")

    def auto_select_provider(self, task_hint: str = "") -> str:
        """
        タスク種別に応じて最適なLLMプロバイダーを自動選択
        - コード生成 → anthropic (Claude: コーディング優位)
        - 長文分析 → gemini (Gemini: 長コンテキスト)
        - 日本語テキスト → openai (GPT-4o: 日本語品質) ※オプション
        - デフォルト → anthropic (Claude)
        """
        hint = task_hint.lower()
        if any(k in hint for k in ["code", "dev", "programming", "debug", "fix", "html", "css", "js", "python"]):
            return "anthropic"
        elif any(k in hint for k in ["analysis", "research", "long", "report", "browse"]):
            if settings.gemini.api_key:
                return "gemini"
            return "anthropic"
        elif any(k in hint for k in ["japanese", "日本語", "翻訳"]):
            if settings.openai.api_key:
                return "openai"
            return "anthropic"
        return "anthropic"

    def _load_clawdbot_context(self) -> str:
        """Clawdbotのアイデンティティとメモリコンテキストを読み込む"""
        import os
        
        context_parts = []
        base_dir = "/Users/two-de-sir/Vsh-reflow/src/agents/prompts/clawdbot"
        
        files_to_load = {
            "IDENTITY": "IDENTITY.md",
            "SOUL": "SOUL.md",
            "USER": "USER.md",
            "TOOLS (Local Environment)": "TOOLS.md"
        }
        
        for name, filename in files_to_load.items():
            filepath = os.path.join(base_dir, filename)
            if os.path.exists(filepath):
                try:
                    with open(filepath, "r", encoding="utf-8") as f:
                        content = f.read().strip()
                        if content:
                            context_parts.append(f"--- [Clawdbot {name}] ---\n{content}\n")
                except Exception as e:
                    logging.warning(f"Failed to load Clawdbot context {filename}: {e}")
                    
        return "\n".join(context_parts)

    async def call_llm(
        self,
        prompt: str,
        system_prompt: str = "",
        tier: LLMTier = LLMTier.DEFAULT,
        provider: str = "auto",
        task_hint: str = "",
        max_tokens: int = 2000,
        temperature: float = 0.7,
        image_path: str = None
    ) -> dict:
        """
        LLMを呼び出す（モデル・プロバイダー自動選択付き）
        """
        # Clawdbotコンテキストの注入
        clawdbot_context = self._load_clawdbot_context()
        if clawdbot_context:
            system_prompt = f"{clawdbot_context}\n\n--- [Agent Specific System Prompt] ---\n{system_prompt}"

        # provider="auto" でタスク種別に応じて最適なプロバイダーを自動選択。
        if provider == "auto":
            provider = self.auto_select_provider(task_hint)

        model = self._cost_manager.select_model(tier, provider)
        # ステータス報告: 思考中
        await self._report_presence(status="thinking", thought=f"{provider}/{model} で思考を生成中...")

        try:
            if provider == "openai":
                result = await self._call_openai(
                    prompt, system_prompt, model, max_tokens, temperature
                )
            elif provider == "anthropic":
                result = await self._call_anthropic(
                    prompt, system_prompt, model, max_tokens, temperature
                )
            elif provider == "gemini":
                result = await self._call_gemini(
                    prompt, system_prompt, model, max_tokens, temperature
                )
            else:
                raise ValueError(f"Unknown provider: {provider}")

            if "error" in result:
                # LLM呼び出し自体は成功（Mock等）だったがエラーメッセージが入っている場合
                 pass
            elif "input_tokens" in result and "output_tokens" in result:
                # コスト記録
                cost = self._cost_manager.estimate_llm_cost(
                    model, result["input_tokens"], result["output_tokens"]
                )
                await self._cost_manager.record_cost(
                    service=provider,
                    operation="chat_completion",
                    cost_yen=cost,
                    model=model,
                    input_tokens=result["input_tokens"],
                    output_tokens=result["output_tokens"],
                    agent=self.name,
                )
                result["cost_yen"] = cost
                
            return result

        except Exception as e:
            self._logger.error(f"LLM呼び出しエラー ({provider}/{model}): {e}")
            return {
                "text": f"[LLM Error] {str(e)}",
                "model": model,
                "cost_yen": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "error": str(e),
            }

    async def _call_openai(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        """OpenAI API呼び出し"""
        try:
            from openai import AsyncOpenAI

            async with AsyncOpenAI(api_key=settings.openai.api_key) as client:
                messages = []
                if system_prompt:
                    messages.append({"role": "system", "content": system_prompt})
                messages.append({"role": "user", "content": prompt})

                response = await client.chat.completions.create(
                    model=model,
                    messages=messages,
                    max_tokens=max_tokens,
                    temperature=temperature,
                )

                return {
                    "text": response.choices[0].message.content,
                    "model": model,
                    "input_tokens": response.usage.prompt_tokens,
                    "output_tokens": response.usage.completion_tokens,
                }
        except Exception as e:
            # APIキー未設定時はモックレスポンス
            self._logger.warning(f"OpenAI API エラー (モックレスポンス使用): {e}")
            return {
                "text": f"[Mock Response for {model}] {prompt[:100]}...",
                "model": model,
                "input_tokens": len(prompt) // 4,
                "output_tokens": 100,
            }

    async def _call_anthropic(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        """Anthropic API呼び出し"""
        try:
            from anthropic import AsyncAnthropic

            async with AsyncAnthropic(api_key=settings.anthropic.api_key) as client:
                kwargs = {
                    "model": model,
                    "max_tokens": max_tokens,
                    "temperature": temperature,
                    "messages": [{"role": "user", "content": prompt}],
                }
                if system_prompt:
                    kwargs["system"] = system_prompt

                response = await client.messages.create(**kwargs)

                return {
                    "text": response.content[0].text,
                    "model": model,
                    "input_tokens": response.usage.input_tokens,
                    "output_tokens": response.usage.output_tokens,
                }
        except Exception as e:
            self._logger.warning(f"Anthropic API エラー (モックレスポンス使用): {e}")
            return {
                "text": f"[Mock Response for {model}] {prompt[:100]}...",
                "model": model,
                "input_tokens": len(prompt) // 4,
                "output_tokens": 100,
            }

    async def _call_gemini(
        self,
        prompt: str,
        system_prompt: str,
        model: str,
        max_tokens: int,
        temperature: float,
    ) -> dict:
        """Google Gemini API呼び出し"""
        try:
            import google.generativeai as genai

            genai.configure(api_key=settings.gemini.api_key)
            gen_model = genai.GenerativeModel(
                model_name=model,
                system_instruction=system_prompt if system_prompt else None,
            )
            response = await gen_model.generate_content_async(
                prompt,
                generation_config=genai.GenerationConfig(
                    max_output_tokens=max_tokens,
                    temperature=temperature,
                ),
            )

            # トークン数概算
            input_tokens = len(prompt) // 4
            output_tokens = len(response.text) // 4 if response.text else 0

            return {
                "text": response.text or "",
                "model": model,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
            }
        except Exception as e:
            self._logger.warning(f"Gemini API エラー (モックレスポンス使用): {e}")
            return {
                "text": f"[Mock Response for {model}] {prompt[:100]}...",
                "model": model,
                "input_tokens": len(prompt) // 4,
                "output_tokens": 100,
            }

    async def _record_audit(
        self,
        task_code: str,
        action: str,
        input_data: Optional[dict] = None,
        output_data: Optional[dict] = None,
        success: bool = True,
        error: Optional[str] = None,
        cost_yen: float = 0.0,
    ):
        """監査ログを記録（§9.3準拠）"""
        try:
            async with get_session() as session:
                # task_codeからtask_idを取得
                from sqlalchemy import select
                result = await session.execute(
                    select(Task.id).where(Task.task_code == task_code)
                )
                task_id = result.scalar_one_or_none()

                log = AuditLog(
                    task_id=task_id,
                    agent=self.name,
                    action=action,
                    input_data=input_data or {},
                    output_data=output_data or {},
                    success=success,
                    error_message=error,
                    cost_yen=cost_yen,
                )
                session.add(log)
        except Exception as e:
            self._logger.error(f"監査ログ記録エラー: {e}")

    async def _update_task_status(
        self,
        task_code: str,
        status: TaskStatus,
        result: Optional[dict] = None,
        error: Optional[str] = None,
    ):
        """タスクステータスを更新"""
        try:
            async with get_session() as session:
                from sqlalchemy import select, update
                stmt = (
                    update(Task)
                    .where(Task.task_code == task_code)
                    .values(
                        status=status,
                        updated_at=datetime.now(timezone.utc),
                    )
                )
                if status == TaskStatus.IN_PROGRESS:
                    stmt = stmt.values(started_at=datetime.now(timezone.utc))
                elif status in (TaskStatus.COMPLETED, TaskStatus.FAILED):
                    stmt = stmt.values(completed_at=datetime.now(timezone.utc))
                if result:
                    stmt = stmt.values(result=result)
                if error:
                    stmt = stmt.values(error_message=error)

                await session.execute(stmt)
        except Exception as e:
            self._logger.error(f"タスクステータス更新エラー: {e}")
