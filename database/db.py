"""
database/db.py  –  SQLAlchemy async models + session helper
"""

from __future__ import annotations

import enum
from datetime import datetime, timezone

from sqlalchemy import (
    BigInteger, Boolean, Column, DateTime, Enum as SAEnum,
    Float, ForeignKey, Integer, String, Text, event,
)
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase, relationship

from config.settings import DATABASE_URL

engine = create_async_engine(DATABASE_URL, echo=False, future=True)
AsyncSessionLocal = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


# ── SQLite WAL mode for concurrency ──────────────────────────────────────────
@event.listens_for(engine.sync_engine, "connect")
def set_sqlite_pragma(dbapi_connection, _):
    if "sqlite" in DATABASE_URL:
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


# ── Base ───────────────────────────────────────────────────────────────────────
class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


# ──────────────────────────────────────────────────────────────────────────────
# Models
# ──────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"

    id         = Column(Integer, primary_key=True, autoincrement=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False, index=True)
    username   = Column(String(64), nullable=True)
    full_name  = Column(String(128), nullable=True)
    balance    = Column(Float, default=0.0, nullable=False)
    is_banned  = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=utcnow)
    last_seen  = Column(DateTime, default=utcnow, onupdate=utcnow)

    deposits    = relationship("Deposit",    back_populates="user", lazy="selectin")
    withdrawals = relationship("Withdrawal", back_populates="user", lazy="selectin")
    tx_logs     = relationship("TransactionLog", back_populates="user", lazy="selectin")

    def __repr__(self):
        return f"<User tg={self.telegram_id} bal={self.balance:.2f}>"


class DepositStatus(str, enum.Enum):
    DETECTED  = "detected"
    CONFIRMED = "confirmed"
    CREDITED  = "credited"


class Deposit(Base):
    __tablename__ = "deposits"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    tx_hash     = Column(String(128), unique=True, nullable=False)
    amount      = Column(Float, nullable=False)
    token       = Column(String(16), default="USDT")
    network     = Column(String(16), default="tron")
    status      = Column(SAEnum(DepositStatus), default=DepositStatus.DETECTED)
    created_at  = Column(DateTime, default=utcnow)
    credited_at = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="deposits")


class WithdrawalStatus(str, enum.Enum):
    PENDING  = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    PAID     = "paid"


class Withdrawal(Base):
    __tablename__ = "withdrawals"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    user_id      = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    amount       = Column(Float, nullable=False)
    destination  = Column(String(128), nullable=False)
    network      = Column(String(16), default="tron")
    status       = Column(SAEnum(WithdrawalStatus), default=WithdrawalStatus.PENDING)
    admin_note   = Column(Text, nullable=True)
    requested_at = Column(DateTime, default=utcnow)
    resolved_at  = Column(DateTime, nullable=True)

    user = relationship("User", back_populates="withdrawals")


class TradeSignal(Base):
    """Stores every signal/update posted by the admin or detected from the trading account."""
    __tablename__ = "trade_signals"

    id           = Column(Integer, primary_key=True, autoincrement=True)
    signal_type  = Column(String(32), nullable=False)   # open | update | close | summary
    asset        = Column(String(32), nullable=True)
    direction    = Column(String(8), nullable=True)      # BUY | SELL
    entry_price  = Column(Float, nullable=True)
    exit_price   = Column(Float, nullable=True)
    pnl_pct      = Column(Float, nullable=True)
    message      = Column(Text, nullable=False)
    broadcast_msg_id = Column(BigInteger, nullable=True) # Telegram message id
    posted_at    = Column(DateTime, default=utcnow)


class TransactionLog(Base):
    """Immutable audit log for every balance change."""
    __tablename__ = "transaction_logs"

    id          = Column(Integer, primary_key=True, autoincrement=True)
    user_id     = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    action      = Column(String(32), nullable=False)   # deposit | withdrawal | credit | debit | fee
    amount      = Column(Float, nullable=False)
    balance_before = Column(Float, nullable=False)
    balance_after  = Column(Float, nullable=False)
    reference   = Column(String(256), nullable=True)   # tx hash or withdrawal id
    note        = Column(Text, nullable=True)
    created_at  = Column(DateTime, default=utcnow)

    user = relationship("User", back_populates="tx_logs")


class BotSetting(Base):
    """Key-value store for runtime settings persisted across restarts."""
    __tablename__ = "bot_settings"

    key   = Column(String(64), primary_key=True)
    value = Column(Text, nullable=False)


# ── Helpers ────────────────────────────────────────────────────────────────────

async def init_db() -> None:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


def get_session() -> AsyncSession:
    """Return a new async session (use as async context manager)."""
    return AsyncSessionLocal()
