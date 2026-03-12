"""Tax tracking module for US corporate compliance.

Tracks all USDC transactions for tax reporting purposes:
- Income, expense, escrow, and refund records
- Per-vendor payment totals
- 1099-NEC threshold detection ($600/vendor/year)
- JSON and CSV export
"""

from __future__ import annotations

import csv
import io
import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

logger = logging.getLogger("incagent.tax")

# IRS 1099-NEC filing threshold
_1099_THRESHOLD = 600.0

_VALID_RECORD_TYPES = {"income", "expense", "escrow_in", "escrow_out", "refund"}


class TaxTracker:
    """SQLite-backed tracker for USDC transactions and tax compliance."""

    def __init__(self, db_path: Path | str) -> None:
        self._db_path = Path(db_path)
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self._db_path))
        self._conn.row_factory = sqlite3.Row
        self._init_db()

    def _init_db(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS tax_records (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                timestamp TEXT NOT NULL,
                record_type TEXT NOT NULL,
                counterparty_id TEXT NOT NULL,
                counterparty_name TEXT NOT NULL,
                amount_usdc REAL NOT NULL,
                tx_hash TEXT DEFAULT '',
                contract_id TEXT DEFAULT '',
                description TEXT DEFAULT '',
                tax_year INTEGER NOT NULL,
                metadata TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS vendor_totals (
                vendor_id TEXT NOT NULL,
                vendor_name TEXT NOT NULL,
                tax_year INTEGER NOT NULL,
                total_paid REAL DEFAULT 0,
                needs_1099 INTEGER DEFAULT 0,
                PRIMARY KEY (vendor_id, tax_year)
            );

            CREATE INDEX IF NOT EXISTS idx_tax_records_year
                ON tax_records(tax_year);
            CREATE INDEX IF NOT EXISTS idx_tax_records_counterparty
                ON tax_records(counterparty_id);
            CREATE INDEX IF NOT EXISTS idx_tax_records_type
                ON tax_records(record_type);
            CREATE INDEX IF NOT EXISTS idx_vendor_totals_year
                ON vendor_totals(tax_year);
        """)
        self._conn.commit()

    # ── Record transactions ───────────────────────────────────────────

    def record_payment(
        self,
        record_type: str,
        counterparty_id: str,
        counterparty_name: str,
        amount_usdc: float,
        tx_hash: str = "",
        contract_id: str = "",
        description: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> int:
        """Record a transaction and update vendor totals.

        Returns the record id.
        """
        if record_type not in _VALID_RECORD_TYPES:
            raise ValueError(
                f"Invalid record_type '{record_type}'. "
                f"Must be one of: {', '.join(sorted(_VALID_RECORD_TYPES))}"
            )

        now = datetime.now(timezone.utc)
        tax_year = now.year
        timestamp = now.isoformat()

        cur = self._conn.execute(
            """INSERT INTO tax_records
               (timestamp, record_type, counterparty_id, counterparty_name,
                amount_usdc, tx_hash, contract_id, description, tax_year, metadata)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                timestamp, record_type, counterparty_id, counterparty_name,
                amount_usdc, tx_hash, contract_id, description, tax_year,
                json.dumps(metadata or {}),
            ),
        )
        self._conn.commit()

        record_id: int = cur.lastrowid  # type: ignore[assignment]
        logger.info(
            "Recorded %s: %.2f USDC %s %s (id=%d)",
            record_type, amount_usdc,
            "from" if record_type == "income" else "to",
            counterparty_name, record_id,
        )

        # Update vendor totals for outbound payment types
        if record_type in ("expense", "escrow_out"):
            self._update_vendor_total(counterparty_id, counterparty_name, amount_usdc, tax_year)

        return record_id

    def _update_vendor_total(
        self,
        vendor_id: str,
        vendor_name: str,
        amount_usdc: float,
        tax_year: int,
    ) -> None:
        """Update vendor running total and check 1099-NEC threshold."""
        existing = self._conn.execute(
            "SELECT * FROM vendor_totals WHERE vendor_id = ? AND tax_year = ?",
            (vendor_id, tax_year),
        ).fetchone()

        if existing:
            new_total = existing["total_paid"] + amount_usdc
            needs_1099 = 1 if new_total >= _1099_THRESHOLD else 0
            self._conn.execute(
                """UPDATE vendor_totals
                   SET total_paid = ?, needs_1099 = ?, vendor_name = ?
                   WHERE vendor_id = ? AND tax_year = ?""",
                (new_total, needs_1099, vendor_name, vendor_id, tax_year),
            )
        else:
            needs_1099 = 1 if amount_usdc >= _1099_THRESHOLD else 0
            self._conn.execute(
                """INSERT INTO vendor_totals
                   (vendor_id, vendor_name, tax_year, total_paid, needs_1099)
                   VALUES (?, ?, ?, ?, ?)""",
                (vendor_id, vendor_name, tax_year, amount_usdc, needs_1099),
            )

        self._conn.commit()

        if needs_1099:
            logger.warning(
                "Vendor %s (%s) has reached 1099-NEC threshold: $%.2f in %d",
                vendor_name, vendor_id,
                amount_usdc if not existing else existing["total_paid"] + amount_usdc,
                tax_year,
            )

    # ── Summaries ─────────────────────────────────────────────────────

    def get_year_summary(self, tax_year: int) -> dict[str, Any]:
        """Get tax year summary: total income, expenses, net, vendor/1099 counts."""
        income = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usdc), 0) as total FROM tax_records "
            "WHERE tax_year = ? AND record_type = 'income'",
            (tax_year,),
        ).fetchone()["total"]

        expenses = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usdc), 0) as total FROM tax_records "
            "WHERE tax_year = ? AND record_type = 'expense'",
            (tax_year,),
        ).fetchone()["total"]

        escrow_in = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usdc), 0) as total FROM tax_records "
            "WHERE tax_year = ? AND record_type = 'escrow_in'",
            (tax_year,),
        ).fetchone()["total"]

        escrow_out = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usdc), 0) as total FROM tax_records "
            "WHERE tax_year = ? AND record_type = 'escrow_out'",
            (tax_year,),
        ).fetchone()["total"]

        refunds = self._conn.execute(
            "SELECT COALESCE(SUM(amount_usdc), 0) as total FROM tax_records "
            "WHERE tax_year = ? AND record_type = 'refund'",
            (tax_year,),
        ).fetchone()["total"]

        vendor_count = self._conn.execute(
            "SELECT COUNT(*) as c FROM vendor_totals WHERE tax_year = ?",
            (tax_year,),
        ).fetchone()["c"]

        vendors_needing_1099 = self._conn.execute(
            "SELECT COUNT(*) as c FROM vendor_totals WHERE tax_year = ? AND needs_1099 = 1",
            (tax_year,),
        ).fetchone()["c"]

        record_count = self._conn.execute(
            "SELECT COUNT(*) as c FROM tax_records WHERE tax_year = ?",
            (tax_year,),
        ).fetchone()["c"]

        return {
            "tax_year": tax_year,
            "total_income": round(income, 2),
            "total_expenses": round(expenses, 2),
            "net": round(income - expenses - refunds, 2),
            "escrow_in": round(escrow_in, 2),
            "escrow_out": round(escrow_out, 2),
            "total_refunds": round(refunds, 2),
            "vendor_count": vendor_count,
            "vendors_needing_1099": vendors_needing_1099,
            "record_count": record_count,
        }

    def get_vendor_summary(self, tax_year: int) -> list[dict[str, Any]]:
        """Get per-vendor totals with 1099-NEC flag for a tax year."""
        rows = self._conn.execute(
            """SELECT * FROM vendor_totals
               WHERE tax_year = ?
               ORDER BY total_paid DESC""",
            (tax_year,),
        ).fetchall()

        return [
            {
                "vendor_id": r["vendor_id"],
                "vendor_name": r["vendor_name"],
                "tax_year": r["tax_year"],
                "total_paid": round(r["total_paid"], 2),
                "needs_1099": bool(r["needs_1099"]),
                "threshold": _1099_THRESHOLD,
            }
            for r in rows
        ]

    def get_vendors_needing_1099(self, tax_year: int) -> list[dict[str, Any]]:
        """Get vendors who received >= $600 in a tax year (1099-NEC required)."""
        rows = self._conn.execute(
            """SELECT * FROM vendor_totals
               WHERE tax_year = ? AND needs_1099 = 1
               ORDER BY total_paid DESC""",
            (tax_year,),
        ).fetchall()

        return [
            {
                "vendor_id": r["vendor_id"],
                "vendor_name": r["vendor_name"],
                "tax_year": r["tax_year"],
                "total_paid": round(r["total_paid"], 2),
                "needs_1099": True,
                "threshold": _1099_THRESHOLD,
            }
            for r in rows
        ]

    # ── Export ────────────────────────────────────────────────────────

    def export_records(self, tax_year: int, format: str = "json") -> str:
        """Export all records for a tax year.

        Args:
            tax_year: The tax year to export.
            format: 'json' or 'csv'.

        Returns:
            Formatted string of all records.
        """
        if format == "csv":
            return self.export_csv(tax_year)
        if format != "json":
            raise ValueError(f"Unsupported format '{format}'. Use 'json' or 'csv'.")
        return self._export_json(tax_year)

    def _export_json(self, tax_year: int) -> str:
        """Export all records for a tax year as JSON."""
        rows = self._conn.execute(
            "SELECT * FROM tax_records WHERE tax_year = ? ORDER BY id ASC",
            (tax_year,),
        ).fetchall()

        records = [
            {
                "id": r["id"],
                "timestamp": r["timestamp"],
                "record_type": r["record_type"],
                "counterparty_id": r["counterparty_id"],
                "counterparty_name": r["counterparty_name"],
                "amount_usdc": round(r["amount_usdc"], 2),
                "tx_hash": r["tx_hash"],
                "contract_id": r["contract_id"],
                "description": r["description"],
                "tax_year": r["tax_year"],
                "metadata": json.loads(r["metadata"]),
            }
            for r in rows
        ]

        return json.dumps(
            {
                "tax_year": tax_year,
                "record_count": len(records),
                "summary": self.get_year_summary(tax_year),
                "records": records,
            },
            indent=2,
        )

    def export_csv(self, tax_year: int) -> str:
        """Export all records for a tax year as CSV."""
        rows = self._conn.execute(
            "SELECT * FROM tax_records WHERE tax_year = ? ORDER BY id ASC",
            (tax_year,),
        ).fetchall()

        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow([
            "id", "timestamp", "record_type", "counterparty_id",
            "counterparty_name", "amount_usdc", "tx_hash", "contract_id",
            "description", "tax_year", "metadata",
        ])
        for r in rows:
            writer.writerow([
                r["id"], r["timestamp"], r["record_type"],
                r["counterparty_id"], r["counterparty_name"],
                round(r["amount_usdc"], 2), r["tx_hash"], r["contract_id"],
                r["description"], r["tax_year"], r["metadata"],
            ])

        return output.getvalue()

    # ── Cleanup ───────────────────────────────────────────────────────

    def close(self) -> None:
        self._conn.close()
