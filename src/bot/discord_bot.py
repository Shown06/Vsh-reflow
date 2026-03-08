"""
Vsh-reflow - Discord Bot
§7 準拠。全コマンド対応、通知チャンネル管理。
"""

import asyncio
import logging
import os
import threading

import discord
from discord import app_commands
from discord.ext import commands, tasks

from src.config import settings
from src.bot.commands import command_handler
from src.database import init_db
from src.health import start_health_server

logger = logging.getLogger(__name__)

# ============================================
# Bot Setup
# ============================================

intents = discord.Intents.default()
intents.message_content = True
intents.guilds = True

bot = commands.Bot(
    command_prefix="!",
    intents=intents,
    description="Vsh-reflow - AI社内チーム自律運用システム",
)


def is_owner():
    """オーナー認証デコレータ"""
    async def predicate(interaction: discord.Interaction) -> bool:
        if settings.discord.owner_id:
            return interaction.user.id == settings.discord.owner_id
        return True  # owner_id未設定時は全ユーザー許可
    return app_commands.check(predicate)


# ============================================
# Events
# ============================================

@bot.event
async def on_ready():
    logger.info(f"✅ Bot起動: {bot.user} (ID: {bot.user.id})")
    logger.info(f"📡 サーバー数: {len(bot.guilds)}")

    # DB初期化
    await init_db()

    # スラッシュコマンド同期
    if settings.discord.guild_id:
        guild = discord.Object(id=settings.discord.guild_id)
        bot.tree.copy_global_to(guild=guild)
        await bot.tree.sync(guild=guild)
    else:
        await bot.tree.sync()

    logger.info("✅ スラッシュコマンド同期完了")

    # 定期タスク開始
    approval_checker.start()
    task_result_observer.start()


@bot.event
async def on_command_error(ctx, error):
    logger.error(f"コマンドエラー: {error}")


# ============================================
# Slash Commands (§7.1)
# ============================================

@bot.tree.command(name="idea", description="アイデア出し・企画立案を指示")
@is_owner()
@app_commands.describe(theme="企画テーマ")
async def cmd_idea(interaction: discord.Interaction, theme: str):
    logger.info(f"📥 [Discord] コマンド受信: /idea theme={theme} (user={interaction.user})")
    await interaction.response.defer()
    try:
        result = await command_handler.handle_idea(theme, channel_id=str(interaction.channel_id))
        logger.info(f"✅ [Discord] /idea 処理完了: {result.get('task_code')}")
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /idea エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="research", description="競合・トレンド調査を指示")
@is_owner()
@app_commands.describe(keyword="調査キーワード")
async def cmd_research(interaction: discord.Interaction, keyword: str):
    await interaction.response.defer()
    try:
        result = await command_handler.handle_research(keyword, channel_id=str(interaction.channel_id))
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /research エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="draft", description="投稿下書き生成")
@is_owner()
@app_commands.describe(platform="プラットフォーム (X, Instagram等)", theme="投稿テーマ")
async def cmd_draft(interaction: discord.Interaction, platform: str, theme: str):
    await interaction.response.defer()
    try:
        result = await command_handler.handle_draft(platform, theme, channel_id=str(interaction.channel_id))
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /draft エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="image", description="画像生成を指示")
@is_owner()
@app_commands.describe(description="画像の説明")
async def cmd_image(interaction: discord.Interaction, description: str):
    await interaction.response.defer()
    try:
        result = await command_handler.handle_image(description, channel_id=str(interaction.channel_id))
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /image エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="approve", description="タスクを承認")
@is_owner()
@app_commands.describe(task_code="タスクID")
async def cmd_approve(interaction: discord.Interaction, task_code: str):
    await interaction.response.defer()
    try:
        result = await command_handler.handle_approve(task_code)
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /approve エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="reject", description="タスクを却下")
@is_owner()
@app_commands.describe(task_code="タスクID", reason="却下理由")
async def cmd_reject(interaction: discord.Interaction, task_code: str, reason: str = ""):
    await interaction.response.defer()
    try:
        result = await command_handler.handle_reject(task_code, reason)
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /reject エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="edit", description="修正指示を送信")
@is_owner()
@app_commands.describe(task_code="タスクID", instructions="修正指示")
async def cmd_edit(interaction: discord.Interaction, task_code: str, instructions: str):
    await interaction.response.defer()
    try:
        result = await command_handler.handle_edit(task_code, instructions)
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /edit エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="status", description="システム稼働状態・コスト確認")
@is_owner()
async def cmd_status(interaction: discord.Interaction):
    await interaction.response.defer()
    result = await command_handler.handle_status()
    await interaction.followup.send(result["message"])


