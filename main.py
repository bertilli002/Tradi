"""
Telegram Trading Bot - Main Entry Point
Run this file to start the bot.
"""

import asyncio
import logging
import sys
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
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
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger(__name__)

# ── Error Handler ─────────────────────────────────────────────────────────────
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Log the error that caused the update to fail."""
    logger.error("Exception while handling an update:", exc_info=context.error)
    # Optional: Send a message to the user or admin that an error occurred
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text(
            "An internal error occurred while processing your request."
        )

async def post_init(application: Application) -> None:
    """Called once after bot is initialised."""
    await init_db()
    logger.info("Database initialised.")

    # Start background tasks
    deposit_monitor = DepositMonitor(application.bot)
    application.create_task(deposit_monitor.run())

    broadcaster = TradeBroadcaster(application.bot)
    application.create_task(broadcaster.run())

    logger.info("Background tasks started.")


async def main(*args, **kwargs) -> None:
    """Main entry point for the bot."""
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN is not set. Check your environment variables.")
        return

    # Initialize Handlers
    user = UserHandlers()
    admin = AdminHandlers()

    # Build Application
    app = (
        Application.builder()
        .token(BOT_TOKEN)
        .post_init(post_init)
        .build()
    )

    # ── Register Error Handler ────────────────────────────────────────────────
    app.add_error_handler(error_handler)

    # ── User Commands ──────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("start",    user.cmd_start))
    app.add_handler(CommandHandler("help",     user.cmd_help))
    app.add_handler(CommandHandler("profile",  user.cmd_profile))
    app.add_handler(CommandHandler("deposit",  user.cmd_deposit))
    app.add_handler(CommandHandler("withdraw", user.cmd_withdraw))
    app.add_handler(CommandHandler("history",  user.cmd_history))
    app.add_handler(CommandHandler("support",  user.cmd_support))

    # ── Admin Commands ─────────────────────────────────────────────────────────
    app.add_handler(CommandHandler("admin",            admin.cmd_admin_panel))
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

    # ── Callbacks & Fallback ───────────────────────────────────────────────────
    app.add_handler(CallbackQueryHandler(admin.handle_callback, pattern="^admin:"))
    app.add_handler(CallbackQueryHandler(user.handle_callback,  pattern="^user:"))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, user.handle_message))

    logger.info("Bot is starting...")
    
    async with app:
        await app.initialize()
        await app.start()
        await app.updater.start_polling(drop_pending_updates=True)
        logger.info("Bot is polling. Waiting for messages...")
        while True:
            await asyncio.sleep(3600)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot stopped.")
    except Exception as e:
        logger.exception(f"Unexpected crash at startup: {e}")
