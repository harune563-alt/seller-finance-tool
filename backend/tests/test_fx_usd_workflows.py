import io
import os
import uuid
from datetime import date, timedelta

import pytest
import requests
from pymongo import MongoClient


# FX + USD-ledger regression coverage for CAD-native flows, USD costs, payouts, legacy records, and CSV import
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def mongo_db():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL or DB_NAME not set")
    client = MongoClient(mongo_url)
    db = client[db_name]
    yield db
    client.close()


@pytest.fixture(scope="session")
def admin_session(base_url):
    s = requests.Session()
    login = s.post(
        f"{base_url}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert login.status_code == 200
    token = login.json().get("token")
    assert isinstance(token, str) and token
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture
def isolated_store(admin_session, base_url):
    payload = {
        "name": f"TEST_FX_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US", "CA", "UK", "DE"],
        "default_currency": "USD",
    }
    create = admin_session.post(f"{base_url}/api/stores", json=payload, timeout=20)
    assert create.status_code == 200
    store = create.json()
    yield store
    admin_session.delete(f"{base_url}/api/stores/{store['id']}", timeout=20)


def _find_native(summary, currency):
    return next((row for row in summary.get("native_balances", []) if row.get("currency") == currency), None)


def _tx(
    store_id,
    marketplace,
    tx_type,
    category,
    amount,
    currency,
    tx_date,
    order_id,
    **kwargs,
):
    payload = {
        "store_id": store_id,
        "marketplace": marketplace,
        "type": tx_type,
        "category": category,
        "amount": amount,
        "currency": currency,
        "date": tx_date,
        "description": "",
        "order_id": order_id,
        "product_cost": 0,
        "shipping_cost": 0,
        "extra_cost": 0,
        "product_cost_recovery": 0,
        "shipping_cost_recovery": 0,
    }
    payload.update(kwargs)
    return payload


def test_fx_quote_endpoint_contract_and_validation(admin_session, base_url):
    cad = admin_session.get(
        f"{base_url}/api/fx/to-usd",
        params={"currency": "CAD", "date": "2025-01-15"},
        timeout=20,
    )
    assert cad.status_code == 200
    q = cad.json()
    assert q["base"] == "CAD"
    assert q["quote"] == "USD"
    assert q["requested_date"] == "2025-01-15"
    assert q["rate_date"] <= q["requested_date"]
    assert float(q["rate"]) > 0

    usd = admin_session.get(
        f"{base_url}/api/fx/to-usd",
        params={"currency": "USD", "date": "2025-01-15"},
        timeout=20,
    )
    assert usd.status_code == 200
    assert float(usd.json()["rate"]) == 1.0

    unsupported = admin_session.get(
        f"{base_url}/api/fx/to-usd",
        params={"currency": "NOK", "date": "2025-01-15"},
        timeout=20,
    )
    assert unsupported.status_code == 422

    future_date = (date.today() + timedelta(days=3)).isoformat()
    future = admin_session.get(
        f"{base_url}/api/fx/to-usd",
        params={"currency": "CAD", "date": future_date},
        timeout=20,
    )
    assert future.status_code == 422


def test_all_supported_currencies_return_historical_quotes(admin_session, base_url):
    supported = ["USD", "CAD", "MXN", "GBP", "EUR", "AUD", "JPY", "AED", "SAR", "TRY", "SEK", "PLN"]
    for currency in supported:
        r = admin_session.get(
            f"{base_url}/api/fx/to-usd",
            params={"currency": currency, "date": "2025-01-15"},
            timeout=20,
        )
        assert r.status_code == 200
        q = r.json()
        assert q["base"] == currency
        assert q["requested_date"] == "2025-01-15"
        assert q["rate_date"] <= "2025-01-15"
        assert float(q["rate"]) > 0


def test_weekend_request_uses_provider_rate_date_not_invented(admin_session, base_url):
    weekend = admin_session.get(
        f"{base_url}/api/fx/to-usd",
        params={"currency": "CAD", "date": "2025-01-19"},
        timeout=20,
    )
    assert weekend.status_code == 200
    q = weekend.json()
    assert q["requested_date"] == "2025-01-19"
    assert q["rate_date"] <= q["requested_date"]
    assert float(q["rate"]) > 0


def test_cad_income_uses_usd_costs_and_native_balance_is_cad(admin_session, base_url, isolated_store):
    order_id = f"FX-ORDER-{uuid.uuid4().hex[:6]}"
    create = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(
            isolated_store["id"],
            "CA",
            "income",
            "Order payments",
            100,
            "CAD",
            "2025-01-15",
            order_id,
            product_cost=20,
            shipping_cost=5,
            extra_cost=3,
        ),
        timeout=20,
    )
    assert create.status_code == 200
    row = create.json()
    assert row["currency"] == "CAD"
    assert row["cost_currency"] == "USD"
    assert row["amount"] == 100
    assert row["amount_usd"] == pytest.approx(69.63, abs=0.03)
    assert row["usd_costs"]["product_cost"] == pytest.approx(20.0, abs=0.001)
    assert row["usd_costs"]["shipping_cost"] == pytest.approx(5.0, abs=0.001)
    assert row["usd_costs"]["extra_cost"] == pytest.approx(3.0, abs=0.001)

    listing = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "CA"},
        timeout=20,
    )
    assert listing.status_code == 200
    persisted = [r for r in listing.json() if r["id"] == row["id"]]
    assert len(persisted) == 1
    assert persisted[0]["amount_usd"] == pytest.approx(69.63, abs=0.03)

    summary = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "CA"},
        timeout=20,
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["currency"] == "USD"
    assert s["source_currency"] == "ALL"
    assert s["revenue"] == pytest.approx(69.63, abs=0.03)
    assert s["expenses"] == pytest.approx(28.0, abs=0.03)
    assert s["net_profit"] == pytest.approx(41.63, abs=0.03)
    cad_bucket = _find_native(s, "CAD")
    assert cad_bucket is not None
    assert cad_bucket["amazon_balance"] == pytest.approx(100.0, abs=0.001)


def test_refunds_fees_and_payout_math_keep_native_balance(admin_session, base_url, isolated_store):
    oid = f"FX-MATH-{uuid.uuid4().hex[:6]}"
    sale = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(isolated_store["id"], "CA", "income", "Order payments", 100, "CAD", "2025-01-15", oid, product_cost=20, shipping_cost=5, extra_cost=3),
        timeout=20,
    )
    assert sale.status_code == 200

    refund = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(
            isolated_store["id"],
            "CA",
            "expense",
            "Refunds",
            20,
            "CAD",
            "2025-01-15",
            oid,
            product_cost_recovery=10,
            shipping_cost_recovery=2,
        ),
        timeout=20,
    )
    assert refund.status_code == 200
    r = refund.json()
    assert r["amount_usd"] == pytest.approx(13.93, abs=0.03)

    fee = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(isolated_store["id"], "CA", "expense", "Service Fees", 5, "CAD", "2025-01-15", oid),
        timeout=20,
    )
    assert fee.status_code == 200
    assert fee.json()["amount_usd"] == pytest.approx(3.48, abs=0.03)

    pending = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(isolated_store["id"], "CA", "payout", "Oluşturuldu", 10, "CAD", "2025-01-15", oid),
        timeout=20,
    )
    assert pending.status_code == 200

    banked = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(isolated_store["id"], "CA", "payout", "Bankada", 50, "CAD", "2025-01-15", oid),
        timeout=20,
    )
    assert banked.status_code == 200

    summary = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "CA"},
        timeout=20,
    )
    assert summary.status_code == 200
    s = summary.json()
    assert s["net_profit"] == pytest.approx(36.22, abs=0.03)
    assert s["margin"] == pytest.approx(52.02, abs=0.05)
    cad_bucket = _find_native(s, "CAD")
    assert cad_bucket is not None
    assert cad_bucket["amazon_balance"] == pytest.approx(25.0, abs=0.001)
    assert cad_bucket["payouts_received"] == pytest.approx(50.0, abs=0.001)


def test_fx_snapshot_immutable_when_editing_costs(admin_session, base_url, isolated_store):
    oid = f"IMMUT-{uuid.uuid4().hex[:6]}"
    create = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(
            isolated_store["id"], "CA", "income", "Order payments", 100, "CAD", "2025-01-15", oid,
            product_cost=5, shipping_cost=2, extra_cost=1,
        ),
        timeout=20,
    )
    assert create.status_code == 200
    row = create.json()
    fx_before = row["fx"]
    amount_usd_before = row["amount_usd"]

    patch = admin_session.patch(
        f"{base_url}/api/transactions/{row['id']}/costs",
        json={
            "product_cost": 20,
            "shipping_cost": 5,
            "extra_cost": 3,
            "product_cost_recovery": 0,
            "shipping_cost_recovery": 0,
        },
        timeout=20,
    )
    assert patch.status_code == 200
    edited = patch.json()
    assert edited["fx"] == fx_before
    assert edited["amount_usd"] == amount_usd_before
    assert edited["cost_currency"] == "USD"
    assert edited["usd_costs"]["product_cost"] == 20

    reloaded = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "CA"},
        timeout=20,
    )
    assert reloaded.status_code == 200
    same = next(r for r in reloaded.json() if r["id"] == row["id"])
    assert same["fx"] == fx_before
    assert same["amount_usd"] == amount_usd_before


def test_legacy_record_enriched_without_overwriting_native_costs(admin_session, base_url, isolated_store, mongo_db):
    tx_id = f"legacy-{uuid.uuid4().hex[:10]}"
    user = admin_session.get(f"{base_url}/api/auth/me", timeout=20).json()
    legacy = {
        "id": tx_id,
        "user_id": user["id"],
        "store_id": isolated_store["id"],
        "marketplace": "CA",
        "type": "income",
        "category": "Order payments",
        "amount": 100,
        "currency": "CAD",
        "date": "2025-01-15",
        "description": "legacy fixture",
        "order_id": f"LEG-{uuid.uuid4().hex[:5]}",
        "product_cost": 20,
        "shipping_cost": 5,
        "extra_cost": 3,
        "product_cost_recovery": 0,
        "shipping_cost_recovery": 0,
        "created_at": "2026-01-01T00:00:00+00:00",
        "source": "manual",
    }
    mongo_db.transactions.insert_one(legacy)

    listed = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "CA", "limit": 10000},
        timeout=20,
    )
    assert listed.status_code == 200
    row = next(r for r in listed.json() if r["id"] == tx_id)
    assert row["cost_currency"] == "CAD"
    assert row["amount_usd"] == pytest.approx(69.63, abs=0.03)
    assert row["usd_costs"]["product_cost"] == pytest.approx(13.93, abs=0.03)
    assert row["usd_costs"]["shipping_cost"] == pytest.approx(3.48, abs=0.03)
    assert row["usd_costs"]["extra_cost"] == pytest.approx(2.09, abs=0.03)

    raw_after_read = mongo_db.transactions.find_one({"id": tx_id}, {"_id": 0})
    assert raw_after_read["product_cost"] == 20
    assert raw_after_read["shipping_cost"] == 5
    assert raw_after_read["extra_cost"] == 3

    patch = admin_session.patch(
        f"{base_url}/api/transactions/{tx_id}/costs",
        json={
            "product_cost": 30,
            "shipping_cost": 4,
            "extra_cost": 1,
            "product_cost_recovery": 0,
            "shipping_cost_recovery": 0,
        },
        timeout=20,
    )
    assert patch.status_code == 200
    updated = patch.json()
    assert updated["cost_currency"] == "USD"
    stored = mongo_db.transactions.find_one({"id": tx_id}, {"_id": 0, "original_costs": 1})
    assert stored["original_costs"]["currency"] == "CAD"
    assert stored["original_costs"]["product_cost"] == 20


