"""Memory — persistent learning from trade history.

The agent learns from every interaction:
- Which partners are reliable
- What price ranges lead to successful deals
- Which negotiation strategies work
- Seasonal/temporal patterns
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("incagent.memory")


class Memory:
    """SQLite-backed agent memory for learning and strategy optimization."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS trade_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                partner_id TEXT NOT NULL,
                partner_name TEXT NOT NULL,
                contract_title TEXT NOT NULL,
                success INTEGER NOT NULL DEFAULT 0,
                final_price REAL,
                quantity INTEGER,
                rounds INTEGER,
                duration_ms INTEGER,
                error TEXT,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS partner_profiles (
                partner_id TEXT PRIMARY KEY,
                partner_name TEXT NOT NULL,
                total_trades INTEGER DEFAULT 0,
                successful_trades INTEGER DEFAULT 0,
                avg_price REAL,
                avg_rounds REAL,
                reliability_score REAL DEFAULT 0.5,
                last_trade TEXT,
                preferred_terms TEXT DEFAULT '{}',
                notes TEXT DEFAULT ''
            );

            CREATE TABLE IF NOT EXISTS learned_strategies (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_type TEXT NOT NULL,
                context TEXT NOT NULL,
                insight TEXT NOT NULL,
                confidence REAL DEFAULT 0.5,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                times_validated INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS heartbeat_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tick_number INTEGER NOT NULL,
                timestamp TEXT NOT NULL,
                data TEXT DEFAULT '{}'
            );

            CREATE INDEX IF NOT EXISTS idx_trade_partner ON trade_history(partner_id);
            CREATE INDEX IF NOT EXISTS idx_strategy_type ON learned_strategies(strategy_type);
        """)
        self._conn.commit()

    # ── Trade recording ──────────────────────────────────────────────

    def record_trade_attempt(
        self,
        partner_id: str,
        partner_name: str,
        contract_title: str,
        success: bool,
        final_price: float | None = None,
        quantity: int | None = None,
        rounds: int | None = None,
        duration_ms: int | None = None,
        error: str | None = None,
        metadata: dict | None = None,
    ) -> None:
        """Record a trade attempt and update partner profile."""
        now = datetime.now(timezone.utc).isoformat()

        self._conn.execute(
            """INSERT INTO trade_history
               (timestamp, partner_id, partner_name, contract_title, success,
                final_price, quantity, rounds, duration_ms, error, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (now, partner_id, partner_name, contract_title, int(success),
             final_price, quantity, rounds, duration_ms, error,
             json.dumps(metadata or {})),
        )
        self._conn.commit()

        # Update partner profile
        self._update_partner_profile(partner_id, partner_name, success, final_price, rounds)

    def _update_partner_profile(
        self, partner_id: str, partner_name: str, success: bool,
        price: float | None, rounds: int | None,
    ) -> None:
        """Update or create partner profile based on trade results."""
        now = datetime.now(timezone.utc).isoformat()
        existing = self._conn.execute(
            "SELECT * FROM partner_profiles WHERE partner_id = ?", (partner_id,)
        ).fetchone()

        if existing:
            total = existing["total_trades"] + 1
            successful = existing["successful_trades"] + (1 if success else 0)
            reliability = successful / total

            # Running average for price and rounds
            avg_price = existing["avg_price"] or 0
            if price is not None:
                avg_price = (avg_price * existing["total_trades"] + price) / total

            avg_rounds = existing["avg_rounds"] or 0
            if rounds is not None:
                avg_rounds = (avg_rounds * existing["total_trades"] + rounds) / total

            self._conn.execute(
                """UPDATE partner_profiles SET
                   total_trades = ?, successful_trades = ?,
                   avg_price = ?, avg_rounds = ?,
                   reliability_score = ?, last_trade = ?, partner_name = ?
                   WHERE partner_id = ?""",
                (total, successful, avg_price, avg_rounds, reliability, now, partner_name, partner_id),
            )
        else:
            self._conn.execute(
                """INSERT INTO partner_profiles
                   (partner_id, partner_name, total_trades, successful_trades,
                    avg_price, avg_rounds, reliability_score, last_trade)
                   VALUES (?, ?, 1, ?, ?, ?, ?, ?)""",
                (partner_id, partner_name, 1 if success else 0,
                 price, rounds, 1.0 if success else 0.0, now),
            )
        self._conn.commit()

    # ── Partner history ──────────────────────────────────────────────

    def get_partner_history(self, partner_id: str) -> dict[str, Any] | None:
        """Get aggregated history for a trading partner."""
        row = self._conn.execute(
            "SELECT * FROM partner_profiles WHERE partner_id = ?", (partner_id,)
        ).fetchone()
        if not row:
            return None
        return {
            "partner_id": row["partner_id"],
            "partner_name": row["partner_name"],
            "total_trades": row["total_trades"],
            "successful_trades": row["successful_trades"],
            "success_rate": row["reliability_score"],
            "avg_price": row["avg_price"],
            "avg_rounds": row["avg_rounds"],
            "last_trade": row["last_trade"],
        }

    def get_all_partners(self) -> list[dict[str, Any]]:
        """Get all partner profiles sorted by reliability."""
        rows = self._conn.execute(
            "SELECT * FROM partner_profiles ORDER BY reliability_score DESC"
        ).fetchall()
        return [
            {
                "partner_id": r["partner_id"],
                "partner_name": r["partner_name"],
                "total_trades": r["total_trades"],
                "success_rate": r["reliability_score"],
                "avg_price": r["avg_price"],
            }
            for r in rows
        ]

    # ── Strategy learning ────────────────────────────────────────────

    def learn_strategy(self, strategy_type: str, context: str, insight: str, confidence: float = 0.5) -> None:
        """Record a learned strategy insight."""
        now = datetime.now(timezone.utc).isoformat()

        # Check if similar insight exists
        existing = self._conn.execute(
            "SELECT id, times_validated, confidence FROM learned_strategies WHERE strategy_type = ? AND context = ?",
            (strategy_type, context),
        ).fetchone()

        if existing:
            # Reinforce existing insight
            new_confidence = min(1.0, existing["confidence"] + 0.1)
            self._conn.execute(
                """UPDATE learned_strategies SET
                   insight = ?, confidence = ?, updated_at = ?,
                   times_validated = times_validated + 1
                   WHERE id = ?""",
                (insight, new_confidence, now, existing["id"]),
            )
        else:
            self._conn.execute(
                """INSERT INTO learned_strategies
                   (strategy_type, context, insight, confidence, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (strategy_type, context, insight, confidence, now, now),
            )
        self._conn.commit()

    def get_strategies(self, strategy_type: str | None = None, min_confidence: float = 0.0) -> list[dict[str, Any]]:
        """Get learned strategies filtered by type and confidence."""
        sql = "SELECT * FROM learned_strategies WHERE confidence >= ?"
        params: list[Any] = [min_confidence]
        if strategy_type:
            sql += " AND strategy_type = ?"
            params.append(strategy_type)
        sql += " ORDER BY confidence DESC"

        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "strategy_type": r["strategy_type"],
                "context": r["context"],
                "insight": r["insight"],
                "confidence": r["confidence"],
                "times_validated": r["times_validated"],
            }
            for r in rows
        ]

    def get_optimal_terms(self, partner_id: str) -> dict[str, Any] | None:
        """Get optimized trade terms based on history with a partner."""
        profile = self.get_partner_history(partner_id)
        if not profile or profile["total_trades"] < 2:
            return None

        # Use historical average as baseline
        terms: dict[str, Any] = {}
        if profile["avg_price"]:
            terms["terms"] = {
                "unit_price": round(profile["avg_price"], 2),
                "currency": "USD",
                "payment_terms": "net_30",
            }
            terms["title"] = f"Optimized trade with {profile['partner_name']}"

        return terms if terms else None

    # ── Heartbeat log ────────────────────────────────────────────────

    def record_heartbeat(self, tick_number: int, data: dict | None = None) -> None:
        """Record a heartbeat tick."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            "INSERT INTO heartbeat_log (tick_number, timestamp, data) VALUES (?, ?, ?)",
            (tick_number, now, json.dumps(data or {})),
        )
        self._conn.commit()

    # ── Export / Stats ────────────────────────────────────────────────

    def stats(self) -> dict[str, Any]:
        """Get memory statistics."""
        trades = self._conn.execute("SELECT COUNT(*) as c FROM trade_history").fetchone()["c"]
        partners = self._conn.execute("SELECT COUNT(*) as c FROM partner_profiles").fetchone()["c"]
        strategies = self._conn.execute("SELECT COUNT(*) as c FROM learned_strategies").fetchone()["c"]
        heartbeats = self._conn.execute("SELECT COUNT(*) as c FROM heartbeat_log").fetchone()["c"]
        return {
            "total_trades": trades,
            "known_partners": partners,
            "learned_strategies": strategies,
            "heartbeat_ticks": heartbeats,
        }

    def export(self) -> dict[str, Any]:
        """Export all memory data."""
        return {
            "stats": self.stats(),
            "partners": self.get_all_partners(),
            "strategies": self.get_strategies(),
        }

    def close(self) -> None:
        self._conn.close()
