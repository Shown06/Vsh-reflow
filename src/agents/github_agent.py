"""
Vsh-reflow - GitHub-Agent (リポジトリ管理・PR・Issue・コードレビュー)
GitHub API 経由でリポジトリ操作を完全自動化。
"""

import logging
import os
from datetime import datetime, timezone
from typing import Any, Optional

from src.agents.base_agent import BaseAgent
from src.cost_manager import LLMTier
from src.config import settings
from src.models import AgentRole

logger = logging.getLogger(__name__)


class GitHubAgent(BaseAgent):
    """GitHub連携エージェント"""

    def __init__(self):
        super().__init__(role=AgentRole.CONTENT, name="GitHub-Agent")
        self._token = os.environ.get("GITHUB_TOKEN", "")
        self._default_owner = os.environ.get("GITHUB_OWNER", "")

    def _get_headers(self) -> dict:
        return {
            "Authorization": f"token {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _github_api(self, method: str, endpoint: str, json_data: dict = None) -> dict:
        """GitHub REST API 呼び出し"""
        import httpx
        url = f"https://api.github.com{endpoint}"
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.request(
                method, url,
                headers=self._get_headers(),
                json=json_data,
            )
            if response.status_code >= 400:
                return {"error": f"GitHub API Error {response.status_code}: {response.text[:500]}"}
            return response.json() if response.text else {}

    async def execute_task(self, task_code: str, task_type: str, payload: dict) -> dict:
        if task_type == "create_repo":
            return await self._create_repo(task_code, payload)
        elif task_type == "create_pr":
            return await self._create_pr(task_code, payload)
        elif task_type == "create_issue":
            return await self._create_issue(task_code, payload)
        elif task_type == "review_pr":
            return await self._review_pr(task_code, payload)
        elif task_type == "push_code":
            return await self._push_code(task_code, payload)
        elif task_type == "list_repos":
            return await self._list_repos(task_code, payload)
        elif task_type == "repo_status":
            return await self._repo_status(task_code, payload)
        else:
            return {"success": False, "error": f"Unknown task type: {task_type}"}

    async def _create_repo(self, task_code: str, payload: dict) -> dict:
        """リポジトリ作成"""
        name = payload.get("name", "")
        description = payload.get("description", "")
        private = payload.get("private", True)

        if not self._token:
            return {"success": False, "error": "GITHUB_TOKEN未設定"}

        result = await self._github_api("POST", "/user/repos", {
            "name": name,
            "description": description,
            "private": private,
            "auto_init": True,
        })

        if "error" in result:
            return {"success": False, "error": result["error"]}

        return {
            "success": True,
            "result": {
                "repo_url": result.get("html_url", ""),
                "clone_url": result.get("clone_url", ""),
                "name": name,
                "private": private,
            },
            "cost_yen": 0.0,
        }

    async def _create_pr(self, task_code: str, payload: dict) -> dict:
        """プルリクエスト作成"""
        repo = payload.get("repo", "")
        title = payload.get("title", "")
        body = payload.get("body", "")
        head = payload.get("head", "develop")
        base = payload.get("base", "main")
        owner = payload.get("owner", self._default_owner)

        # LLMでPR説明文を生成
        if not body:
            llm_result = await self.call_llm(
                prompt=f"以下のプルリクエストの説明文を生成してください。\nタイトル: {title}\nリポジトリ: {repo}",
                system_prompt="GitHub PRの説明文を日本語で丁寧に書いてください。変更点、理由、テスト方法を含めてください。",
                tier=LLMTier.DEFAULT,
                task_hint="code dev",
            )
            body = llm_result.get("text", "")

        result = await self._github_api("POST", f"/repos/{owner}/{repo}/pulls", {
            "title": title,
            "body": body,
            "head": head,
            "base": base,
        })

        if "error" in result:
            return {"success": False, "error": result["error"]}

        return {
            "success": True,
            "result": {
                "pr_url": result.get("html_url", ""),
                "pr_number": result.get("number", 0),
                "title": title,
            },
            "cost_yen": 0.0,
        }

    async def _create_issue(self, task_code: str, payload: dict) -> dict:
        """Issue作成"""
        repo = payload.get("repo", "")
        title = payload.get("title", "")
        body = payload.get("body", "")
        labels = payload.get("labels", [])
        owner = payload.get("owner", self._default_owner)

        result = await self._github_api("POST", f"/repos/{owner}/{repo}/issues", {
            "title": title,
            "body": body,
            "labels": labels,
        })

        if "error" in result:
            return {"success": False, "error": result["error"]}

        return {
            "success": True,
            "result": {
                "issue_url": result.get("html_url", ""),
                "issue_number": result.get("number", 0),
            },
            "cost_yen": 0.0,
        }

    async def _review_pr(self, task_code: str, payload: dict) -> dict:
        """PRのコードレビュー"""
        repo = payload.get("repo", "")
        pr_number = payload.get("pr_number", 0)
        owner = payload.get("owner", self._default_owner)

        # PRの差分を取得
        diff_result = await self._github_api("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}")
        if "error" in diff_result:
            return {"success": False, "error": diff_result["error"]}

        # ファイル変更を取得
        files_result = await self._github_api("GET", f"/repos/{owner}/{repo}/pulls/{pr_number}/files")

        # LLMでレビュー
        files_summary = ""
        if isinstance(files_result, list):
            for f in files_result[:10]:
                files_summary += f"\n--- {f.get('filename', '')} ({f.get('status', '')}) ---\n"
                files_summary += (f.get("patch", ""))[:1000] + "\n"

        review = await self.call_llm(
            prompt=f"""以下のPRをレビューしてください。

PR: {diff_result.get('title', '')}
説明: {diff_result.get('body', '')[:500]}

変更ファイル:
{files_summary[:5000]}

以下を含むレビューを書いてください:
1. 全体的な評価
2. 良い点
3. 改善が必要な点
4. バグの可能性
5. 承認推奨 or 修正リクエスト""",
            system_prompt="シニアエンジニアとして厳密かつ建設的なコードレビューを行ってください。",
            tier=LLMTier.IMPORTANT,
            task_hint="code review",
        )

        # レビューコメントを投稿
        await self._github_api("POST", f"/repos/{owner}/{repo}/pulls/{pr_number}/reviews", {
            "body": review.get("text", ""),
            "event": "COMMENT",
        })

        return {
            "success": True,
            "result": {
                "review": review.get("text", ""),
                "pr_number": pr_number,
                "repo": repo,
            },
            "cost_yen": review.get("cost_yen", 0.0),
        }

    async def _push_code(self, task_code: str, payload: dict) -> dict:
        """コードをリポジトリにプッシュ"""
        repo = payload.get("repo", "")
        filepath = payload.get("filepath", "")
        content = payload.get("content", "")
        message = payload.get("message", f"auto: {task_code}")
        branch = payload.get("branch", "main")
        owner = payload.get("owner", self._default_owner)

        import base64
        encoded = base64.b64encode(content.encode()).decode()

        # 既存ファイルのSHA取得（更新時に必要）
        existing = await self._github_api("GET", f"/repos/{owner}/{repo}/contents/{filepath}?ref={branch}")
        sha = existing.get("sha") if isinstance(existing, dict) and "sha" in existing else None

        data = {
            "message": message,
            "content": encoded,
            "branch": branch,
        }
        if sha:
            data["sha"] = sha

        result = await self._github_api("PUT", f"/repos/{owner}/{repo}/contents/{filepath}", data)

        if "error" in result:
            return {"success": False, "error": result["error"]}

        return {
            "success": True,
            "result": {
                "filepath": filepath,
                "repo": f"{owner}/{repo}",
                "commit_sha": result.get("commit", {}).get("sha", ""),
            },
            "cost_yen": 0.0,
        }

    async def _list_repos(self, task_code: str, payload: dict) -> dict:
        """リポジトリ一覧"""
        result = await self._github_api("GET", "/user/repos?sort=updated&per_page=20")

        if isinstance(result, dict) and "error" in result:
            return {"success": False, "error": result["error"]}

        repos = []
        if isinstance(result, list):
            for r in result:
                repos.append({
                    "name": r.get("full_name", ""),
                    "url": r.get("html_url", ""),
                    "private": r.get("private", False),
                    "updated": r.get("updated_at", ""),
                })

        return {
            "success": True,
            "result": {"repos": repos, "count": len(repos)},
            "cost_yen": 0.0,
        }

    async def _repo_status(self, task_code: str, payload: dict) -> dict:
        """リポジトリの状態確認"""
        repo = payload.get("repo", "")
        owner = payload.get("owner", self._default_owner)

        repo_info = await self._github_api("GET", f"/repos/{owner}/{repo}")
        prs = await self._github_api("GET", f"/repos/{owner}/{repo}/pulls?state=open")
        issues = await self._github_api("GET", f"/repos/{owner}/{repo}/issues?state=open")

        return {
            "success": True,
            "result": {
                "repo": f"{owner}/{repo}",
                "default_branch": repo_info.get("default_branch", "main") if isinstance(repo_info, dict) else "main",
                "open_prs": len(prs) if isinstance(prs, list) else 0,
                "open_issues": len(issues) if isinstance(issues, list) else 0,
                "stars": repo_info.get("stargazers_count", 0) if isinstance(repo_info, dict) else 0,
            },
            "cost_yen": 0.0,
        }


# エージェントインスタンス
github_agent = GitHubAgent()
