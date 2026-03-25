"""
bot/trade_broadcaster.py  –  Reads trade data from external source and
auto-posts signals to the broadcast channel.

Currently reads from a local JSON file that the admin (or trading script)
writes to. Replace _fetch_new_trades() to pull from an exchange API,
webhook, or any other source.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from pathlib import Path

from telegram.constants import ParseMode

from config.settings import BROADCAST_CHAT_ID, TRADE_POLL_INTERVAL, runtime
from database.crud import create_trade_signal, get_setting

logger = logging.getLogger(__name__)

# Path where your trading script drops new signals as JSON objects (one per line)
TRADE_FEED_FILE = Path("trade_feed.jsonl")


class TradeBroadcaster:
    """
    Watches TRADE_FEED_FILE for new trade signal entries and broadcasts them
    to BROADCAST_CHAT_ID.

    Each line in the file is a JSON object:
    {
      "type": "open|close|update|summary",
      "asset": "BTC",
      "direction": "BUY",
      "entry_price": 65000,
      "exit_price": null,
      "pnl_pct": null,
      "message": "BTC long entry at support"
    }
    """

    def __init__(self, bot):
        self.bot     = bot
        self._offset = 0  # byte offset into the feed file

    async def run(self) -> None:
        logger.info("TradeBroadcaster started.")
        # Restore persistent offset
        try:
            stored = await get_setting("trade_feed_offset", "0")
            self._offset = int(stored)
        except Exception:
            self._offset = 0

        while True:
            try:
                await self._process_feed()
            except Exception as e:
                logger.error(f"TradeBroadcaster error: {e}", exc_info=True)
            await asyncio.sleep(TRADE_POLL_INTERVAL)

    async def _process_feed(self) -> None:
        if not TRADE_FEED_FILE.exists():
            return
        if not runtime.get("signals_active", True):
            return

        with open(TRADE_FEED_FILE, "rb") as f:
            f.seek(self._offset)
            lines = f.readlines()
            new_offset = f.tell()

        if not lines:
            return

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                trade = json.loads(line)
                await self._broadcast_trade(trade)
            except json.JSONDecodeError:
                logger.warning(f"Invalid JSON line: {line}")
            except Exception as e:
                logger.error(f"Error broadcasting trade: {e}")

        self._offset = new_offset
        await self._save_offset()

    async def _broadcast_trade(self, trade: dict) -> None:
        signal_type = trade.get("type", "update").lower()
        asset       = trade.get("asset")
        direction   = trade.get("direction")
        entry       = trade.get("entry_price")
        exit_p      = trade.get("exit_price")
        pnl         = trade.get("pnl_pct")
        message     = trade.get("message", "")

        if signal_type == "open":
            text = (
                f"📈 *New Trade Signal*\n\n"
                f"Asset: `{asset}`\n"
                f"Direction: {'🟢 BUY' if direction == 'BUY' else '🔴 SELL'}\n"
                f"Entry: `${entry:,.2f}`\n\n"
                f"_{message}_"
            )
        elif signal_type == "close":
            sign  = "+" if (pnl or 0) >= 0 else ""
            emoji = "🎉" if (pnl or 0) >= 0 else "📉"
            text  = (
                f"{emoji} *Trade Closed*\n\n"
                f"Asset: `{asset}`\n"
                f"Exit: `${exit_p:,.2f}`\n"
                f"Result: `{sign}{pnl:.2f}%`\n\n"
                f"_{message}_"
            )
        elif signal_type == "summary":
            text = f"📊 *Summary*\n\n{message}"
        else:
            text = f"🔔 *Update*\n\n{message}"

        sent_id = None
        if BROADCAST_CHAT_ID:
            try:
                sent = await self.bot.send_message(BROADCAST_CHAT_ID, text, parse_mode=ParseMode.MARKDOWN)
                sent_id = sent.message_id
            except Exception as e:
                logger.error(f"Failed to send to channel: {e}")

        await create_trade_signal(
            signal_type=signal_type,
            message=message,
            asset=asset,
            direction=direction,
            entry_price=entry,
            exit_price=exit_p,
            pnl_pct=pnl,
            broadcast_msg_id=sent_id,
        )

    async def _save_offset(self) -> None:
        from database.crud import set_setting
        await set_setting("trade_feed_offset", str(self._offset))
