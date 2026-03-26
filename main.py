"""
Telegram Trading Bot - Main Entry Point
Run this file to start the bot.
"""

import asyncio
import logging
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
)

from config.settings import BOT_TOKEN, LOG_LEVEL
from database.db import init_db
from bot.user_handlers import UserHandlers
from bot.admin_handlers import AdminHandlers
from bot.deposit_monitor import DepositMonitor
from bot.trade_broadcaster import TradeBroadcaster

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    handlers=[
        logging.FileHandler("bot.log"),
        logging.StreamHandler(),
    ],
)
logger = logging.getLogger(__name__)


async def post_init(application: Application) -> None:
    """Called once after bot is initialised."""
    await init_db()
    logger.info("Database initialised.")

    # Start background deposit monitor
    deposit_monitor = DepositMonitor(application.bot)
    application.create_task(deposit_monitor.run())

    # Start trade broadcaster
    broadcaster = TradeBroadcaster(application.bot)
    application.create_task(broadcaster.run())

    logger.info("Background tasks started.")


def main() -> None:
    if not BOT_TOKEN:
        raise ValueError("BOT_TOKEN is not set. Check your .env file.")

    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    user = UserHandlers()
    admin = AdminHandlers()

    # ── User commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",    user.cmd_start))
    app.add_handler(CommandHandler("balance",  user.cmd_balance))
    app.add_handler(CommandHandler("deposit",  user.cmd_deposit))
    app.add_handler(CommandHandler("withdraw", user.cmd_withdraw))
    app.add_handler(CommandHandler("history",  user.cmd_history))
    app.add_handler(CommandHandler("help",     user.cmd_help))

    # ── Admin commands ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin",           admin.cmd_admin_panel))
    app.add_handler(CommandHandler("users",           admin.cmd_list_users))
    app.add_handler(CommandHandler("pending",         admin.cmd_pending_withdrawals))
    app.add_handler(CommandHandler("approve",         admin.cmd_approve_withdrawal))
    app.add_handler(CommandHandler("reject",          admin.cmd_reject_withdrawal))
    app.add_handler(CommandHandler("credit",          admin.cmd_credit_user))
    app.add_handler(CommandHandler("debit",           admin.cmd_debit_user))
    app.add_handler(CommandHandler("broadcast_trade", admin.cmd_broadcast_trade))
    app.add_handler(CommandHandler("summary",         admin.cmd_post_summary))
    app.add_handler(CommandHandler("pause",           admin.cmd_pause_signals))
    app.add_handler(CommandHandler("resume",          admin.cmd_resume_signals))
    app.add_handler(CommandHandler("logs",            admin.cmd_recent_logs))
    app.add_handler(CommandHandler("setdepositaddr",  admin.cmd_set_deposit_address))

    # ── Inline button callbacks ────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(admin.handle_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(user.handle_callback,  pattern="^user:"))

    # ── Fallback ───────────────────────────────────────────────────────────────
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user.handle_message))

    logger.info("Bot is polling…")
    app.run_polling(drop_pending_updates=True)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass

