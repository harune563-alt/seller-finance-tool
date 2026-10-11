import asyncio
import sys
from pathlib import Path

import pytest

sys.path.append(str(Path(__file__).resolve().parents[1]))

from fx_service import FxError
import usd_ledger


# Unit-mock coverage for FX provider failure handling, offline snapshots, and payout bypass


class _DummyTransactions:
    async def update_one(self, *_args, **_kwargs):
        return None

    async def find_one(self, *_args, **_kwargs):
        return None


class _DummyDb:
    def __init__(self):
        self.transactions = _DummyTransactions()


def test_payout_does_not_require_fx_quote(monkeypatch):
    called = {"value": False}

    async def _boom(*_args, **_kwargs):
        called["value"] = True
        raise FxError("should not be called")

    monkeypatch.setattr(usd_ledger, "get_rate", _boom)
    doc = {
        "id": "tx-1",
        "user_id": "u-1",
        "type": "payout",
        "category": "Bankada",
        "amount": 50,
        "currency": "CAD",
        "date": "2025-01-15",
    }
    enriched = asyncio.run(usd_ledger.attach_usd(_DummyDb(), doc))
    assert enriched["fx_status"] == "not_required"
    assert enriched["amount_usd"] == 0
    assert called["value"] is False


def test_existing_snapshot_remains_usable_offline(monkeypatch):
    async def _boom(*_args, **_kwargs):
        raise FxError("provider down")

    monkeypatch.setattr(usd_ledger, "get_rate", _boom)
    doc = {
        "id": "tx-2",
        "user_id": "u-1",
        "type": "income",
        "category": "Order payments",
        "amount": 100,
        "currency": "CAD",
        "date": "2025-01-15",
        "fx": {"base": "CAD", "quote": "USD", "rate": "0.69634", "requested_date": "2025-01-15", "rate_date": "2025-01-15", "source": "frankfurter-v2", "fetched_at": "2026-01-01T00:00:00+00:00"},
        "amount_usd": 69.63,
        "usd_costs": {"product_cost": 20, "shipping_cost": 5, "extra_cost": 3, "product_cost_recovery": 0, "shipping_cost_recovery": 0},
    }
    enriched = asyncio.run(usd_ledger.attach_usd(_DummyDb(), doc))
    assert enriched["fx_status"] == "ready"
    assert enriched["amount_usd"] == 69.63


def test_unavailable_fx_nulls_totals_but_keeps_native_balances():
    docs = [
        {
            "id": "sale-1",
            "type": "income",
            "category": "Order payments",
            "amount": 100,
            "currency": "CAD",
            "marketplace": "CA",
            "date": "2025-01-15",
            "amount_usd": None,
            "usd_costs": {},
            "fx_status": "unavailable",
            "fx_error": "CAD/USD unavailable",
        },
        {
            "id": "payout-1",
            "type": "payout",
            "category": "Bankada",
            "amount": 50,
            "currency": "CAD",
            "marketplace": "CA",
            "date": "2025-01-16",
            "amount_usd": 0,
            "usd_costs": {"product_cost": 0, "shipping_cost": 0, "extra_cost": 0, "product_cost_recovery": 0, "shipping_cost_recovery": 0},
            "fx_status": "not_required",
            "fx_error": None,
        },
    ]
    summary = usd_ledger.summary_usd(docs)
    assert summary["incomplete_count"] == 1
    assert summary["revenue"] is None
    assert summary["expenses"] is None
    assert summary["net_profit"] is None
    assert summary["margin"] is None
    native = next(row for row in summary["native_balances"] if row["currency"] == "CAD")
    assert native["amazon_balance"] == pytest.approx(50.0, abs=0.001)
    assert native["payouts_received"] == pytest.approx(50.0, abs=0.001)
