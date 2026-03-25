"""
config/settings.py  –  All configuration loaded from environment / .env
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root
load_dotenv(Path(__file__).resolve().parent.parent / ".env")

# ── Core ───────────────────────────────────────────────────────────────────────
BOT_TOKEN: str        = os.getenv("BOT_TOKEN", "")
ADMIN_IDS: list[int]  = [
    int(x.strip()) for x in os.getenv("ADMIN_IDS", "").split(",") if x.strip()
]

# ── Channel/Group ──────────────────────────────────────────────────────────────
# Where trade signals & summaries are broadcast (e.g. "@mychannel" or "-1001234567890")
BROADCAST_CHAT_ID: str = os.getenv("BROADCAST_CHAT_ID", "")

# ── Crypto / Wallet ────────────────────────────────────────────────────────────
# Master deposit wallet that users send funds to
MASTER_WALLET_ADDRESS: str = os.getenv("MASTER_WALLET_ADDRESS", "")

# Which network to monitor  (tron | ethereum | bsc | solana)
CRYPTO_NETWORK: str = os.getenv("CRYPTO_NETWORK", "tron")

# TronGrid / Etherscan / BscScan API key for deposit monitoring
BLOCKCHAIN_API_KEY: str = os.getenv("BLOCKCHAIN_API_KEY", "")

# Minimum deposit amount (in USD or token units, depending on your setup)
MIN_DEPOSIT: float = float(os.getenv("MIN_DEPOSIT", "10"))
MIN_WITHDRAWAL: float = float(os.getenv("MIN_WITHDRAWAL", "10"))

# ── Deposit Monitor ────────────────────────────────────────────────────────────
# How often (seconds) to poll the blockchain for new deposits
DEPOSIT_POLL_INTERVAL: int = int(os.getenv("DEPOSIT_POLL_INTERVAL", "60"))

# ── Trade Broadcaster ──────────────────────────────────────────────────────────
# How often (seconds) to check for new trades to broadcast
TRADE_POLL_INTERVAL: int = int(os.getenv("TRADE_POLL_INTERVAL", "30"))

# Whether signals are currently active (runtime-toggled; starts True)
SIGNALS_ACTIVE: bool = os.getenv("SIGNALS_ACTIVE", "true").lower() == "true"

# ── Database ───────────────────────────────────────────────────────────────────
DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./bot_data.db")

# ── Logging ────────────────────────────────────────────────────────────────────
LOG_LEVEL: str = os.getenv("LOG_LEVEL", "INFO")

# ── Runtime state (mutable at runtime) ────────────────────────────────────────
# This dict is shared across modules; do not reassign the dict itself.
runtime: dict = {
    "signals_active": SIGNALS_ACTIVE,
}
