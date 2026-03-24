# 📈 Telegram Trading Bot

A production-ready Telegram bot for managing a crypto trading fund.
Tracks user balances, handles deposit/withdrawal workflows, and broadcasts
trade signals — all without ever touching funds automatically.

---

## Features

| Feature | Details |
|---|---|
| **User Management** | Register users, track internal USDT balances, full audit log |
| **Deposits** | Blockchain polling (TRON/ETH/BSC), admin notification, balance credit |
| **Withdrawals** | Request → admin approval → manual on-chain transfer |
| **Trade Signals** | Admin command or auto-feed from `trade_feed.jsonl` → broadcast to channel |
| **Safety** | No automatic fund movement. All withdrawals need human approval |
| **Admin Panel** | Full suite of moderation, credit/debit, approval, log commands |
| **Pause/Resume** | Instantly pause signal broadcasting with `/pause` |

---

## Quick Start

### 1. Clone & install
```bash
git clone <this-repo>
cd telegram-trading-bot
python -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure
```bash
cp .env.example .env
nano .env          # fill in BOT_TOKEN, ADMIN_IDS, etc.
```

### 3. Run
```bash
python main.py
```

The bot will create `bot_data.db` automatically on first run.

---

## Configuration Reference

| Variable | Description |
|---|---|
| `BOT_TOKEN` | From @BotFather on Telegram |
| `ADMIN_IDS` | Comma-separated Telegram user IDs with admin access |
| `BROADCAST_CHAT_ID` | Channel/group ID for trade signal posts |
| `MASTER_WALLET_ADDRESS` | On-chain address users send deposits to |
| `CRYPTO_NETWORK` | `tron` \| `ethereum` \| `bsc` |
| `BLOCKCHAIN_API_KEY` | TronGrid / Etherscan API key |
| `MIN_DEPOSIT` | Minimum deposit in USDT (default: 10) |
| `MIN_WITHDRAWAL` | Minimum withdrawal in USDT (default: 10) |
| `DEPOSIT_POLL_INTERVAL` | Seconds between blockchain checks (default: 60) |
| `TRADE_POLL_INTERVAL` | Seconds between trade feed checks (default: 30) |
| `DATABASE_URL` | SQLite (default) or PostgreSQL URL |

---

## User Commands

| Command | Description |
|---|---|
| `/start` | Register and see welcome message |
| `/balance` | Check USDT balance |
| `/deposit` | Get deposit wallet address |
| `/withdraw <amount> <address>` | Submit withdrawal request |
| `/history` | View last 15 transactions |
| `/help` | FAQ |

---

## Admin Commands

| Command | Description |
|---|---|
| `/admin` | Overview panel |
| `/users` | List all users and balances |
| `/pending` | View pending withdrawal requests |
| `/approve <id> [note]` | Approve a withdrawal |
| `/reject <id> [reason]` | Reject & refund a withdrawal |
| `/credit <tg_id> <amount> [note]` | Manually credit a user's balance |
| `/debit <tg_id> <amount> [note]` | Manually debit a user's balance |
| `/broadcast_trade open BTC BUY 65000 "message"` | Post a trade signal |
| `/broadcast_trade close BTC SELL 67000 5.2 "message"` | Post a closed trade |
| `/broadcast_trade update "free text"` | Post an update |
| `/broadcast_trade summary "text"` | Post a summary |
| `/summary` | Auto-generate and post performance summary |
| `/pause` | Pause all signal broadcasting |
| `/resume` | Resume signal broadcasting |
| `/logs` | View recent transaction log |
| `/setdepositaddr <address>` | Update the master wallet address |

---

## Deposit Flow

```
User sends USDT on-chain to master wallet
        ↓
Bot polls blockchain every 60s (configurable)
        ↓
Admin receives notification with tx hash & amount
        ↓
Admin runs: /credit <user_tg_id> <amount> deposit:<txhash>
        ↓
User balance updated, audit log written
```

> **Production tip:** For auto-matching, have users send a small "test" amount first to verify, or use a payment processor that assigns unique sub-addresses per user.

---

## Trade Signal Auto-Feed

The bot watches `trade_feed.jsonl` in the project root. Your trading script or admin tool can append lines to this file:

```jsonl
{"type": "open", "asset": "BTC", "direction": "BUY", "entry_price": 65000, "message": "Breakout entry"}
{"type": "close", "asset": "BTC", "direction": "BUY", "exit_price": 67500, "pnl_pct": 3.85, "message": "TP hit"}
{"type": "summary", "message": "Week 12 Results: 4W/1L, +14.2% avg"}
```

Each line is processed once and broadcast to your channel. The file position is tracked so restarts don't re-post.

---

## Database

Uses SQLite by default (file: `bot_data.db`). Tables:

- `users` — Telegram users + balances
- `deposits` — On-chain deposit records
- `withdrawals` — Withdrawal requests + status
- `trade_signals` — All posted signals/summaries
- `transaction_logs` — Immutable audit trail
- `bot_settings` — Runtime key-value settings

Switch to PostgreSQL by setting `DATABASE_URL=postgresql+asyncpg://...` and installing `asyncpg`.

---

## Security Notes

- ✅ Bot **never** automatically moves funds
- ✅ All withdrawals require explicit admin approval
- ✅ Balance deducted at request time (prevents double-spend)
- ✅ Rejected withdrawals automatically refunded
- ✅ Every balance change logged with before/after values
- ✅ Admin commands verified by Telegram user ID
- ✅ No private keys stored in the bot

---

## Production Deployment

```bash
# Run as a systemd service (Linux)
sudo nano /etc/systemd/system/tradingbot.service
```

```ini
[Unit]
Description=Telegram Trading Bot
After=network.target

[Service]
Type=simple
User=ubuntu
WorkingDirectory=/home/ubuntu/telegram-trading-bot
ExecStart=/home/ubuntu/telegram-trading-bot/venv/bin/python main.py
Restart=always
RestartSec=10
EnvironmentFile=/home/ubuntu/telegram-trading-bot/.env

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl enable tradingbot
sudo systemctl start tradingbot
sudo journalctl -u tradingbot -f   # live logs
```

---

## Files Overview

```
telegram-trading-bot/
├── main.py                   # Entry point, handler registration
├── requirements.txt
├── .env.example              # Config template
├── trade_feed.jsonl          # Auto-created; drop signals here
├── bot_data.db               # SQLite database (auto-created)
├── bot.log                   # Log file (auto-created)
├── config/
│   └── settings.py           # All env vars loaded here
├── database/
│   ├── db.py                 # SQLAlchemy models
│   └── crud.py               # All DB operations
└── bot/
    ├── user_handlers.py      # /start /balance /deposit /withdraw /history
    ├── admin_handlers.py     # All /admin commands
    ├── deposit_monitor.py    # Blockchain polling background task
    └── trade_broadcaster.py  # trade_feed.jsonl watcher
```