@bot.tree.command(name="budget", description="月間コスト残額確認")
@is_owner()
async def cmd_budget(interaction: discord.Interaction):
    await interaction.response.defer()
    result = await command_handler.handle_budget()
    await interaction.followup.send(result["message"])


@bot.tree.command(name="meeting", description="AI社内会議を招集")
@is_owner()
@app_commands.describe(topic="会議テーマ")
async def cmd_meeting(interaction: discord.Interaction, topic: str):
    logger.info(f"📥 [Discord] コマンド受信: /meeting topic={topic[:50]}... (user={interaction.user})")
    await interaction.response.defer()
    try:
        result = await command_handler.handle_meeting(topic, channel_id=str(interaction.channel_id))
        logger.info(f"✅ [Discord] /meeting 処理完了")
        await interaction.followup.send(result["message"])
    except Exception as e:
        logger.error(f"❌ [Discord] /meeting エラー: {e}", exc_info=True)
        error_msg = f"⚠️ エラーが発生しました: {e}"
        await interaction.followup.send(error_msg[:1900])


@bot.tree.command(name="stop", description="全エージェント緊急停止")
@is_owner()
async def cmd_stop(interaction: discord.Interaction):
    await interaction.response.defer()
    result = await command_handler.handle_stop()
    await interaction.followup.send(result["message"])


@bot.tree.command(name="report", description="週次パフォーマンスレポート生成")
@is_owner()
async def cmd_report(interaction: discord.Interaction):
    await interaction.response.defer()
    result = await command_handler.handle_report()
    await interaction.followup.send(result["message"])


# ============================================
# 通知ヘルパー (§7.2)
# ============================================

async def send_to_channel(channel_id: int, message: str, embed: discord.Embed = None):
    """指定チャンネルにメッセージを送信"""
    if not channel_id:
        logger.warning("チャンネルIDが設定されていません")
        return
    channel = bot.get_channel(channel_id)
    if channel:
        if embed:
            await channel.send(content=message, embed=embed)
        else:
            await channel.send(message)
    else:
        logger.error(f"チャンネル {channel_id} が見つかりません")


async def send_approval_notification(message: str):
    """承認チャンネルに通知"""
    if settings.discord.approvals_channel_id:
        await send_to_channel(settings.discord.approvals_channel_id, message)


async def send_alert_notification(message: str):
    """アラートチャンネルに通知"""
    if settings.discord.alerts_channel_id:
        await send_to_channel(settings.discord.alerts_channel_id, message)


async def send_report_notification(message: str):
    """レポートチャンネルに通知"""
    if settings.discord.reports_channel_id:
        await send_to_channel(settings.discord.reports_channel_id, message)


async def send_log_notification(message: str):
    """ログチャンネルに通知"""
    if settings.discord.logs_channel_id:
        await send_to_channel(settings.discord.logs_channel_id, message)


# ============================================
# 定期タスク
# ============================================

@tasks.loop(minutes=5)
async def approval_checker():
    """承認タイムアウト・リマインドチェック (5分おき)"""
    try:
        from src.approval_manager import approval_manager

        # タイムアウトチェック
        timed_out = await approval_manager.check_timeouts()
        for req in timed_out:
            await send_alert_notification(
                f"⏰ 承認タイムアウト: タスクが自動キャンセルされました\n"
                f"タスクID: {req.task_id}"
            )

        # リマインドチェック
        needs_reminder = await approval_manager.get_requests_needing_reminder()
        for reminder_type, req in needs_reminder:
            if reminder_type == "first":
                await send_approval_notification(
                    f"⏰ リマインド: 承認待ちのタスクがあります\n"
                    f"{req.summary[:100]}"
                )
            elif reminder_type == "second":
                await send_approval_notification(
                    f"🔔 2回目リマインド: まだ承認待ちです\n"
                    f"{req.summary[:100]}"
                )
    except Exception as e:
        logger.error(f"承認チェッカーエラー: {e}")


