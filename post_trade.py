#!/usr/bin/env python3
"""
tools/post_trade.py  –  CLI helper for admins to post trade signals
without opening Telegram. Appends to trade_feed.jsonl which the bot watches.

Usage:
  python tools/post_trade.py open BTC BUY 65000 "Breakout confirmed"
  python tools/post_trade.py close BTC BUY 67500 3.85 "TP hit"
  python tools/post_trade.py update "Holding, next TP at 69k"
  python tools/post_trade.py summary "Week recap: 5W/1L +22%"
"""

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

FEED_FILE = Path(__file__).resolve().parent.parent / "trade_feed.jsonl"


def main():
    args = sys.argv[1:]
    if not args:
        print(__doc__)
        sys.exit(1)

    signal_type = args[0].lower()
    record: dict = {"type": signal_type, "posted_at": datetime.now(timezone.utc).isoformat()}

    if signal_type == "open":
        if len(args) < 4:
            print('Usage: post_trade.py open <ASSET> <BUY|SELL> <entry_price> "message"')
            sys.exit(1)
        record["asset"]       = args[1].upper()
        record["direction"]   = args[2].upper()
        record["entry_price"] = float(args[3])
        record["message"]     = " ".join(args[4:]).strip('"')

    elif signal_type == "close":
        if len(args) < 5:
            print('Usage: post_trade.py close <ASSET> <BUY|SELL> <exit_price> <pnl%> "message"')
            sys.exit(1)
        record["asset"]      = args[1].upper()
        record["direction"]  = args[2].upper()
        record["exit_price"] = float(args[3])
        record["pnl_pct"]    = float(args[4])
        record["message"]    = " ".join(args[5:]).strip('"')

    elif signal_type in ("update", "summary"):
        if len(args) < 2:
            print(f'Usage: post_trade.py {signal_type} "your message"')
            sys.exit(1)
        record["message"] = " ".join(args[1:]).strip('"')

    else:
        print(f"Unknown signal type: {signal_type}")
        sys.exit(1)

    with open(FEED_FILE, "a") as f:
        f.write(json.dumps(record) + "\n")

    print(f"✅ Signal written to {FEED_FILE}: {record}")


if __name__ == "__main__":
    main()
