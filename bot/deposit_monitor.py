"""
bot/deposit_monitor.py  –  Background task that polls the blockchain
for deposits to the master wallet and credits user balances.

Supports: TRON (TRC-20 USDT) out of the box.
Extend the _fetch_transactions method for other networks.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Optional

import aiohttp

from config.settings import (
    ADMIN_IDS, BLOCKCHAIN_API_KEY, CRYPTO_NETWORK,
    DEPOSIT_POLL_INTERVAL, MIN_DEPOSIT,
)
from database.crud import (
    create_deposit, credit_deposit, deposit_exists,
    get_setting, get_all_users,
)

logger = logging.getLogger(__name__)

# USDT contract addresses per network
USDT_CONTRACTS = {
    "tron":     "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t",   # USDT TRC-20
    "ethereum": "0xdAC17F958D2ee523a2206206994597C13D831ec7",
    "bsc":      "0x55d398326f99059fF775485246999027B3197955",
}


class DepositMonitor:
    """Polls the blockchain every DEPOSIT_POLL_INTERVAL seconds."""

    def __init__(self, bot):
        self.bot = bot
        self._seen_hashes: set[str] = set()

    async def run(self) -> None:
        logger.info("DepositMonitor started.")
        while True:
            try:
                await self._check_deposits()
            except Exception as e:
                logger.error(f"DepositMonitor error: {e}", exc_info=True)
            await asyncio.sleep(DEPOSIT_POLL_INTERVAL)

    async def _check_deposits(self) -> None:
        master_wallet = await get_setting("master_wallet_address")
        if not master_wallet:
            return  # Not configured yet

        transactions = await self._fetch_transactions(master_wallet)
        users        = await get_all_users()

        # Build a lookup: deposit memo/tag not used in simple USDT; we match by
        # checking if any user's registered deposit address (future feature) or
        # by notifying admins to manually match. For now, we notify admins of
        # detected deposits and they credit users via /credit.
        #
        # For production: users register a unique sub-address OR include their
        # Telegram ID as a memo/tag, then you can auto-match here.

        for tx in transactions:
            tx_hash = tx.get("hash") or tx.get("txID", "")
            amount  = tx.get("amount", 0.0)

            if not tx_hash or tx_hash in self._seen_hashes:
                continue
            self._seen_hashes.add(tx_hash)

            if await deposit_exists(tx_hash):
                continue

            if amount < MIN_DEPOSIT:
                logger.info(f"Skipping small deposit {amount} in tx {tx_hash}")
                continue

            logger.info(f"New deposit detected: {amount} USDT | tx={tx_hash}")

            # Notify all admins to manually credit the right user
            msg = (
                f"📥 *New Deposit Detected*\n\n"
                f"Amount: `{amount:.2f} USDT`\n"
                f"TxHash: `{tx_hash}`\n"
                f"Network: {CRYPTO_NETWORK.upper()}\n\n"
                f"Use `/credit <telegram_id> {amount:.2f} deposit:{tx_hash}` to credit the correct user."
            )
            for admin_id in ADMIN_IDS:
                try:
                    await self.bot.send_message(admin_id, msg, parse_mode="Markdown")
                except Exception:
                    pass

    # ──────────────────────────────────────────────────────────────────────────
    # Network adapters
    # ──────────────────────────────────────────────────────────────────────────

    async def _fetch_transactions(self, wallet: str) -> list[dict]:
        network = CRYPTO_NETWORK.lower()
        if network == "tron":
            return await self._fetch_tron(wallet)
        elif network == "ethereum":
            return await self._fetch_evm(wallet, "https://api.etherscan.io/api")
        elif network == "bsc":
            return await self._fetch_evm(wallet, "https://api.bscscan.com/api")
        else:
            logger.warning(f"Unsupported network: {network}")
            return []

    async def _fetch_tron(self, wallet: str) -> list[dict]:
        """Fetch recent TRC-20 USDT transfers to wallet via TronGrid."""
        contract = USDT_CONTRACTS["tron"]
        url = (
            f"https://api.trongrid.io/v1/accounts/{wallet}/transactions/trc20"
            f"?contract_address={contract}&limit=50&only_to=true"
        )
        headers = {}
        if BLOCKCHAIN_API_KEY:
            headers["TRON-PRO-API-KEY"] = BLOCKCHAIN_API_KEY

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    txns = data.get("data", [])
                    results = []
                    for tx in txns:
                        try:
                            amount = int(tx["value"]) / 1_000_000  # USDT has 6 decimals
                            results.append({
                                "hash":   tx["transaction_id"],
                                "amount": amount,
                                "from":   tx.get("from"),
                                "to":     tx.get("to"),
                            })
                        except (KeyError, ValueError):
                            continue
                    return results
        except Exception as e:
            logger.error(f"TronGrid fetch error: {e}")
            return []

    async def _fetch_evm(self, wallet: str, api_base: str) -> list[dict]:
        """Fetch ERC-20 / BEP-20 USDT transfers via Etherscan-compatible API."""
        network = CRYPTO_NETWORK.lower()
        contract = USDT_CONTRACTS.get(network, "")
        params = {
            "module":          "account",
            "action":          "tokentx",
            "contractaddress": contract,
            "address":         wallet,
            "sort":            "desc",
            "apikey":          BLOCKCHAIN_API_KEY or "freekey",
        }
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(api_base, params=params, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                    data = await resp.json()
                    txns = data.get("result", [])
                    if not isinstance(txns, list):
                        return []
                    results = []
                    for tx in txns:
                        if tx.get("to", "").lower() != wallet.lower():
                            continue
                        try:
                            decimals = int(tx.get("tokenDecimal", 6))
                            amount   = int(tx["value"]) / (10 ** decimals)
                            results.append({
                                "hash":   tx["hash"],
                                "amount": amount,
                                "from":   tx.get("from"),
                                "to":     tx.get("to"),
                            })
                        except (KeyError, ValueError):
                            continue
                    return results
        except Exception as e:
            logger.error(f"EVM fetch error: {e}")
            return []
