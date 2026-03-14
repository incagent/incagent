"""Tamper-evident transaction ledger using SQLite."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class Ledger:
    """Append-only, hash-chained transaction ledger."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                agent_id TEXT NOT NULL,
                action TEXT NOT NULL,
                data TEXT NOT NULL,
                signature TEXT NOT NULL DEFAULT '',
                prev_hash TEXT NOT NULL,
                hash TEXT NOT NULL UNIQUE
            );
            CREATE INDEX IF NOT EXISTS idx_entries_agent ON entries(agent_id);
            CREATE INDEX IF NOT EXISTS idx_entries_action ON entries(action);
        """)
        # Migration: add signature column if missing (existing DBs)
        try:
            self._conn.execute("SELECT signature FROM entries LIMIT 1")
        except Exception:
            self._conn.execute("ALTER TABLE entries ADD COLUMN signature TEXT NOT NULL DEFAULT ''")
        self._conn.commit()

    def _last_hash(self) -> str:
        row = self._conn.execute(
            "SELECT hash FROM entries ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return row["hash"] if row else "0" * 64

    @staticmethod
    def _compute_hash(timestamp: str, agent_id: str, action: str, data: str, prev_hash: str) -> str:
        payload = f"{timestamp}|{agent_id}|{action}|{data}|{prev_hash}"
        return hashlib.sha256(payload.encode()).hexdigest()

    def append(
        self,
        agent_id: str,
        action: str,
        data: dict[str, Any] | None = None,
        signature: str = "",
    ) -> int:
        """Append an entry to the ledger. Returns the entry id.

        If a signature is provided, it is stored alongside the entry
        for cryptographic attribution (Ed25519 hex signature of the data).
        """
        now = datetime.now(timezone.utc).isoformat()
        data_json = json.dumps(data or {}, sort_keys=True, separators=(",", ":"))
        prev = self._last_hash()
        entry_hash = self._compute_hash(now, agent_id, action, data_json, prev)

        cur = self._conn.execute(
            "INSERT INTO entries (timestamp, agent_id, action, data, signature, prev_hash, hash) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (now, agent_id, action, data_json, signature, prev, entry_hash),
        )
        self._conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def verify_chain(self) -> bool:
        """Verify the integrity of the entire ledger chain."""
        rows = self._conn.execute("SELECT * FROM entries ORDER BY id ASC").fetchall()
        prev_hash = "0" * 64
        for row in rows:
            expected = self._compute_hash(
                row["timestamp"], row["agent_id"], row["action"], row["data"], prev_hash
            )
            if row["hash"] != expected:
                return False
            if row["prev_hash"] != prev_hash:
                return False
            prev_hash = row["hash"]
        return True

    def query(
        self,
        agent_id: str | None = None,
        action: str | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Query ledger entries with optional filters."""
        sql = "SELECT * FROM entries WHERE 1=1"
        params: list[Any] = []
        if agent_id:
            sql += " AND agent_id = ?"
            params.append(agent_id)
        if action:
            sql += " AND action = ?"
            params.append(action)
        sql += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        rows = self._conn.execute(sql, params).fetchall()
        return [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "agent_id": r["agent_id"],
                "action": r["action"],
                "data": json.loads(r["data"]),
                "signature": r["signature"] if "signature" in r.keys() else "",
                "hash": r["hash"],
            }
            for r in rows
        ]

    def export_json(self, filepath: Path | str | None = None) -> str:
        """Export entire ledger as JSON."""
        rows = self._conn.execute("SELECT * FROM entries ORDER BY id ASC").fetchall()
        entries = [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "agent_id": r["agent_id"],
                "action": r["action"],
                "data": json.loads(r["data"]),
                "signature": r["signature"] if "signature" in r.keys() else "",
                "prev_hash": r["prev_hash"],
                "hash": r["hash"],
            }
            for r in rows
        ]
        output = json.dumps(entries, indent=2)
        if filepath:
            Path(filepath).write_text(output)
        return output

    def close(self) -> None:
        self._conn.close()