def test_summary_consolidates_usd_and_cad_but_keeps_native_buckets(admin_session, base_url, isolated_store):
    oid = f"MIX-{uuid.uuid4().hex[:6]}"
    us = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(isolated_store["id"], "US", "income", "Order payments", 50, "USD", "2025-01-15", oid, product_cost=5),
        timeout=20,
    )
    ca = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(isolated_store["id"], "CA", "income", "Order payments", 100, "CAD", "2025-01-15", oid, product_cost=10),
        timeout=20,
    )
    assert us.status_code == 200
    assert ca.status_code == 200

    all_summary = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "ALL"},
        timeout=20,
    )
    assert all_summary.status_code == 200
    s_all = all_summary.json()
    assert s_all["currency"] == "USD"
    assert s_all["source_currency"] == "ALL"
    assert _find_native(s_all, "USD") is not None
    assert _find_native(s_all, "CAD") is not None

    cad_only = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "ALL", "currency": "CAD"},
        timeout=20,
    )
    assert cad_only.status_code == 200
    s_cad = cad_only.json()
    assert s_cad["currency"] == "USD"
    assert s_cad["source_currency"] == "CAD"

    txs = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "ALL", "limit": 10000},
        timeout=20,
    )
    assert txs.status_code == 200
    currencies = {row["currency"] for row in txs.json()}
    assert "USD" in currencies
    assert "CAD" in currencies


def test_csv_import_commits_fx_snapshot_and_is_idempotent(admin_session, base_url, isolated_store):
    csv_body = (
        "Date,Transaction type,Total (CAD),Order Id\n"
        "2025-01-15,Order,100,CSV-CAD-1\n"
        "2025-01-16,Refund,-20,CSV-CAD-1\n"
    )
    params = {"store_id": isolated_store["id"], "marketplace": "CA", "commit": "true"}
    files = {"file": ("cad_payments.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    first = admin_session.post(f"{base_url}/api/transactions/import", files=files, params=params, timeout=20)
    assert first.status_code == 200
    a = first.json()
    assert a["committed"] is True
    assert a["inserted"] == 2

    rows = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "CA", "limit": 10000},
        timeout=20,
    )
    assert rows.status_code == 200
    created = [r for r in rows.json() if r.get("order_id") == "CSV-CAD-1"]
    assert len(created) == 2
    assert all(r.get("amount_usd") is not None for r in created)
    assert all(r.get("cost_currency") == "USD" for r in created)
    assert all(r.get("product_cost", 0) == 0 for r in created)

    files_repeat = {"file": ("cad_payments.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    second = admin_session.post(f"{base_url}/api/transactions/import", files=files_repeat, params=params, timeout=20)
    assert second.status_code == 200
    b = second.json()
    assert b["inserted"] == 0
    assert b["duplicates"] >= 2


def test_csv_future_date_rejected_before_insert(admin_session, base_url, isolated_store):
    future = (date.today() + timedelta(days=5)).isoformat()
    csv_body = f"Date,Transaction type,Total (CAD),Order Id\n{future},Order,100,FUTURE-1\n"

    count_before = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "CA", "limit": 10000},
        timeout=20,
    )
    assert count_before.status_code == 200
    before_len = len(count_before.json())

    files = {"file": ("future.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    commit = admin_session.post(
        f"{base_url}/api/transactions/import",
        files=files,
        params={"store_id": isolated_store["id"], "marketplace": "CA", "commit": "true"},
        timeout=20,
    )
    assert commit.status_code == 422

    count_after = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"], "marketplace": "CA", "limit": 10000},
        timeout=20,
    )
    assert count_after.status_code == 200
    assert len(count_after.json()) == before_len
