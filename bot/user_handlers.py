"""
bot/user_handlers.py  –  Commands available to all registered users
"""

from __future__ import annotations

import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes
from telegram.constants import ParseMode

from config.settings import ADMIN_IDS, MIN_DEPOSIT, MIN_WITHDRAWAL, MASTER_WALLET_ADDRESS, CRYPTO_NETWORK
from database.crud import (
    get_or_create_user, get_user_tx_log, get_user_withdrawals,
    create_withdrawal,
)

logger = logging.getLogger(__name__)


class UserHandlers:

    # ── /start ────────────────────────────────────────────────────────────────
    async def cmd_profile(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tg = update.effective_user
        user = await get_or_create_user(tg.id, tg.username, tg.full_name)
        await update.message.reply_text(
            f"👋 Welcome, *{tg.first_name}*!\n\n"
            f"I'm your trading account manager. Here's what you can do:\n\n"
            f"💰 /balance — View your balance\n"
            f"📥 /deposit — Get the deposit address\n"
            f"📤 /withdraw — Request a withdrawal\n"
            f"📋 /history — Transaction history\n"
            f"❓ /help — Help & FAQ",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /balance ──────────────────────────────────────────────────────────────
    async def cmd_balance(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tg = update.effective_user
        user = await get_or_create_user(tg.id, tg.username, tg.full_name)
        withdrawals = await get_user_withdrawals(user.id, limit=50)
        pending_out = sum(w.amount for w in withdrawals if w.status.value == "pending")

        await update.message.reply_text(
            f"💼 *Your Account Balance*\n\n"
            f"Available: `${user.balance:.2f} USDT`\n"
            f"Pending withdrawal: `${pending_out:.2f} USDT`\n\n"
            f"Use /deposit to add funds or /withdraw to cash out.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /deposit ──────────────────────────────────────────────────────────────
    async def cmd_deposit(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not MASTER_WALLET_ADDRESS:
            await update.message.reply_text(
                "⚠️ Deposit address not configured yet. Contact an admin."
            )
            return

        network_label = CRYPTO_NETWORK.upper()
        await update.message.reply_text(
            f"📥 *Deposit Instructions*\n\n"
            f"Send USDT ({network_label}) to:\n\n"
            f"`{MASTER_WALLET_ADDRESS}`\n\n"
            f"Minimum deposit: `${MIN_DEPOSIT:.2f} USDT`\n\n"
            f"⏱ Your balance will be updated automatically within a few minutes after confirmation.\n\n"
            f"⚠️ *Only send USDT on {network_label} network.* Other assets may be lost.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /withdraw ─────────────────────────────────────────────────────────────
    async def cmd_withdraw(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tg = update.effective_user
        user = await get_or_create_user(tg.id, tg.username, tg.full_name)

        # Usage: /withdraw <amount> <address>
        args = ctx.args
        if len(args) < 2:
            await update.message.reply_text(
                "📤 *Withdrawal Request*\n\n"
                "Usage: `/withdraw <amount> <wallet_address>`\n\n"
                f"Example: `/withdraw 50 TRX...abc`\n"
                f"Minimum: `${MIN_WITHDRAWAL:.2f} USDT`\n"
                f"Your balance: `${user.balance:.2f} USDT`\n\n"
                "Withdrawals require admin approval and are processed manually.",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        try:
            amount = float(args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid amount. Use a number, e.g. `50`.", parse_mode=ParseMode.MARKDOWN)
            return

        destination = args[1].strip()

        if amount < MIN_WITHDRAWAL:
            await update.message.reply_text(f"❌ Minimum withdrawal is ${MIN_WITHDRAWAL:.2f} USDT.")
            return

        if user.balance < amount:
            await update.message.reply_text(
                f"❌ Insufficient balance.\n"
                f"Available: `${user.balance:.2f} USDT`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        w = await create_withdrawal(user.id, amount, destination, CRYPTO_NETWORK)

        # Notify admins
        for admin_id in ADMIN_IDS:
            try:
                await ctx.bot.send_message(
                    admin_id,
                    f"🔔 *New Withdrawal Request #{w.id}*\n\n"
                    f"User: @{tg.username or tg.id} (`{tg.id}`)\n"
                    f"Amount: `${amount:.2f} USDT`\n"
                    f"To: `{destination}`\n"
                    f"Network: {CRYPTO_NETWORK.upper()}\n\n"
                    f"Use `/approve {w.id}` or `/reject {w.id} <reason>` to action.",
                    parse_mode=ParseMode.MARKDOWN,
                )
            except Exception:
                pass

        await update.message.reply_text(
            f"✅ *Withdrawal Request Submitted*\n\n"
            f"Amount: `${amount:.2f} USDT`\n"
            f"To: `{destination}`\n"
            f"Status: ⏳ Pending admin approval\n\n"
            f"Reference ID: `#{w.id}`\n\n"
            "You will be notified when it's processed.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /history ──────────────────────────────────────────────────────────────
    async def cmd_history(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        tg = update.effective_user
        user = await get_or_create_user(tg.id, tg.username, tg.full_name)
        logs = await get_user_tx_log(user.id, limit=15)

        if not logs:
            await update.message.reply_text("📋 No transactions yet.")
            return

        lines = ["📋 *Recent Transactions* (last 15)\n"]
        for tx in logs:
            sign = "+" if tx.amount >= 0 else ""
            emoji = {
                "deposit": "📥", "withdrawal_hold": "📤", "withdrawal_refund": "↩️",
                "withdrawal_approved": "✅", "admin_credit": "🎁", "admin_debit": "🔧",
            }.get(tx.action, "•")
            lines.append(
                f"{emoji} `{tx.action}` {sign}${tx.amount:.2f} → bal `${tx.balance_after:.2f}`\n"
                f"   _{tx.created_at.strftime('%Y-%m-%d %H:%M UTC')}_"
            )

        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    # ── /help ─────────────────────────────────────────────────────────────────
    async def cmd_help(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "❓ *Help & FAQ*\n\n"
            "*Commands:*\n"
            "/balance — Check your USDT balance\n"
            "/deposit — Get the deposit wallet address\n"
            "/withdraw <amount> <address> — Request a withdrawal\n"
            "/history — View your transaction history\n\n"
            "*How deposits work:*\n"
            "Send USDT to the master wallet. The bot detects it on-chain and credits your internal balance automatically.\n\n"
            "*How withdrawals work:*\n"
            "Submit a request. An admin reviews and processes it manually. You'll get a notification.\n\n"
            "*Is my money safe?*\n"
            "The bot never moves funds automatically. All withdrawals require admin approval.",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── Callback buttons ──────────────────────────────────────────────────────
    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        # Extensible for future inline button flows

    # ── Plain messages ────────────────────────────────────────────────────────
    async def handle_message(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        await update.message.reply_text(
            "Use /help to see available commands.",
        )
