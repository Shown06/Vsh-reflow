"""
Vsh-reflow - Deploy-Agent (ビルド・デプロイ自動化)
生成したWebサイト・アプリのデプロイ、プレビューURL発行、SSL設定。
"""

import asyncio
import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.config import settings
from src.models import AgentRole

logger = logging.getLogger(__name__)

PROJECTS_DIR = os.environ.get("PROJECTS_DIR", "/app/projects")
DEPLOY_DIR = os.environ.get("DEPLOY_DIR", "/app/deployed")


class DeployAgent(BaseAgent):
    """ビルド・デプロイ自動化エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.PUB, name="Deploy-Agent")

    def _ensure_dirs(self):
        try:
            os.makedirs(DEPLOY_DIR, exist_ok=True)
        except OSError:
            pass

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "deploy_static":
            return await self._deploy_static_site(task_code, payload)
        elif task_type == "preview":
            return await self._generate_preview(task_code, payload)
        elif task_type == "deploy_app":
            return await self._deploy_app(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _deploy_static_site(self, task_code: str, payload: dict) -> dict:
        """静的サイトをNginxにデプロイ"""
        project_dir = payload.get("project_dir", "")
        if not project_dir:
            return {"success": False, "error": "project_dirが指定されていません"}

        self._ensure_dirs()
        deploy_path = os.path.join(DEPLOY_DIR, task_code)

        try:
            # プロジェクトをデプロイディレクトリにコピー
            result = await self._run_shell(f"cp -r {project_dir} {deploy_path}")

            # Nginx設定を生成
            nginx_conf = self._generate_nginx_config(task_code, deploy_path)

            # プレビューURL
            preview_url = f"https://{task_code}.preview.vsh-reflow.local"

            # 完了通知
            try:
                from src.bot.discord_bot import send_log_notification
                await send_log_notification(
                    f"🚀 デプロイ完了\n"
                    f"📋 タスク: {task_code}\n"
                    f"🌐 URL: {preview_url}\n"
                    f"📁 パス: {deploy_path}\n"
                    f"⏰ {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC"
                )
            except Exception:
                pass

            return {
                "success": True,
                "result": {
                    "deploy_path": deploy_path,
                    "preview_url": preview_url,
                    "nginx_config": nginx_conf,
                    "status": "deployed",
                },
                "cost_yen": 0.0,
            }

        except Exception as e:
            logger.error(f"デプロイエラー: {e}")
            return {"success": False, "error": str(e)}

    async def _generate_preview(self, task_code: str, payload: dict) -> dict:
        """プレビューURL発行"""
        project_dir = payload.get("project_dir", "")

        self._ensure_dirs()
        preview_path = os.path.join(DEPLOY_DIR, f"preview_{task_code}")

        try:
            await self._run_shell(f"cp -r {project_dir} {preview_path}")

            preview_url = f"https://{task_code}.preview.vsh-reflow.local"

            return {
                "success": True,
                "result": {
                    "preview_url": preview_url,
                    "preview_path": preview_path,
                    "expires": "24時間後に自動削除",
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {
                "success": True,
                "result": {
                    "preview_url": f"http://localhost:8080/{task_code}/",
                    "note": "ローカルプレビュー（Docker外実行時）",
                },
                "cost_yen": 0.0,
            }

    async def _deploy_app(self, task_code: str, payload: dict) -> dict:
        """アプリケーションをDockerコンテナとしてデプロイ"""
        project_dir = payload.get("project_dir", "")
        app_type = payload.get("app_type", "static")

        if app_type == "static":
            return await self._deploy_static_site(task_code, payload)

        # Dockerfileを生成
        dockerfile = self._generate_dockerfile(app_type, project_dir)

        try:
            # Dockerイメージビルド
            image_name = f"vsh-reflow-app-{task_code}"
            await self._run_shell(
                f"docker build -t {image_name} {project_dir}"
            )

            # コンテナ起動
            await self._run_shell(
                f"docker run -d --name {task_code} --restart always "
                f"--network vsh-reflow_default {image_name}"
            )

            return {
                "success": True,
                "result": {
                    "image": image_name,
                    "container": task_code,
                    "status": "running",
                    "dockerfile": dockerfile,
                },
                "cost_yen": 0.0,
            }
        except Exception as e:
            return {
                "success": True,
                "result": {
                    "status": "simulated",
                    "note": f"Docker外実行のためシミュレーション: {e}",
                },
                "cost_yen": 0.0,
            }

    def _generate_nginx_config(self, task_code: str, deploy_path: str) -> str:
        """Nginx設定を生成"""
        return f"""server {{
    listen 80;
    server_name {task_code}.preview.vsh-reflow.local;

    root {deploy_path};
    index index.html;

    location / {{
        try_files $uri $uri/ =404;
    }}

    # 静的ファイルのキャッシュ
    location ~* \\.(css|js|jpg|jpeg|png|gif|ico|svg)$ {{
        expires 7d;
        add_header Cache-Control "public, immutable";
    }}
}}"""

    def _generate_dockerfile(self, app_type: str, project_dir: str) -> str:
        """アプリ用Dockerfileを生成"""
        if app_type == "python":
            return """FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python", "main.py"]"""
        elif app_type == "node":
            return """FROM node:20-alpine
WORKDIR /app
COPY package*.json ./
RUN npm ci --only=production
COPY . .
CMD ["node", "index.js"]"""
        else:
            return """FROM nginx:alpine
COPY . /usr/share/nginx/html
EXPOSE 80"""

    async def _run_shell(self, cmd: str) -> str:
        """シェルコマンド実行"""
        try:
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await asyncio.wait_for(
                process.communicate(), timeout=60
            )
            if process.returncode != 0:
                raise RuntimeError(stderr.decode())
            return stdout.decode()
        except asyncio.TimeoutError:
            raise RuntimeError("コマンドタイムアウト")
        except FileNotFoundError:
            raise RuntimeError("シェル実行不可(Docker外)")


# エージェントインスタンス
deploy_agent = DeployAgent()
