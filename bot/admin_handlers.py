"""
bot/admin_handlers.py  –  Admin-only commands
All commands check ADMIN_IDS before executing.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Optional

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from config.settings import ADMIN_IDS, BROADCAST_CHAT_ID, runtime
from database.crud import (
    admin_credit, admin_debit, approve_withdrawal, create_trade_signal,
    get_all_users, get_pending_withdrawals, get_recent_signals,
    get_recent_tx_logs, get_setting, get_withdrawal, reject_withdrawal,
    set_setting,
)

logger = logging.getLogger(__name__)

# Re-export get_recent_logs if missing from crud (defined below as a fallback alias)
try:
    from database.crud import get_recent_tx_logs as _grl
except ImportError:
    pass


def _is_admin(user_id: int) -> bool:
    return user_id in ADMIN_IDS


def _admin_only(func):
    """Decorator to reject non-admin users."""
    async def wrapper(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE):
        if not _is_admin(update.effective_user.id):
            await update.message.reply_text("⛔ Admin only.")
            return
        return await func(self, update, ctx)
    wrapper.__name__ = func.__name__
    return wrapper


class AdminHandlers:

    # ── /admin ────────────────────────────────────────────────────────────────
    @_admin_only
    async def cmd_admin_panel(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        signals_state = "🟢 Active" if runtime["signals_active"] else "🔴 Paused"
        deposit_addr  = await get_setting("master_wallet_address", "Not set")
        users         = await get_all_users()
        pending       = await get_pending_withdrawals()

        await update.message.reply_text(
            f"🛠 *Admin Panel*\n\n"
            f"👥 Total users: `{len(users)}`\n"
            f"⏳ Pending withdrawals: `{len(pending)}`\n"
            f"📡 Signals: {signals_state}\n"
            f"🏦 Deposit address: `{deposit_addr}`\n\n"
            f"*Available Admin Commands:*\n"
            f"/users — List all users\n"
            f"/pending — View pending withdrawals\n"
            f"/approve <id> [note] — Approve withdrawal\n"
            f"/reject <id> [reason] — Reject withdrawal\n"
            f"/credit <tg_id> <amount> [note] — Credit a user\n"
            f"/debit <tg_id> <amount> [note] — Debit a user\n"
            f"/broadcast_trade — Post a trade signal\n"
            f"/summary — Post a performance summary\n"
            f"/pause — Pause signal broadcasting\n"
            f"/resume — Resume signal broadcasting\n"
            f"/logs — Recent transaction logs\n"
            f"/setdepositaddr <address> — Set master wallet",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /users ────────────────────────────────────────────────────────────────
    @_admin_only
    async def cmd_list_users(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        users = await get_all_users()
        if not users:
            await update.message.reply_text("No users yet.")
            return
        lines = [f"👥 *All Users* ({len(users)})\n"]
        for u in users[:30]:
            tag = f"@{u.username}" if u.username else f"id:{u.telegram_id}"
            lines.append(f"• {tag} — `${u.balance:.2f}` USDT")
        if len(users) > 30:
            lines.append(f"…and {len(users)-30} more")
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    # ── /pending ──────────────────────────────────────────────────────────────
    @_admin_only
    async def cmd_pending_withdrawals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        pending = await get_pending_withdrawals()
        if not pending:
            await update.message.reply_text("✅ No pending withdrawals.")
            return
        lines = [f"⏳ *Pending Withdrawals* ({len(pending)})\n"]
        for w in pending:
            lines.append(
                f"*#{w.id}* — `${w.amount:.2f}` USDT\n"
                f"  To: `{w.destination}`\n"
                f"  Requested: {w.requested_at.strftime('%Y-%m-%d %H:%M UTC')}\n"
                f"  → `/approve {w.id}` | `/reject {w.id}`"
            )
        await update.message.reply_text("\n\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    # ── /approve <id> [note] ──────────────────────────────────────────────────
    @_admin_only
    async def cmd_approve_withdrawal(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args
        if not args:
            await update.message.reply_text("Usage: `/approve <withdrawal_id> [note]`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            wid = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid ID.")
            return
        note = " ".join(args[1:]) if len(args) > 1 else None
        try:
            w = await approve_withdrawal(wid, note)
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
            return

        await update.message.reply_text(
            f"✅ Withdrawal *#{w.id}* approved.\n"
            f"Amount: `${w.amount:.2f}` to `{w.destination}`\n"
            f"⚠️ *Remember to send the funds manually on-chain.*",
            parse_mode=ParseMode.MARKDOWN,
        )
        # Notify the user
        await self._notify_user_withdrawal(ctx, w, approved=True)

    # ── /reject <id> [reason] ─────────────────────────────────────────────────
    @_admin_only
    async def cmd_reject_withdrawal(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args
        if not args:
            await update.message.reply_text("Usage: `/reject <withdrawal_id> [reason]`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            wid = int(args[0])
        except ValueError:
            await update.message.reply_text("❌ Invalid ID.")
            return
        reason = " ".join(args[1:]) if len(args) > 1 else "No reason provided"
        try:
            w = await reject_withdrawal(wid, reason)
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
            return

        await update.message.reply_text(
            f"↩️ Withdrawal *#{w.id}* rejected. ${w.amount:.2f} refunded to user.",
            parse_mode=ParseMode.MARKDOWN,
        )
        await self._notify_user_withdrawal(ctx, w, approved=False)

    async def _notify_user_withdrawal(self, ctx, withdrawal, approved: bool) -> None:
        from database.crud import get_session
        from database.db import User
        from sqlalchemy import select
        async with get_session() as session:
            user = await session.get(User, withdrawal.user_id)
            if user is None:
                return
        try:
            if approved:
                msg = (
                    f"✅ *Withdrawal Approved*\n\n"
                    f"Amount: `${withdrawal.amount:.2f} USDT`\n"
                    f"To: `{withdrawal.destination}`\n"
                    f"Note: {withdrawal.admin_note or 'Processed'}\n\n"
                    f"Funds will arrive on-chain shortly."
                )
            else:
                msg = (
                    f"❌ *Withdrawal Rejected*\n\n"
                    f"Amount: `${withdrawal.amount:.2f} USDT` has been refunded to your balance.\n"
                    f"Reason: {withdrawal.admin_note or 'No reason given'}"
                )
            await ctx.bot.send_message(user.telegram_id, msg, parse_mode=ParseMode.MARKDOWN)
        except Exception:
            pass

    # ── /credit <tg_id> <amount> [note] ──────────────────────────────────────
    @_admin_only
    async def cmd_credit_user(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args
        if len(args) < 2:
            await update.message.reply_text("Usage: `/credit <telegram_id> <amount> [note]`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            tg_id  = int(args[0])
            amount = float(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid arguments.")
            return
        note = " ".join(args[2:]) if len(args) > 2 else "Admin credit"
        try:
            user = await admin_credit(tg_id, amount, note)
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
            return
        await update.message.reply_text(
            f"✅ Credited `${amount:.2f}` to user `{tg_id}`.\nNew balance: `${user.balance:.2f}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /debit <tg_id> <amount> [note] ────────────────────────────────────────
    @_admin_only
    async def cmd_debit_user(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        args = ctx.args
        if len(args) < 2:
            await update.message.reply_text("Usage: `/debit <telegram_id> <amount> [note]`", parse_mode=ParseMode.MARKDOWN)
            return
        try:
            tg_id  = int(args[0])
            amount = float(args[1])
        except ValueError:
            await update.message.reply_text("❌ Invalid arguments.")
            return
        note = " ".join(args[2:]) if len(args) > 2 else "Admin debit"
        try:
            user = await admin_debit(tg_id, amount, note)
        except ValueError as e:
            await update.message.reply_text(f"❌ {e}")
            return
        await update.message.reply_text(
            f"✅ Debited `${amount:.2f}` from user `{tg_id}`.\nNew balance: `${user.balance:.2f}`",
            parse_mode=ParseMode.MARKDOWN,
        )

    # ── /broadcast_trade ──────────────────────────────────────────────────────
    @_admin_only
    async def cmd_broadcast_trade(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Usage:
          /broadcast_trade open BTC BUY 65000 "BTC long opened"
          /broadcast_trade close BTC SELL 67000 5.2 "BTC closed +5.2%"
          /broadcast_trade update "Holding strong, TP at 68k"
        """
        if not runtime["signals_active"]:
            await update.message.reply_text("⛔ Signals are currently paused. Use /resume to enable.")
            return

        args = ctx.args
        if not args:
            await update.message.reply_text(
                "Usage:\n"
                "`/broadcast_trade open <asset> <BUY|SELL> <entry> \"message\"`\n"
                "`/broadcast_trade close <asset> <BUY|SELL> <exit> <pnl%> \"message\"`\n"
                "`/broadcast_trade update \"free text message\"`\n"
                "`/broadcast_trade summary \"weekly summary text\"`",
                parse_mode=ParseMode.MARKDOWN,
            )
            return

        signal_type = args[0].lower()
        text_parts  = ctx.args[1:]

        asset = direction = None
        entry_price = exit_price = pnl_pct = None
        message = ""

        try:
            if signal_type == "open" and len(text_parts) >= 3:
                asset       = text_parts[0].upper()
                direction   = text_parts[1].upper()
                entry_price = float(text_parts[2])
                message     = " ".join(text_parts[3:]).strip('"')
                formatted   = (
                    f"📈 *New Trade Signal*\n\n"
                    f"Asset: `{asset}`\n"
                    f"Direction: {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}\n"
                    f"Entry: `${entry_price:,.2f}`\n\n"
                    f"_{message}_"
                )
            elif signal_type == "close" and len(text_parts) >= 4:
                asset      = text_parts[0].upper()
                direction  = text_parts[1].upper()
                exit_price = float(text_parts[2])
                pnl_pct    = float(text_parts[3])
                message    = " ".join(text_parts[4:]).strip('"')
                sign       = "+" if pnl_pct >= 0 else ""
                emoji      = "🎉" if pnl_pct >= 0 else "📉"
                formatted  = (
                    f"{emoji} *Trade Closed*\n\n"
                    f"Asset: `{asset}`\n"
                    f"Exit: `${exit_price:,.2f}`\n"
                    f"Result: `{sign}{pnl_pct:.2f}%`\n\n"
                    f"_{message}_"
                )
            elif signal_type in ("update", "summary"):
                message   = " ".join(text_parts).strip('"')
                icon      = "📊" if signal_type == "summary" else "🔔"
                label     = "Weekly Summary" if signal_type == "summary" else "Trade Update"
                formatted = f"{icon} *{label}*\n\n{message}"
            else:
                await update.message.reply_text("❌ Unrecognised signal format. See usage above.")
                return
        except (ValueError, IndexError) as e:
            await update.message.reply_text(f"❌ Parse error: {e}")
            return

        sent_msg = None
        if BROADCAST_CHAT_ID:
            try:
                sent_msg = await ctx.bot.send_message(
                    BROADCAST_CHAT_ID, formatted, parse_mode=ParseMode.MARKDOWN
                )
            except Exception as e:
                await update.message.reply_text(f"⚠️ Broadcast failed: {e}")

        await create_trade_signal(
            signal_type=signal_type,
            message=message,
            asset=asset,
            direction=direction,
            entry_price=entry_price,
            exit_price=exit_price,
            pnl_pct=pnl_pct,
            broadcast_msg_id=sent_msg.message_id if sent_msg else None,
        )

        await update.message.reply_text("✅ Signal broadcasted and logged.")

    # ── /summary ──────────────────────────────────────────────────────────────
    @_admin_only
    async def cmd_post_summary(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        signals = await get_recent_signals(50)
        closed  = [s for s in signals if s.signal_type == "close" and s.pnl_pct is not None]
        if not closed:
            await update.message.reply_text("No closed trades to summarise.")
            return
        wins     = [s for s in closed if s.pnl_pct >= 0]
        losses   = [s for s in closed if s.pnl_pct < 0]
        avg_pnl  = sum(s.pnl_pct for s in closed) / len(closed)
        win_rate = len(wins) / len(closed) * 100

        summary = (
            f"📊 *Performance Summary*\n\n"
            f"Total Trades: `{len(closed)}`\n"
            f"Wins: `{len(wins)}` | Losses: `{len(losses)}`\n"
            f"Win Rate: `{win_rate:.1f}%`\n"
            f"Avg PnL: `{'+'if avg_pnl>=0 else ''}{avg_pnl:.2f}%`\n"
            f"Best: `+{max(s.pnl_pct for s in wins):.2f}%`\n"
        ) if wins else (
            f"📊 *Performance Summary*\n\n"
            f"Total Trades: `{len(closed)}` | All losses 📉"
        )

        if BROADCAST_CHAT_ID:
            try:
                sent = await ctx.bot.send_message(
                    BROADCAST_CHAT_ID, summary, parse_mode=ParseMode.MARKDOWN
                )
                await create_trade_signal("summary", summary, broadcast_msg_id=sent.message_id)
            except Exception as e:
                await update.message.reply_text(f"⚠️ {e}")
                return
        await update.message.reply_text("✅ Summary posted.")

    # ── /pause / /resume ──────────────────────────────────────────────────────
    @_admin_only
    async def cmd_pause_signals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        runtime["signals_active"] = False
        await set_setting("signals_active", "false")
        await update.message.reply_text("🔴 Signal broadcasting *paused*.", parse_mode=ParseMode.MARKDOWN)

    @_admin_only
    async def cmd_resume_signals(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        runtime["signals_active"] = True
        await set_setting("signals_active", "true")
        await update.message.reply_text("🟢 Signal broadcasting *resumed*.", parse_mode=ParseMode.MARKDOWN)

    # ── /logs ─────────────────────────────────────────────────────────────────
    @_admin_only
    async def cmd_recent_logs(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        logs = await get_recent_tx_logs(30)
        if not logs:
            await update.message.reply_text("No logs yet.")
            return
        lines = ["📋 *Recent Transaction Logs* (30)\n"]
        for tx in logs:
            sign = "+" if tx.amount >= 0 else ""
            lines.append(
                f"• `{tx.action}` {sign}${tx.amount:.2f} "
                f"[user {tx.user_id}] "
                f"bal→`${tx.balance_after:.2f}` "
                f"_{tx.created_at.strftime('%m-%d %H:%M')}_"
            )
        await update.message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)

    # ── /setdepositaddr <address> ─────────────────────────────────────────────
    @_admin_only
    async def cmd_set_deposit_address(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        if not ctx.args:
            await update.message.reply_text("Usage: `/setdepositaddr <wallet_address>`", parse_mode=ParseMode.MARKDOWN)
            return
        address = ctx.args[0].strip()
        await set_setting("master_wallet_address", address)
        # Also update runtime settings module
        import config.settings as s
        s.MASTER_WALLET_ADDRESS = address
        await update.message.reply_text(f"✅ Deposit address updated to:\n`{address}`", parse_mode=ParseMode.MARKDOWN)

    # ── Callback handler ──────────────────────────────────────────────────────
    async def handle_callback(self, update: Update, ctx: ContextTypes.DEFAULT_TYPE) -> None:
        query = update.callback_query
        await query.answer()
        data = query.data  # e.g. "admin:approve:5"
        parts = data.split(":")
        if len(parts) < 2:
            return
        action = parts[1]
        if action == "approve" and len(parts) == 3:
            ctx.args = [parts[2]]
            update.message = query.message
            await self.cmd_approve_withdrawal(update, ctx)
        elif action == "reject" and len(parts) == 3:
            ctx.args = [parts[2]]
            update.message = query.message
            await self.cmd_reject_withdrawal(update, ctx)
