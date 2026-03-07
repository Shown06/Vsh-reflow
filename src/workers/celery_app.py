"""
Vsh-reflow - Celery ワーカー定義
Redis + Celery ベースのタスクキュー。定期スケジュール（Celery Beat）。
"""

import logging
from celery import Celery
from celery.schedules import crontab

from src.config import settings

logger = logging.getLogger(__name__)

# ============================================
# Celery App
# ============================================

celery_app = Celery(
    "vsh-reflow",
    broker=settings.redis.celery_broker_url,
    backend=settings.redis.celery_result_backend,
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="Asia/Tokyo",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue="default",
    task_queues={
        "pm_queue": {"exchange": "pm_queue", "routing_key": "pm"},
        "growth_queue": {"exchange": "growth_queue", "routing_key": "growth"},
        "content_queue": {"exchange": "content_queue", "routing_key": "content"},
        "design_queue": {"exchange": "design_queue", "routing_key": "design"},
        "analyst_queue": {"exchange": "analyst_queue", "routing_key": "analyst"},
        "guard_queue": {"exchange": "guard_queue", "routing_key": "guard"},
        "pub_queue": {"exchange": "pub_queue", "routing_key": "pub"},
    },
)


# ============================================
# Agent Registry
# ============================================

AGENT_MAP = {
    "pm": "src.agents.pm_agent:pm_agent",
    "growth": "src.agents.growth_agent:growth_agent",
    "content": "src.agents.content_agent:content_agent",
    "design": "src.agents.design_agent:design_agent",
    "guard": "src.agents.guard_agent:guard_agent",
    "analyst": "src.agents.analyst_agent:analyst_agent",
    "pub": "src.agents.pub_agent:pub_agent",
    # 互換性のためのエイリアス
    "pm-agent": "src.agents.pm_agent:pm_agent",
    "growth-agent": "src.agents.growth_agent:growth_agent",
    "content-agent": "src.agents.content_agent:content_agent",
    # Phase 2: AGI拡張
    "browser": "src.agents.browser_agent:browser_agent",
    "dev": "src.agents.dev_agent:dev_agent",
    "web": "src.agents.web_agent:web_agent",
    "commerce": "src.agents.commerce_agent:commerce_agent",
    "deploy": "src.agents.deploy_agent:deploy_agent",
    # Phase 3: 統合拡張
    "github": "src.agents.github_agent:github_agent",
    "email": "src.agents.email_agent:email_agent",
    "saas": "src.agents.saas_agent:saas_agent",
    # Phase 4: 業務拡張
    "seo": "src.agents.seo_agent:seo_agent",
    "crm": "src.agents.crm_agent:crm_agent",
    "line": "src.agents.line_agent:line_agent",
    "schedule": "src.agents.schedule_agent:schedule_agent",
    "finance": "src.agents.finance_agent:finance_agent",
}


def _get_agent(agent_key: str):
    """エージェントインスタンスを動的に取得"""
    module_path = AGENT_MAP.get(agent_key)
    if not module_path:
        raise ValueError(f"Unknown agent: {agent_key}")

    module_name, attr_name = module_path.rsplit(":", 1)
    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


# ============================================
# Celery Tasks
# ============================================

@celery_app.task(name="dispatch_agent_task", bind=True, max_retries=3)
def dispatch_agent_task(self, agent_key: str, task_code: str, task_type: str, payload: dict):
    """エージェントタスクをディスパッチ"""
    import asyncio
    logger.info(f"📥 [Worker] タスク受信: {agent_key}/{task_type} (code={task_code})")

    try:
        agent = _get_agent(agent_key)
        result = asyncio.run(agent.run(task_code, task_type, payload))

        logger.info(f"タスク完了: {task_code} -> {result.get('success')}")
        return result

    except Exception as e:
        logger.error(f"タスクエラー: {task_code} - {e}")
        self.retry(exc=e, countdown=60 * (self.request.retries + 1))


