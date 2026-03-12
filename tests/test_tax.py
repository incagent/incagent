"""Tax tracking module tests — USDC transaction records, vendor totals, 1099-NEC."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pytest

from incagent.tax import TaxTracker


@pytest.fixture
def tracker():
    tmp = tempfile.mkdtemp()
    db_path = Path(tmp) / "tax.db"
    t = TaxTracker(db_path)
    yield t
    t.close()
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)


class TestTaxRecording:
    def test_record_expense(self, tracker):
        tracker.record_payment(
            record_type="expense",
            counterparty_id="vendor_1",
            counterparty_name="CloudPeak",
            amount_usdc=500.0,
            tx_hash="0xabc123",
            contract_id="c_001",
            description="GPU hours purchase",
        )
        summary = tracker.get_year_summary(2026)
        assert summary["total_expenses"] == 500.0
        assert summary["total_income"] == 0.0

    def test_record_income(self, tracker):
        tracker.record_payment(
            record_type="income",
            counterparty_id="client_1",
            counterparty_name="BuyerCo",
            amount_usdc=1000.0,
        )
        summary = tracker.get_year_summary(2026)
        assert summary["total_income"] == 1000.0

    def test_multiple_records(self, tracker):
        tracker.record_payment("income", "c1", "Client A", 500.0)
        tracker.record_payment("income", "c2", "Client B", 300.0)
        tracker.record_payment("expense", "v1", "Vendor X", 200.0)

        summary = tracker.get_year_summary(2026)
        assert summary["total_income"] == 800.0
        assert summary["total_expenses"] == 200.0
        assert summary["net"] == 600.0

    def test_record_types(self, tracker):
        for rt in ("income", "expense", "escrow_in", "escrow_out", "refund"):
            tracker.record_payment(rt, "p1", "Partner", 100.0)
        summary = tracker.get_year_summary(2026)
        # income + refund = 200 income-side
        assert summary["total_income"] >= 100.0


class TestVendorTracking:
    def test_vendor_totals(self, tracker):
        tracker.record_payment("expense", "v1", "Vendor A", 300.0)
        tracker.record_payment("expense", "v1", "Vendor A", 400.0)

        vendors = tracker.get_vendor_summary(2026)
        assert len(vendors) == 1
        assert vendors[0]["vendor_name"] == "Vendor A"
        assert vendors[0]["total_paid"] == 700.0

    def test_1099_threshold(self, tracker):
        # Below threshold
        tracker.record_payment("expense", "v1", "Small Vendor", 500.0)
        assert len(tracker.get_vendors_needing_1099(2026)) == 0

        # At threshold
        tracker.record_payment("expense", "v1", "Small Vendor", 100.0)
        needing = tracker.get_vendors_needing_1099(2026)
        assert len(needing) == 1
        assert needing[0]["total_paid"] == 600.0

    def test_1099_multiple_vendors(self, tracker):
        tracker.record_payment("expense", "v1", "Big Vendor", 1000.0)
        tracker.record_payment("expense", "v2", "Small Vendor", 200.0)
        tracker.record_payment("expense", "v3", "Medium Vendor", 600.0)

        needing = tracker.get_vendors_needing_1099(2026)
        assert len(needing) == 2  # v1 and v3

    def test_no_1099_for_empty_year(self, tracker):
        # No records in a different year
        assert len(tracker.get_vendors_needing_1099(2020)) == 0


class TestExport:
    def test_export_json(self, tracker):
        tracker.record_payment("income", "c1", "Client", 500.0)
        tracker.record_payment("expense", "v1", "Vendor", 200.0)

        output = tracker.export_records(2026, format="json")
        import json
        data = json.loads(output)
        assert data["record_count"] == 2
        assert len(data["records"]) == 2

    def test_export_csv(self, tracker):
        tracker.record_payment("income", "c1", "Client", 500.0)
        tracker.record_payment("expense", "v1", "Vendor", 200.0)

        output = tracker.export_csv(2026)
        lines = output.strip().split("\n")
        assert len(lines) == 3  # header + 2 rows
        assert "timestamp" in lines[0]  # header

    def test_year_summary_counts(self, tracker):
        tracker.record_payment("expense", "v1", "V1", 700.0)
        tracker.record_payment("expense", "v2", "V2", 100.0)
        tracker.record_payment("income", "c1", "C1", 1000.0)

        summary = tracker.get_year_summary(2026)
        assert summary["vendor_count"] == 2
        assert summary["vendors_needing_1099"] == 1
        assert summary["record_count"] == 3
