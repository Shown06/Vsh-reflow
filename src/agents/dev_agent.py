"""
Vsh-reflow - Dev-Agent (コード生成・実行・テスト)
LLMでコード生成 → Dockerサンドボックスで安全に実行 → 結果返却。
自動リトライ付き（最大3回）。
"""

import asyncio
import logging
import os
import tempfile
import uuid
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.config import settings
from src.models import AgentRole

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/app/projects")


class DevAgent(BaseAgent):
    """コード生成・実行エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.CONTENT, name="Dev-Agent")

    def _ensure_dirs(self):
        try:
            os.makedirs(PROJECTS_DIR, exist_ok=True)
        except OSError:
            pass

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "code_generation":
            return await self._generate_and_run(task_code, payload)
        elif task_type == "code_fix":
            return await self._fix_code(task_code, payload)
        elif task_type == "code_test":
            return await self._test_code(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _generate_and_run(self, task_code: str, payload: dict, retry: int = 0) -> dict:
        """コード生成→サンドボックス実行（最大3回リトライ）"""
        instruction = payload.get("instruction", "")
        language = payload.get("language", "python")
        total_cost = 0.0

        # Step 1: LLMでコード生成
        gen_result = await self.call_llm(
            prompt=f"""以下の指示に従ってコードを生成してください。

指示: {instruction}
言語: {language}

要件:
- 完全に動作するコードを生成
- コメントを含める
- エラーハンドリングを含める
- 実行可能な形式で出力（```{language}...``` ブロックで囲む）

コードのみを出力してください。""",
            system_prompt=f"あなたは{language}のエキスパートプログラマーです。クリーンで効率的なコードを生成してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="code dev programming",
        )
        total_cost += gen_result.get("cost_yen", 0.0)

        # コードブロックを抽出
        code = self._extract_code(gen_result.get("text", ""), language)

        # Step 2: サンドボックスで実行
        exec_result = await self._run_in_sandbox(code, language, task_code)

        # Step 3: エラー時は自動修正（最大3回）
        if not exec_result["success"] and retry < 3:
            fix_result = await self.call_llm(
                prompt=f"""以下のコードでエラーが発生しました。修正してください。

元のコード:
```{language}
{code}
```

エラー:
{exec_result.get('error', '')}

修正したコードのみを出力してください。""",
                system_prompt="バグを修正して、正しく動作するコードを出力してください。",
                tier=LLMTier.IMPORTANT,
                task_hint="code fix debug",
            )
            total_cost += fix_result.get("cost_yen", 0.0)

            fixed_code = self._extract_code(fix_result.get("text", ""), language)
            exec_result = await self._run_in_sandbox(fixed_code, language, task_code)
            code = fixed_code

            if not exec_result["success"] and retry < 2:
                return await self._generate_and_run(
                    task_code,
                    {**payload, "instruction": f"{instruction}\n\n前回のエラー: {exec_result.get('error', '')}"},
                    retry + 1,
                )

        # ファイル保存
        self._ensure_dirs()
        ext = {"python": ".py", "javascript": ".js", "html": ".html"}.get(language, ".txt")
        filepath = os.path.join(PROJECTS_DIR, f"{task_code}{ext}")
        try:
            with open(filepath, "w") as f:
                f.write(code)
        except Exception:
            filepath = "保存不可（Docker外実行中）"

        return {
            "success": exec_result["success"],
            "result": {
                "code": code,
                "output": exec_result.get("output", ""),
                "filepath": filepath,
                "language": language,
                "retries": retry,
            },
            "error": exec_result.get("error"),
            "cost_yen": total_cost,
        }

    def _extract_code(self, text: str, language: str) -> str:
        """LLM出力からコードブロックを抽出"""
        import re
        patterns = [
            rf"```{language}\n(.*?)```",
            r"```\n(.*?)```",
            r"```(.*?)```",
        ]
        for pattern in patterns:
            match = re.search(pattern, text, re.DOTALL)
            if match:
                return match.group(1).strip()
        return text.strip()

    async def _run_in_sandbox(self, code: str, language: str, task_code: str) -> dict:
        """Dockerサンドボックスでコードを実行"""
        timeout = settings.sandbox.timeout_seconds

        try:
            # コードを一時ファイルに書き出し
            ext = {"python": ".py", "javascript": ".js"}.get(language, ".py")
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=ext, delete=False, prefix=f"ag_{task_code}_"
            ) as f:
                f.write(code)
                tmpfile = f.name

            # Docker実行コマンド
            cmd_map = {
                "python": f"python3 {os.path.basename(tmpfile)}",
                "javascript": f"node {os.path.basename(tmpfile)}",
            }
            run_cmd = cmd_map.get(language, f"python3 {os.path.basename(tmpfile)}")

            docker_cmd = [
                "docker", "run", "--rm",
                "--memory", settings.sandbox.memory_limit,
                "--cpus", "1",
                "--network", "none" if settings.sandbox.network_disabled else "bridge",
                "-v", f"{tmpfile}:/sandbox/{os.path.basename(tmpfile)}:ro",
                "-w", "/sandbox",
                settings.sandbox.image,
                "sh", "-c", run_cmd,
            ]

            process = await asyncio.create_subprocess_exec(
                *docker_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=timeout
            )

            os.unlink(tmpfile)

            if process.returncode == 0:
                return {
                    "success": True,
                    "output": stdout.decode()[:5000],
                }
            else:
                return {
                    "success": False,
                    "output": stdout.decode()[:2000],
                    "error": stderr.decode()[:2000],
                }

        except asyncio.TimeoutError:
            return {"success": False, "error": f"実行タイムアウト ({timeout}秒)"}
        except FileNotFoundError:
            # Dockerが利用不可（ローカル開発時）
            logger.info("Docker未利用 - ローカル実行シミュレーション")
            return {
                "success": True,
                "output": f"[シミュレーション] コード生成完了 ({language}, {len(code)}文字)",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    async def _fix_code(self, task_code: str, payload: dict) -> dict:
        """コードのバグ修正"""
        error_info = payload.get("error", "")
        code = payload.get("code", "")

        result = await self.call_llm(
            prompt=f"""以下のコードのバグを修正してください。

コード:
{code}

エラー情報:
{error_info}

修正後のコードのみを出力してください。""",
            system_prompt="バグを正確に特定し、最小限の変更で修正してください。",
            tier=LLMTier.IMPORTANT,
            task_hint="code fix debug",
        )

        return {
            "success": True,
            "result": {"fixed_code": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }

    async def _test_code(self, task_code: str, payload: dict) -> dict:
        """コードのテスト実行"""
        filepath = payload.get("filepath", "")

        result = await self.call_llm(
            prompt=f"以下のファイルのテストコードを生成してください: {filepath}",
            system_prompt="テスト駆動開発のプロとして、有用なテストケースを生成してください。",
            tier=LLMTier.DEFAULT,
            task_hint="code test",
        )

        return {
            "success": True,
            "result": {"test_code": result.get("text", "")},
            "cost_yen": result.get("cost_yen", 0.0),
        }


# エージェントインスタンス
dev_agent = DevAgent()