@celery_app.task(name="check_approval_timeouts")
def check_approval_timeouts():
    """承認タイムアウトチェック（定期実行）"""
    import asyncio

    async def _check():
        from src.approval_manager import approval_manager
        timed_out = await approval_manager.check_timeouts()
        if timed_out:
            logger.warning(f"承認タイムアウト: {len(timed_out)}件")
            for req in timed_out:
                try:
                    from src.bot.telegram_bot import send_alert
                    await send_alert(
                        f"承認タイムアウト: タスク {req.task_id} が自動キャンセルされました"
                    )
                except Exception:
                    pass

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_check())
    finally:
        loop.close()


@celery_app.task(name="check_cost_status")
def check_cost_status():
    """コスト状態チェック（定期実行）"""
    import asyncio

    async def _check():
        agent = _get_agent("guard")
        await agent.run("SYSTEM-COST-CHECK", "cost_check", {})

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(_check())
    finally:
        loop.close()


@celery_app.task(name="daily_backup_notification")
def daily_backup_notification():
    """日次バックアップ完了通知"""
    import asyncio

    async def _notify():
        try:
            from src.bot.telegram_bot import send_system_notification
            await send_system_notification("✅ 日次DBバックアップ完了")
        except Exception as e:
            logger.error(f"バックアップ通知エラー: {e}")

    asyncio.run(_notify())


@celery_app.task(name="trigger_heartbeat")
def trigger_heartbeat():
    """
    ClawdbotのHeartbeatメカニズム
    BaseAgent系の自律タスクとして、通知の確認やメモリ(記憶)の整理などを
    非同期で定期実行するエントリポイント。
    """
    import asyncio
    import uuid
    import time
    from src.workers.celery_app import dispatch_agent_task

    task_code = f"hb_{int(time.time())}_{uuid.uuid4().hex[:6]}"
    logger.info(f"❤️ Heartbeat triggered: {task_code}")
    
    # 総合管理を行うPM-AgentにHeartbeatのコンテキスト評価を依頼する
    dispatch_agent_task.delay(
        "pm", 
        task_code, 
        "heartbeat", 
        {"context": "Read HEARTBEAT.md if it exists. Evaluate current system state and notify if critical events exists. If nothing needs attention, just log HEARTBEAT_OK."}
    )


# ============================================
# Celery Beat Schedule (定期タスク)
# ============================================

celery_app.conf.beat_schedule = {
    # 承認タイムアウトチェック: 5分おき
    "check-approval-timeouts": {
        "task": "check_approval_timeouts",
        "schedule": 300.0,  # 5 minutes
    },
    # コスト状態チェック: 1時間おき
    "check-cost-status": {
        "task": "check_cost_status",
        "schedule": 3600.0,  # 1 hour
    },
    # 日次バックアップ通知: 毎日深夜2時30分
    "daily-backup-notification": {
        "task": "daily_backup_notification",
        "schedule": crontab(hour=2, minute=30),
    },
    # Clawdbot Heartbeat: 30分おき
    "clawdbot-heartbeat-30m": {
        "task": "trigger_heartbeat",
        "schedule": 1800.0,  # 30 minutes
    },
}

# ============================================
# 初期化: Celery Worker 起動完了後に全エージェントの Presence を報告
# ============================================
from celery.signals import worker_ready

@worker_ready.connect
def on_worker_ready(**kwargs):
    """ワーカー起動完了後に全エージェントのPresenceをRedisへ報告"""
    import redis as redis_lib
    import json
    from datetime import datetime, timezone

    logger.info("🏢 Virtual Office: Registering all agents presence...")
    try:
        r = redis_lib.Redis.from_url(f"redis://redis:6379/0", socket_timeout=5)
        for key, module_path in AGENT_MAP.items():
            try:
                agent = _get_agent(key)
                data = {
                    "name": agent.name,
                    "role": agent.role.value if hasattr(agent.role, "value") else str(agent.role),
                    "status": "idle",
                    "task": "",
                    "thought": "起動完了。待機中です。",
                    "last_seen": datetime.now(timezone.utc).isoformat()
                }
                r.set(f"vsh:agent:{agent.name}", json.dumps(data), ex=600)
                logger.info(f"  ✅ {agent.name} registered in virtual office")
            except Exception as e:
                logger.warning(f"  ❌ Failed to register {key}: {e}")
        logger.info("🏢 Virtual Office: All agents registered!")
    except Exception as e:
        logger.error(f"🏢 Virtual Office: Failed to connect to Redis: {e}")
