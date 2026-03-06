"""
Vsh-reflow - Telegram Bot (通知専用)
緊急アラート・承認リマインドをTelegramにも送信。
"""

import asyncio
import logging
from typing import Optional

from src.config import settings

logger = logging.getLogger(__name__)

# telegram bot は通知専用のため、軽量実装
_bot_instance = None


async def get_telegram_bot():
    """Telegram Botインスタンスを取得（遅延初期化）"""
    global _bot_instance
    if _bot_instance is None and settings.telegram.bot_token:
        try:
            from telegram import Bot
            _bot_instance = Bot(token=settings.telegram.bot_token)
        except ImportError:
            logger.warning("python-telegram-bot がインストールされていません")
        except Exception as e:
            logger.error(f"Telegram Bot初期化エラー: {e}")
    return _bot_instance


async def send_telegram_message(
    text: str,
    chat_id: Optional[str] = None,
    parse_mode: str = "HTML",
) -> bool:
    """Telegramにメッセージを送信"""
    bot = await get_telegram_bot()
    if not bot:
        logger.debug("Telegram Bot未設定 - メッセージをスキップ")
        return False

    target_chat_id = chat_id or settings.telegram.chat_id
    if not target_chat_id:
        logger.warning("Telegram chat_id が設定されていません")
        return False

    try:
        await bot.send_message(
            chat_id=target_chat_id,
            text=text,
            parse_mode=parse_mode,
        )
        logger.info(f"Telegram通知送信完了: {text[:50]}...")
        return True
    except Exception as e:
        logger.error(f"Telegram送信エラー: {e}")
        return False


async def send_alert(message: str) -> bool:
    """緊急アラートをTelegramに送信"""
    return await send_telegram_message(f"🚨 <b>Vsh-reflow Alert</b>\n\n{message}")


async def send_approval_reminder(task_code: str, summary: str) -> bool:
    """承認リマインドをTelegramに送信"""
    text = (
        f"⏰ <b>承認リマインド</b>\n\n"
        f"タスクID: <code>{task_code}</code>\n"
        f"内容: {summary}\n\n"
        f"Discord で /approve {task_code} を実行してください"
    )
    return await send_telegram_message(text)


async def send_system_notification(message: str) -> bool:
    """システム通知をTelegramに送信"""
    return await send_telegram_message(f"ℹ️ <b>Vsh-reflow</b>\n\n{message}")


async def send_cost_alert(level: str, total_yen: float, limit_yen: float) -> bool:
    """コストアラートをTelegramに送信"""
    emoji = {"warning": "⚠️", "alert": "🟠", "critical": "🔴"}.get(level, "ℹ️")
    text = (
        f"{emoji} <b>コストアラート [{level.upper()}]</b>\n\n"
        f"月間累計: ¥{total_yen:,.0f}\n"
        f"予算上限: ¥{limit_yen:,.0f}\n"
        f"使用率: {(total_yen/limit_yen)*100:.1f}%"
    )
    return await send_telegram_message(text)


# ============================================
# Entry Point (スタンドアロン実行用)
# ============================================

def main():
    """Telegram Bot通知サービス起動"""
    logging.basicConfig(
        level=getattr(logging, settings.log_level),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if not settings.telegram.bot_token:
        logger.error("❌ TELEGRAM_BOT_TOKEN が設定されていません")
        return

    logger.info("🚀 Vsh-reflow Telegram Bot (通知専用) 待機中...")

    # メインループ - ヘルスチェックとして定期的にping
    async def keep_alive():
        while True:
            bot = await get_telegram_bot()
            if bot:
                try:
                    me = await bot.get_me()
                    logger.debug(f"Telegram Bot alive: @{me.username}")
                except Exception as e:
                    logger.error(f"Telegram health check failed: {e}")
            await asyncio.sleep(60)

    asyncio.run(keep_alive())


if __name__ == "__main__":
    main()
