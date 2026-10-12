"""Focused tests for Amazon payout -> Cash Flow integration (iteration 15).

Verifies:
- Bankada payout creates exactly ONE AMAZON_DISBURSEMENT cash-in entry.
- Idempotent across repeated/concurrent reads and re-saves.
- İşleniyor -> Bankada status change creates the entry once.
- Normal income (order payments) is NOT counted as cash-in.
- summary cash_in / net_cash_flow / closing_cash reflect the payout.
"""
import asyncio
import os
import uuid
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fba-finance-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def client():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    r = s.post(f"{API}/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    token = r.json().get("access_token") or r.json().get("token")
    assert token, f"no token in {r.json()}"
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture(scope="module")
def store(client):
    # Create isolated test store with CA marketplace / CAD currency
    name = f"TEST_CF_DISB_{uuid.uuid4().hex[:6]}"
    r = client.post(f"{API}/stores", json={
        "name": name, "marketplaces": ["CA"], "default_currency": "CAD"
    })
    assert r.status_code in (200, 201), f"store create failed: {r.status_code} {r.text}"
    s = r.json()
    yield s
    # Teardown: delete all transactions for store, then store
    try:
        txs = client.get(f"{API}/transactions", params={"store_id": s["id"], "limit": 1000}).json()
        if txs:
            ids = [t["id"] for t in txs]
            client.post(f"{API}/transactions/bulk-delete", json={"ids": ids})
    except Exception:
        pass
    try:
        client.delete(f"{API}/stores/{s['id']}")
    except Exception:
        pass


def _make_payout(client, store_id, *, category, amount=100, ref=None, date="2025-10-01"):
    body = {
        "store_id": store_id, "marketplace": "CA", "type": "payout",
        "category": category, "amount": amount, "currency": "CAD",
        "date": date, "payment_reference": ref or "",
    }
    r = client.post(f"{API}/transactions", json=body)
    assert r.status_code == 200, f"payout create failed: {r.status_code} {r.text}"
    return r.json()


def _entries(client, store_id):
    r = client.get(f"{API}/cashflow/entries", params={"store_id": store_id})
    assert r.status_code == 200, f"cashflow entries failed: {r.status_code} {r.text}"
    return r.json()


def _summary(client, store_id):
    r = client.get(f"{API}/cashflow/summary", params={"store_id": store_id})
    assert r.status_code == 200, f"cashflow summary failed: {r.status_code} {r.text}"
    return r.json()


# ---- Test 1: Bankada payout creates exactly one AMAZON_DISBURSEMENT ----
def test_bankada_payout_creates_one_disbursement_entry(client, store):
    ref = f"TEST-REF-{uuid.uuid4().hex[:6]}"
    payout = _make_payout(client, store["id"], category="Bankada", amount=100, ref=ref)
    data = _entries(client, store["id"])
    disbs = [r for r in data["rows"] if r["source_type"] == "AMAZON_DISBURSEMENT"]
    assert len(disbs) == 1, f"expected 1 AMAZON_DISBURSEMENT, got {len(disbs)}: {disbs}"
    e = disbs[0]
    assert e["direction"] == "IN"
    assert e["original_amount"] == 100.0
    assert e["original_currency"] == "CAD"
    assert e["payment_reference"] == ref
    assert e["source_id"] == payout["id"]
    # CAD->USD typically 0.70-0.78 USD per CAD; cash_in ~70-78
    assert e["cash_in"] is not None and 50 < e["cash_in"] < 100, f"cash_in out of CAD range: {e['cash_in']}"
    assert e["cash_out"] is None


# ---- Test 2: Summary reflects the payout cash-in ----
def test_summary_reflects_disbursement(client, store):
    s = _summary(client, store["id"])
    assert s["cash_in"] > 0, s
    assert s["net_cash_flow"] == pytest.approx(s["cash_in"] - s["cash_out"], abs=0.02)
    assert s["closing_cash"] == pytest.approx(s["opening_cash"] + s["net_cash_flow"], abs=0.02)


# ---- Test 3: Idempotent across repeated reads ----
def test_repeated_reads_do_not_duplicate(client, store):
    for _ in range(5):
        _entries(client, store["id"])
        _summary(client, store["id"])
    data = _entries(client, store["id"])
    disbs = [r for r in data["rows"] if r["source_type"] == "AMAZON_DISBURSEMENT"]
    assert len(disbs) == 1, f"duplication after repeated reads: {len(disbs)}"


# ---- Test 4: Concurrent reads do not duplicate ----
def test_concurrent_reads_do_not_duplicate(client, store):
    async def hammer():
        loop = asyncio.get_event_loop()
        tasks = [loop.run_in_executor(None, lambda: _entries(client, store["id"])) for _ in range(10)]
        await asyncio.gather(*tasks)
    asyncio.run(hammer())
    data = _entries(client, store["id"])
    disbs = [r for r in data["rows"] if r["source_type"] == "AMAZON_DISBURSEMENT"]
    assert len(disbs) == 1, f"duplication after concurrent reads: {len(disbs)}"


# ---- Test 5: Re-save (PUT) same payout -> still one entry ----
def test_resave_payout_no_duplicate(client, store):
    data = _entries(client, store["id"])
    disb = next(r for r in data["rows"] if r["source_type"] == "AMAZON_DISBURSEMENT")
    tx_id = disb["source_id"]
    body = {
        "store_id": store["id"], "marketplace": "CA", "type": "payout",
        "category": "Bankada", "amount": 100, "currency": "CAD",
        "date": "2025-10-01", "payment_reference": disb["payment_reference"],
    }
    r = client.put(f"{API}/transactions/{tx_id}", json=body)
    assert r.status_code == 200, f"update failed: {r.status_code} {r.text}"
    after = _entries(client, store["id"])
    disbs = [r for r in after["rows"] if r["source_type"] == "AMAZON_DISBURSEMENT"]
    assert len(disbs) == 1, f"duplicate after re-save: {len(disbs)}"
    assert disbs[0]["source_id"] == tx_id


# ---- Test 6: İşleniyor -> no entry; transition to Bankada -> one entry ----
def test_isleniyor_to_bankada_transition(client, store):
    ref2 = f"TEST-REF2-{uuid.uuid4().hex[:6]}"
    payout = _make_payout(client, store["id"], category="İşleniyor", amount=50, ref=ref2, date="2025-10-05")
    data = _entries(client, store["id"])
    for r in data["rows"]:
        assert r.get("source_id") != payout["id"], f"İşleniyor should not create cash flow entry: {r}"

    # Transition to Bankada
    body = {
        "store_id": store["id"], "marketplace": "CA", "type": "payout",
        "category": "Bankada", "amount": 50, "currency": "CAD",
        "date": "2025-10-05", "payment_reference": ref2,
    }
    r = client.put(f"{API}/transactions/{payout['id']}", json=body)
    assert r.status_code == 200, r.text

    data = _entries(client, store["id"])
    matching = [r for r in data["rows"] if r["source_type"] == "AMAZON_DISBURSEMENT" and r["source_id"] == payout["id"]]
    assert len(matching) == 1, f"expected one entry after transition, got {len(matching)}"
    assert matching[0]["original_amount"] == 50.0
    assert matching[0]["payment_reference"] == ref2


# ---- Test 7: Amazon income (Order payments) must NOT be a cash-in entry ----
def test_income_not_cash_in(client, store):
    body = {
        "store_id": store["id"], "marketplace": "CA", "type": "income",
        "category": "Order payments", "amount": 200, "currency": "CAD",
        "date": "2025-10-02",
    }
    r = client.post(f"{API}/transactions", json=body)
    assert r.status_code == 200, r.text
    income_id = r.json()["id"]

    data = _entries(client, store["id"])
    cash_in_rows = [r for r in data["rows"] if r["direction"] == "IN"]
    # Must not include the income tx id
    assert all(r.get("source_id") != income_id for r in cash_in_rows), \
        f"Order payment leaked into cash_in: {[r for r in cash_in_rows if r.get('source_id') == income_id]}"
    # And no AMAZON_PAYMENT source entries should appear
    amazon_payment_rows = [r for r in data["rows"] if r["source_type"] == "AMAZON_PAYMENT"]
    assert amazon_payment_rows == [], f"legacy AMAZON_PAYMENT entries present: {amazon_payment_rows}"
