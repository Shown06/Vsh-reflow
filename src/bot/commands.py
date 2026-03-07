"""
Vsh-reflow - コマンドハンドラー
§7.1 の全12コマンドのビジネスロジック。
Discord / Telegram 両方から呼び出せるよう、Bot実装と分離。
"""

import logging
from datetime import datetime, timezone
from typing import Any, Optional

from src.approval_manager import approval_manager
from src.cost_manager import cost_manager, CostLevel
from src.database import get_session
from src.models import AgentRole, Task, TaskPriority, TaskStatus, MeetingRecord

logger = logging.getLogger(__name__)


def _generate_task_code() -> str:
    """タスクコードを生成 (TASK-YYYY-MMDD-NNN)"""
    now = datetime.now(timezone.utc)
    import random
    return f"TASK-{now.strftime('%Y-%m%d')}-{random.randint(100, 999):03d}"


def _generate_meeting_code() -> str:
    """ミーティングコードを生成"""
    now = datetime.now(timezone.utc)
    import random
    return f"MTG-{now.strftime('%Y-%m%d')}-{random.randint(100, 999):03d}"


class CommandHandler:
    """全コマンドのビジネスロジック"""

    # -------------------------------------------
    # /idea [テーマ] - アイデア出し・企画立案を指示
    # -------------------------------------------
    async def handle_idea(self, theme: str, channel_id: str = None) -> dict[str, Any]:
        """アイデア出し・企画立案をGrowth-Agentに指示"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"アイデア出し: {theme}",
                description=f"テーマ「{theme}」に関するアイデア出し・企画立案",
                task_type="idea_generation",
                assigned_agent=AgentRole.GROWTH,
                status=TaskStatus.PENDING,
                priority=TaskPriority.NORMAL,
                payload={"theme": theme},
                discord_channel_id=channel_id,
            )
            session.add(task)

        # Celeryタスクをキューに投入
        try:
            from src.workers.celery_app import dispatch_agent_task
            logger.info(f"📤 Celeryタスク投入試行: growth_queue / {task_code}")
            dispatch_agent_task.apply_async(
                args=("growth", task_code, "idea_generation", {"theme": theme}),
                queue="growth_queue"
            )
            logger.info(f"🚀 Celeryタスク投入成功: {task_code}")
        except Exception as e:
            logger.error(f"❌ Celeryタスク投入失敗: {e}", exc_info=True)
            raise

        return {
            "task_code": task_code,
            "message": f"💡 アイデア出しタスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🎯 テーマ: {theme}\n"
                       f"🤖 担当: Growth-Agent",
        }

    # -------------------------------------------
    # /research [キーワード] - 競合・トレンド調査
    # -------------------------------------------
    async def handle_research(self, keyword: str, channel_id: str = None) -> dict[str, Any]:
        """競合・トレンド調査をGrowth-Agentに指示"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"リサーチ: {keyword}",
                description=f"キーワード「{keyword}」の競合・トレンド調査",
                task_type="research",
                assigned_agent=AgentRole.GROWTH,
                status=TaskStatus.PENDING,
                payload={"keyword": keyword},
                discord_channel_id=channel_id,
            )
            session.add(task)

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.apply_async(
            args=("growth", task_code, "research", {"keyword": keyword}),
            queue="growth_queue"
        )

        return {
            "task_code": task_code,
            "message": f"🔍 リサーチタスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🔑 キーワード: {keyword}\n"
                       f"🤖 担当: Growth-Agent",
        }

    # -------------------------------------------
    # /draft [プラットフォーム] [テーマ] - 投稿下書き生成
    # -------------------------------------------
    async def handle_draft(self, platform: str, theme: str, channel_id: str = None) -> dict[str, Any]:
        """投稿下書き生成をContent-Agentに指示"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"下書き: {platform} - {theme}",
                description=f"{platform}向け投稿下書き: {theme}",
                task_type="content_draft",
                assigned_agent=AgentRole.CONTENT,
                status=TaskStatus.PENDING,
                payload={"platform": platform, "theme": theme},
                discord_channel_id=channel_id,
            )
            session.add(task)

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.apply_async(
            args=("content", task_code, "content_draft", {"platform": platform, "theme": theme}),
            queue="content_queue"
        )

        return {
            "task_code": task_code,
            "message": f"📝 下書きタスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📱 プラットフォーム: {platform}\n"
                       f"🎯 テーマ: {theme}\n"
                       f"🤖 担当: Content-Agent",
        }

    # -------------------------------------------
    # /image [説明] - 画像生成を指示
    # -------------------------------------------
    async def handle_image(self, description: str, channel_id: str = None) -> dict[str, Any]:
        """画像生成をDesign-Agentに指示"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"画像生成: {description[:50]}",
                description=f"画像生成: {description}",
                task_type="image_generation",
                assigned_agent=AgentRole.DESIGN,
                status=TaskStatus.PENDING,
                payload={"description": description},
                discord_channel_id=channel_id,
            )
            session.add(task)

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "design", task_code, "image_generation",
            {"description": description}
        )

        return {
            "task_code": task_code,
            "message": f"🎨 画像生成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🖼 説明: {description}\n"
                       f"🤖 担当: Design-Agent",
        }

    # -------------------------------------------
    # /approve [タスクID] - 承認実行
    # -------------------------------------------
    async def handle_approve(self, task_code: str) -> dict[str, Any]:
        """承認を実行"""
        request = await approval_manager.approve(task_code)
        if request:
            # 承認後、Pub-Agentに実行を指示
            from src.workers.celery_app import dispatch_agent_task
            dispatch_agent_task.delay("pub", task_code, "execute_approved", {})

            return {
                "message": f"✅ 承認しました\n"
                           f"📋 タスクID: {task_code}\n"
                           f"🚀 Pub-Agentが実行を開始します",
            }
        return {
            "message": f"❌ タスク {task_code} の承認リクエストが見つかりません",
        }

    # -------------------------------------------
    # /reject [タスクID] [理由] - 却下実行
    # -------------------------------------------
    async def handle_reject(self, task_code: str, reason: str = "") -> dict[str, Any]:
        """却下を実行"""
        request = await approval_manager.reject(task_code, reason)
        if request:
            return {
                "message": f"❌ 却下しました\n"
                           f"📋 タスクID: {task_code}\n"
                           f"📝 理由: {reason or '(未指定)'}",
            }
        return {
            "message": f"❌ タスク {task_code} の承認リクエストが見つかりません",
        }

    # -------------------------------------------
    # /edit [タスクID] [修正指示] - 修正指示
    # -------------------------------------------
    async def handle_edit(self, task_code: str, instructions: str) -> dict[str, Any]:
        """修正指示を送信"""
        request = await approval_manager.edit(task_code, instructions)
        if request:
            return {
                "message": f"✏️ 修正指示を送信しました\n"
                           f"📋 タスクID: {task_code}\n"
                           f"📝 指示: {instructions}",
            }
        return {
            "message": f"❌ タスク {task_code} の承認リクエストが見つかりません",
        }

    # -------------------------------------------
    # /status - システム稼働状態・コスト確認
    # -------------------------------------------
    async def handle_status(self) -> dict[str, Any]:
        """システム稼働状態を表示"""
        cost_report = await cost_manager.get_cost_report()
        pending = await approval_manager.get_pending_requests()

        level_emoji = {
            "normal": "🟢",
            "warning": "🟡",
            "alert": "🟠",
            "critical": "🔴",
        }

        lines = [
            "📊 【Vsh-reflow システムステータス】",
            "━━━━━━━━━━━━━━━━━━",
            f"🏷 プロジェクト: Vsh-reflow",
            f"⏰ 現在時刻: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M:%S')} UTC",
            "",
            "💰 【コスト状況】",
            f"   状態: {level_emoji.get(cost_report['level'], '⚪')} {cost_report['level'].upper()}",
            f"   月間使用: ¥{cost_report['total_yen']:,.0f} / ¥{cost_report['budget_limit_yen']:,}",
            f"   残り: ¥{cost_report['remaining_yen']:,.0f} ({100 - cost_report['usage_percent']:.1f}%)",
            "",
            f"📋 承認待ち: {len(pending)}件",
        ]

        if pending:
            for req in pending[:5]:
                lines.append(f"   - {req.summary[:50]}")

        return {"message": "\n".join(lines)}

    # -------------------------------------------
    # /budget - 月間コスト残額確認
    # -------------------------------------------
    async def handle_budget(self) -> dict[str, Any]:
        """月間コスト詳細を表示"""
        report = await cost_manager.get_cost_report()

        lines = [
            "💰 【月間コストレポート】",
            "━━━━━━━━━━━━━━━━━━",
            f"📅 期間: {report['period']}",
            f"💵 累計: ¥{report['total_yen']:,.0f}",
            f"📊 予算: ¥{report['budget_limit_yen']:,}",
            f"📉 残り: ¥{report['remaining_yen']:,.0f}",
            f"📈 使用率: {report['usage_percent']}%",
            "",
            "📋 【サービス別内訳】",
        ]

        for svc, data in report.get("by_service", {}).items():
            lines.append(f"   {svc}: ¥{data['total']:,.0f} ({data['count']}件)")

        if not report.get("by_service"):
            lines.append("   (まだコスト記録がありません)")

        return {"message": "\n".join(lines)}

    # -------------------------------------------
    # /meeting [テーマ] - AI社内会議を招集
    # -------------------------------------------
    async def handle_meeting(self, topic: str, channel_id: str = None) -> dict[str, Any]:
        """AI社内会議を招集"""
        meeting_code = _generate_meeting_code()
        participants = [
            AgentRole.PM.value,
            AgentRole.GROWTH.value,
            AgentRole.CONTENT.value,
            AgentRole.DESIGN.value,
            AgentRole.GUARD.value,
            AgentRole.ANALYST.value,
        ]

        async with get_session() as session:
            meeting = MeetingRecord(
                meeting_code=meeting_code,
                topic=topic,
                trigger="manual",
                participants=participants,
                agenda=[
                    "1. テーマ・目的の共有",
                    "2. トレンド・競合データの報告 (Growth-Agent)",
                    "3. コンテンツ案の提出 (Content-Agent)",
                    "4. デザイン案の提出 (Design-Agent)",
                    "5. リスク・コスト審査 (Guard-Agent)",
                    "6. パフォーマンス分析からの推薦 (Analyst-Agent)",
                    "7. 合意形成・承認申請書作成 (PM-Agent)",
                ],
            )
            session.add(meeting)
            
            # 会議自体もタスクとして追跡するための管理タスクを作成
            task = Task(
                task_code=meeting_code,
                title=f"AI会議: {topic}",
                description=f"AI会議の進行: {topic}",
                task_type="meeting",
                assigned_agent=AgentRole.PM,
                status=TaskStatus.PENDING,
                discord_channel_id=str(channel_id) if channel_id else None,
            )
            session.add(task)

        # PM-Agentに会議進行を指示
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "pm", meeting_code, "conduct_meeting",
            {"topic": topic, "participants": participants}
        )

        return {
            "meeting_code": meeting_code,
            "message": f"🏢 AI社内会議を招集しました\n"
                       f"📋 会議ID: {meeting_code}\n"
                       f"🎯 テーマ: {topic}\n"
                       f"👥 参加者: {', '.join(participants)}\n"
                       f"📌 PM-Agentが会議進行を開始します",
        }

    # -------------------------------------------
    # /stop - 全エージェント緊急停止
    # -------------------------------------------
    async def handle_stop(self) -> dict[str, Any]:
        """全エージェント緊急停止"""
        # Celery全タスクをrevoke
        from src.workers.celery_app import celery_app
        celery_app.control.purge()

        logger.warning("⚠️ 全エージェント緊急停止が実行されました")

        return {
            "message": "🛑 【緊急停止】\n"
                       "━━━━━━━━━━━━━━━━━━\n"
                       "全エージェントのタスクを停止しました。\n"
                       "キュー内のタスクはすべてクリアされました。\n"
                       "再開するには新しいコマンドを実行してください。",
        }

    # ============================================
    # Phase 2: AGI拡張コマンド
    # ============================================

    # -------------------------------------------
    # /browse [URL] - Webページ閲覧・要約
    # -------------------------------------------
    async def handle_browse(self, url: str, channel_id: str = None) -> dict[str, Any]:
        """Webページを閲覧して要約"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"Web閲覧: {url[:50]}",
                description=f"Webページを閲覧して要約: {url}",
                task_type="browse",
                assigned_agent=AgentRole.GROWTH,
                status=TaskStatus.PENDING,
                payload={"url": url},
                discord_channel_id=channel_id,
            )
            session.add(task)

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("browser", task_code, "browse", {"url": url})

        return {
            "task_code": task_code,
            "message": f"🌐 Web閲覧タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🔗 URL: {url}\n"
                       f"🤖 担当: Browser-Agent",
        }

    # -------------------------------------------
    # /screenshot [URL] - スクリーンショット撮影
    # -------------------------------------------
    async def handle_screenshot(self, url: str) -> dict[str, Any]:
        """Webページのスクリーンショットを撮影"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("browser", task_code, "screenshot", {"url": url})

        return {
            "task_code": task_code,
            "message": f"📸 スクリーンショットタスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🔗 URL: {url}",
        }

    # -------------------------------------------
    # /scrape [URL] [項目] - データ抽出
    # -------------------------------------------
    async def handle_scrape(self, url: str, items: str) -> dict[str, Any]:
        """Webページからデータを抽出"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "browser", task_code, "scrape",
            {"url": url, "items": items}
        )

        return {
            "task_code": task_code,
            "message": f"🔍 データ抽出タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🔗 URL: {url}\n"
                       f"📋 抽出項目: {items}",
        }

    # -------------------------------------------
    # /dev [指示] - コード生成・実行
    # -------------------------------------------
    async def handle_dev(self, instruction: str, language: str = "python", channel_id: str = None) -> dict[str, Any]:
        """コードを生成して実行"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"コード生成: {instruction[:50]}",
                description=f"コード生成・実行: {instruction}",
                task_type="code_generation",
                assigned_agent=AgentRole.CONTENT,
                status=TaskStatus.PENDING,
                payload={"instruction": instruction, "language": language},
                discord_channel_id=channel_id,
            )
            session.add(task)

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "dev", task_code, "code_generation",
            {"instruction": instruction, "language": language}
        )

        return {
            "task_code": task_code,
            "message": f"💻 コード生成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📝 指示: {instruction}\n"
                       f"🔧 言語: {language}\n"
                       f"🤖 担当: Dev-Agent",
        }

    # -------------------------------------------
    # /fix [エラー内容] - バグ修正
    # -------------------------------------------
    async def handle_fix(self, error_info: str) -> dict[str, Any]:
        """コードのバグを修正"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "dev", task_code, "code_fix",
            {"error": error_info}
        )

        return {
            "task_code": task_code,
            "message": f"🔧 バグ修正タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🐛 エラー: {error_info[:100]}",
        }

    # -------------------------------------------
    # /website [説明] - Webサイト生成
    # -------------------------------------------
    async def handle_website(self, description: str) -> dict[str, Any]:
        """Webサイトを生成"""
        task_code = _generate_task_code()

        async with get_session() as session:
            task = Task(
                task_code=task_code,
                title=f"Webサイト生成: {description[:50]}",
                description=f"Webサイト生成: {description}",
                task_type="website_generation",
                assigned_agent=AgentRole.CONTENT,
                status=TaskStatus.PENDING,
                payload={"description": description},
            )
            session.add(task)

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "web", task_code, "website_generation",
            {"description": description}
        )

        return {
            "task_code": task_code,
            "message": f"🌐 Webサイト生成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📝 説明: {description}\n"
                       f"🤖 担当: Web-Agent",
        }

    # -------------------------------------------
    # /landing [テーマ] - ランディングページ生成
    # -------------------------------------------
    async def handle_landing(self, theme: str) -> dict[str, Any]:
        """ランディングページを生成"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "web", task_code, "landing_page",
            {"theme": theme}
        )

        return {
            "task_code": task_code,
            "message": f"📄 ランディングページ生成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🎯 テーマ: {theme}\n"
                       f"🤖 担当: Web-Agent",
        }

    # -------------------------------------------
    # /preview [プロジェクト] - プレビューURL発行
    # -------------------------------------------
    async def handle_preview(self, project_code: str) -> dict[str, Any]:
        """プレビューURLを発行"""
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "deploy", project_code, "preview",
            {"project_dir": f"/app/projects/{project_code}"}
        )

        return {
            "message": f"👁 プレビュー生成中...\n"
                       f"📋 プロジェクト: {project_code}",
        }

    # -------------------------------------------
    # /deploy [プロジェクト] - 本番デプロイ
    # -------------------------------------------
    async def handle_deploy(self, project_code: str) -> dict[str, Any]:
        """プロジェクトをデプロイ"""
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "deploy", project_code, "deploy_static",
            {"project_dir": f"/app/projects/{project_code}", "task_code": project_code}
        )

        return {
            "message": f"🚀 デプロイを開始しました\n"
                       f"📋 プロジェクト: {project_code}\n"
                       f"🤖 担当: Deploy-Agent",
        }

    # -------------------------------------------
    # /listing [商品名] [説明] - EC出品テンプレート
    # -------------------------------------------
    async def handle_listing(self, product_name: str, description: str = "") -> dict[str, Any]:
        """メルカリ等の出品テンプレートを生成"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "commerce", task_code, "listing_template",
            {"product_name": product_name, "description": description}
        )

        return {
            "task_code": task_code,
            "message": f"🛍 出品テンプレート生成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📦 商品: {product_name}\n"
                       f"🤖 担当: Commerce-Agent",
        }

    # -------------------------------------------
    # /pricing [商品名] - 相場調査
    # -------------------------------------------
    async def handle_pricing(self, product_name: str) -> dict[str, Any]:
        """相場調査"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "commerce", task_code, "pricing_research",
            {"product_name": product_name}
        )

        return {
            "task_code": task_code,
            "message": f"💹 相場調査タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📦 商品: {product_name}\n"
                       f"🤖 担当: Commerce-Agent",
        }

    # ============================================
    # Phase 3: 統合拡張コマンド
    # ============================================

    # -------------------------------------------
    # /github [action] [repo] - GitHub操作
    # -------------------------------------------
    async def handle_github(self, action: str, repo: str = "", **kwargs) -> dict[str, Any]:
        """GitHub リポジトリ操作"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "github", task_code, action,
            {"repo": repo, **kwargs}
        )

        action_labels = {
            "list_repos": "📋 リポジトリ一覧取得",
            "create_repo": "📦 リポジトリ作成",
            "repo_status": "📊 リポジトリ状態確認",
        }

        return {
            "task_code": task_code,
            "message": f"🐙 {action_labels.get(action, action)}\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📦 リポジトリ: {repo or '(全体)'}\n"
                       f"🤖 担当: GitHub-Agent",
        }

    # -------------------------------------------
    # /pr [repo] [title] - PR作成
    # -------------------------------------------
    async def handle_pr(self, repo: str, title: str, head: str = "develop", base: str = "main") -> dict[str, Any]:
        """プルリクエスト作成"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "github", task_code, "create_pr",
            {"repo": repo, "title": title, "head": head, "base": base}
        )

        return {
            "task_code": task_code,
            "message": f"🔀 PR作成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📦 リポジトリ: {repo}\n"
                       f"📝 タイトル: {title}",
        }

    # -------------------------------------------
    # /issue [repo] [title] [body] - Issue作成
    # -------------------------------------------
    async def handle_issue(self, repo: str, title: str, body: str = "") -> dict[str, Any]:
        """GitHub Issue作成"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "github", task_code, "create_issue",
            {"repo": repo, "title": title, "body": body}
        )

        return {
            "task_code": task_code,
            "message": f"🐛 Issue作成タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📦 リポジトリ: {repo}\n"
                       f"📝 タイトル: {title}",
        }

    # -------------------------------------------
    # /review [repo] [PR番号] - コードレビュー
    # -------------------------------------------
    async def handle_review(self, repo: str, pr_number: int) -> dict[str, Any]:
        """PRのAIコードレビュー"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "github", task_code, "review_pr",
            {"repo": repo, "pr_number": pr_number}
        )

        return {
            "task_code": task_code,
            "message": f"🔍 AIコードレビューを開始しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📦 リポジトリ: {repo}\n"
                       f"🔀 PR #{pr_number}",
        }

    # -------------------------------------------
    # /email [to] [subject] [body] - メール送信
    # -------------------------------------------
    async def handle_email(self, to: str, subject: str, body: str) -> dict[str, Any]:
        """メール送信"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "email", task_code, "send_email",
            {"to": to, "subject": subject, "body": body}
        )

        return {
            "task_code": task_code,
            "message": f"📧 メール送信タスクを作成しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📬 宛先: {to}\n"
                       f"📝 件名: {subject}",
        }

    # -------------------------------------------
    # /inbox - 受信メール確認
    # -------------------------------------------
    async def handle_inbox(self, count: int = 10) -> dict[str, Any]:
        """受信メール確認"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "email", task_code, "read_emails",
            {"count": count, "unread_only": True}
        )

        return {
            "task_code": task_code,
            "message": f"📬 受信メール取得を開始しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📊 取得件数: {count}件",
        }

    # -------------------------------------------
    # /draft_email [目的] [宛先名] - メール文面生成
    # -------------------------------------------
    async def handle_draft_email(self, purpose: str, to_name: str = "") -> dict[str, Any]:
        """LLMでメール文面を生成"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "email", task_code, "draft_email",
            {"purpose": purpose, "to_name": to_name}
        )

        return {
            "task_code": task_code,
            "message": f"📝 メール下書き生成を開始しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📧 目的: {purpose}",
        }

    # -------------------------------------------
    # /sheets [spreadsheet_id] [action] - Google Sheets
    # -------------------------------------------
    async def handle_sheets(self, spreadsheet_id: str, action: str = "read", sheet_range: str = "Sheet1!A1:Z100") -> dict[str, Any]:
        """Google Sheets操作"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "saas", task_code, "google_sheets",
            {"spreadsheet_id": spreadsheet_id, "action": action, "range": sheet_range}
        )

        return {
            "task_code": task_code,
            "message": f"📊 Google Sheets操作を開始しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📑 アクション: {action}",
        }

    # -------------------------------------------
    # /notion [query] - Notion検索・操作
    # -------------------------------------------
    async def handle_notion(self, query: str, action: str = "search") -> dict[str, Any]:
        """Notion操作"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "saas", task_code, "notion",
            {"query": query, "action": action}
        )

        return {
            "task_code": task_code,
            "message": f"📒 Notion操作を開始しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"🔍 クエリ: {query}",
        }

    # -------------------------------------------
    # /slack [channel] [message] - Slackメッセージ
    # -------------------------------------------
    async def handle_slack(self, channel: str, text: str) -> dict[str, Any]:
        """Slackメッセージ送信"""
        task_code = _generate_task_code()

        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay(
            "saas", task_code, "slack_message",
            {"channel": channel, "text": text}
        )

        return {
            "task_code": task_code,
            "message": f"💬 Slackメッセージ送信を開始しました\n"
                       f"📋 タスクID: {task_code}\n"
                       f"📢 チャンネル: {channel}",
        }

    # ============================================
    # Phase 4: 業務拡張コマンド
    # ============================================

    # -------------------------------------------
    # /seo_audit [URL] - SEO監査
    # -------------------------------------------
    async def handle_seo_audit(self, url: str) -> dict[str, Any]:
        """サイトSEO監査"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("seo", task_code, "seo_audit", {"url": url})
        return {
            "task_code": task_code,
            "message": f"🔍 SEO監査を開始しました\n📋 タスクID: {task_code}\n🔗 URL: {url}\n🤖 担当: SEO-Agent",
        }

    # -------------------------------------------
    # /keywords [トピック] - キーワードリサーチ
    # -------------------------------------------
    async def handle_keywords(self, topic: str) -> dict[str, Any]:
        """キーワードリサーチ"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("seo", task_code, "keyword_research", {"topic": topic})
        return {
            "task_code": task_code,
            "message": f"🔎 キーワードリサーチを開始しました\n📋 タスクID: {task_code}\n🎯 トピック: {topic}",
        }

    # -------------------------------------------
    # /meta [URL] [キーワード] - メタタグ最適化
    # -------------------------------------------
    async def handle_meta(self, url: str, keyword: str = "") -> dict[str, Any]:
        """メタタグ最適化"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("seo", task_code, "meta_optimize", {"url": url, "keyword": keyword})
        return {
            "task_code": task_code,
            "message": f"🏷 メタタグ最適化を開始しました\n📋 タスクID: {task_code}\n🔗 URL: {url}",
        }

    # -------------------------------------------
    # /contact [名前] [メール] - 顧客追加
    # -------------------------------------------
    async def handle_contact(self, name: str, email: str = "", company: str = "") -> dict[str, Any]:
        """顧客追加"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("crm", task_code, "add_contact", {"name": name, "email": email, "company": company})
        return {
            "task_code": task_code,
            "message": f"👤 顧客登録を開始しました\n📋 タスクID: {task_code}\n👤 名前: {name}",
        }

    # -------------------------------------------
    # /crm [action] - CRM操作
    # -------------------------------------------
    async def handle_crm(self, action: str = "list_contacts", **kwargs) -> dict[str, Any]:
        """CRM操作"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("crm", task_code, action, kwargs)
        return {
            "task_code": task_code,
            "message": f"📇 CRM操作を開始しました\n📋 タスクID: {task_code}\n📌 アクション: {action}",
        }

    # -------------------------------------------
    # /pipeline - セールスパイプライン
    # -------------------------------------------
    async def handle_pipeline(self) -> dict[str, Any]:
        """パイプラインレポート"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("crm", task_code, "pipeline", {})
        return {
            "task_code": task_code,
            "message": f"📊 パイプラインレポート生成中\n📋 タスクID: {task_code}",
        }

    # -------------------------------------------
    # /line_msg [ユーザーID] [メッセージ] - LINE送信
    # -------------------------------------------
    async def handle_line_msg(self, user_id: str, message: str) -> dict[str, Any]:
        """LINE プッシュメッセージ"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("line", task_code, "push_message", {"user_id": user_id, "message": message})
        return {
            "task_code": task_code,
            "message": f"📱 LINEメッセージ送信を開始しました\n📋 タスクID: {task_code}",
        }

    # -------------------------------------------
    # /line_broadcast [メッセージ] - LINE一斉配信
    # -------------------------------------------
    async def handle_line_broadcast(self, message: str) -> dict[str, Any]:
        """LINE ブロードキャスト"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("line", task_code, "broadcast", {"message": message})
        return {
            "task_code": task_code,
            "message": f"📢 LINE一斉配信を開始しました\n📋 タスクID: {task_code}\n⚠️ 承認後に配信されます",
        }

    # -------------------------------------------
    # /schedule [日数] - スケジュール確認
    # -------------------------------------------
    async def handle_schedule(self, days: int = 7) -> dict[str, Any]:
        """スケジュール確認"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("schedule", task_code, "list_events", {"days": days})
        return {
            "task_code": task_code,
            "message": f"📅 今後{days}日のスケジュール取得中\n📋 タスクID: {task_code}",
        }

    # -------------------------------------------
    # /today - 今日のスケジュール
    # -------------------------------------------
    async def handle_today(self) -> dict[str, Any]:
        """今日のスケジュール"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("schedule", task_code, "daily_summary", {})
        return {
            "task_code": task_code,
            "message": f"📅 今日のスケジュール取得中\n📋 タスクID: {task_code}",
        }

    # -------------------------------------------
    # /expense [金額] [カテゴリ] [説明] - 経費追加
    # -------------------------------------------
    async def handle_expense(self, amount: int, category: str = "その他", description: str = "") -> dict[str, Any]:
        """経費追加"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("finance", task_code, "add_expense", {"amount": amount, "category": category, "description": description})
        return {
            "task_code": task_code,
            "message": f"💸 経費を記録しました\n📋 タスクID: {task_code}\n💰 金額: ¥{amount:,}\n📁 カテゴリ: {category}",
        }

    # -------------------------------------------
    # /income [金額] [ソース] - 売上追加
    # -------------------------------------------
    async def handle_income(self, amount: int, source: str = "") -> dict[str, Any]:
        """売上追加"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("finance", task_code, "add_income", {"amount": amount, "source": source})
        return {
            "task_code": task_code,
            "message": f"💰 売上を記録しました\n📋 タスクID: {task_code}\n💴 金額: ¥{amount:,}",
        }

    # -------------------------------------------
    # /invoice [クライアント名] - 請求書生成
    # -------------------------------------------
    async def handle_invoice(self, client_name: str, **kwargs) -> dict[str, Any]:
        """請求書生成"""
        task_code = _generate_task_code()
        from src.workers.celery_app import dispatch_agent_task
        dispatch_agent_task.delay("finance", task_code, "create_invoice", {"client_name": client_name, **kwargs})
        return {
            "task_code": task_code,
            "message": f"📄 請求書生成を開始しました\n📋 タスクID: {task_code}\n🏢 クライアント: {client_name}",
        }


# グローバルインスタンス
command_handler = CommandHandler()