@tasks.loop(seconds=10)
async def task_result_observer():
    """タスク完了監視ループ (10秒おき)"""
    try:
        from sqlalchemy import select, update
        from src.database import get_session
        from src.models import Task, TaskStatus

        async with get_session() as session:
            # 完了または失敗した未通知のタスクを取得
            stmt = select(Task).where(
                Task.status.in_([TaskStatus.COMPLETED, TaskStatus.FAILED]),
                Task.notified == False,
                Task.discord_channel_id != None
            ).order_by(Task.completed_at.asc())
            
            result = await session.execute(stmt)
            tasks_to_notify = result.scalars().all()
            
            for task in tasks_to_notify:
                try:
                    channel_id = int(task.discord_channel_id)
                    channel = bot.get_channel(channel_id)
                    if not channel:
                        # チャンネルがキャッシュにない場合はfetch
                        try:
                            channel = await bot.fetch_channel(channel_id)
                        except:
                            logger.warning(f"チャンネル {channel_id} が取得できません。スキップします。")
                            task.notified = True # 取得不能なら諦める
                            continue

                    if task.status == TaskStatus.COMPLETED:
                        # 結果の整形
                        res_data = task.result or {}
                        # content_agent等の結果は 'ideas', 'research_report' 等のキー、または 'result' キーに入っている可能性がある
                        main_text = ""
                        
                        # 既知のキーを優先的に探す
                        prioritized_keys = [
                            "agenda", "research", "content_proposals", "design_proposals", 
                            "guard_review", "analysis", "ideas", "research_report", 
                            "draft", "image_url", "result"
                        ]
                        found_content = False
                        
                        for key in prioritized_keys:
                            if key in res_data and res_data[key]:
                                if isinstance(res_data[key], str):
                                    main_text = res_data[key]
                                    
                                    # 会議用の装飾
                                    emoji = "✅"
                                    if key == "agenda": emoji = "📅 【アジェンダ】"
                                    elif key == "research": emoji = "🔍 【リサーチ報告】"
                                    elif key == "content_proposals": emoji = "📝 【コンテンツ案】"
                                    elif key == "design_proposals": emoji = "🎨 【デザイン案】"
                                    elif key == "guard_review": emoji = "🛡️ 【リスク・コスト審査】"
                                    elif key == "analysis": emoji = "📊 【分析報告】"
                                    
                                    task.title = f"{emoji} {task.title}"
                                    found_content = True
                                    break
                        
                        # 見つからない場合は全文字列を結合
                        if not found_content:
                            for val in res_data.values():
                                if isinstance(val, str):
                                    main_text += val + "\n"
                        
                        if not main_text:
                            main_text = "(詳細な結果データがありません)"
                        
                        header = (
                            f"✅ **タスク完了報告**\n"
                            f"📋 タスクID: `{task.task_code}`\n"
                            f"🎯 タイトル: {task.title}\n"
                            f"🤖 担当: {task.assigned_agent.value if hasattr(task.assigned_agent, 'value') else task.assigned_agent}\n"
                            f"━━━━━━━━━━━━━━━━━━\n"
                        )
                        
                        # Discord制限対策と分割送信
                        if len(header + main_text) > 2000:
                            await channel.send(header)
                            chunks = [main_text[i:i+1900] for i in range(0, len(main_text), 1900)]
                            for i, chunk in enumerate(chunks):
                                await channel.send(f"--- 続き({i+1}/{len(chunks)}) ---\n{chunk}")
                        else:
                            await channel.send(header + main_text)
                            
                        # PDFファイルのアップロード指示があれば実行
                        if "pdf_path" in res_data and res_data["pdf_path"]:
                            pdf_path = res_data["pdf_path"]
                            if os.path.exists(pdf_path):
                                import discord
                                await channel.send(
                                    content="📄 **【プレゼン資料】制作完了**\n会議の結果をまとめたPDF資料を作成しました。ダウンロードしてご確認ください。",
                                    file=discord.File(pdf_path)
                                )
                    else:
                        msg = (
                            f"❌ **タスク失敗報告**\n"
                            f"📋 タスクID: `{task.task_code}`\n"
                            f"🎯 タイトル: {task.title}\n"
                            f"⚠️ エラー: {task.error_message}"
                        )
                        await channel.send(msg)
                    
                    # 通知済みフラグを立てる
                    task.notified = True
                    # セッションをコミットしてDBに反映させる
                    await session.commit()
                except Exception as ex:
                    logger.error(f"タスク結果個席通知エラー ({task.task_code}): {ex}")
            
    except Exception as e:
        logger.error(f"タスク結果監視ループ エラー: {e}")


@approval_checker.before_loop
async def before_approval_checker():
    await bot.wait_until_ready()


# ============================================
# Entry Point
# ============================================

def main():
    """Bot起動"""
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not settings.discord.bot_token:
        logger.error("❌ DISCORD_BOT_TOKEN が設定されていません")
        return

    # ヘルスチェックサーバーをバックグラウンドで起動
    health_thread = threading.Thread(
        target=start_health_server,
        args=(settings.health_check_port,),
        daemon=True,
    )
    health_thread.start()

    logger.info("🚀 Vsh-reflow Discord Bot を起動中...")
    bot.run(settings.discord.bot_token)


if __name__ == "__main__":
    main()
