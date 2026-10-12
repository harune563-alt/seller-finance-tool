"""Sermaye & Kasa -> Nakit Akışı integration tests (iteration 17).

Covers:
  - Capital contribution/withdrawal -> cash-flow entries with stable source_id
  - Idempotency (no duplicates on reload / concurrent GET / repeated POST)
  - Profit/Loss (/portfolio/summary, /dashboard/summary) is NOT affected
  - Edit + delete propagate to cash-flow entries
  - Company-wide /company/cash deposit visible only in ALL scope (not per-store)
  - Opening cash: manual opening superseded by Sermaye & Kasa capital
"""
import os
import uuid
import asyncio
import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "admin@amzsuite.com", "password": "admin123"}


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers["Content-Type"] = "application/json"
    r = s.post(f"{BASE}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    s.headers["Authorization"] = f"Bearer {r.json()['token']}"
    return s


@pytest.fixture(scope="module")
def ctx(session):
    """Create test store + person. Teardown removes everything we created."""
    created = {"capital_ids": [], "cash_ids": []}

    store_name = f"TEST_CAP_{uuid.uuid4().hex[:6]}"
    r = session.post(f"{BASE}/stores",
                     json={"name": store_name, "marketplaces": ["US"], "default_currency": "USD"},
                     timeout=30)
    assert r.status_code in (200, 201), r.text
    store = r.json()
    store_id = store.get("id") or store.get("_id") or store["store_id"]

    r = session.post(f"{BASE}/company/people",
                     json={"name": f"TEST_P_{uuid.uuid4().hex[:4]}", "role": "partner", "note": ""},
                     timeout=30)
    assert r.status_code in (200, 201), r.text
    person_id = r.json()["id"]

    data = {"store_id": store_id, "person_id": person_id, "store_name": store_name, "created": created}
    yield data

    # ---- teardown ----
    for cid in created["capital_ids"]:
        session.delete(f"{BASE}/company/capital/{cid}", timeout=30)
    for cid in created["cash_ids"]:
        session.delete(f"{BASE}/company/cash/{cid}", timeout=30)
    # opening balance -> set to 0 (no explicit delete endpoint)
    session.put(f"{BASE}/cashflow/opening-balance",
                json={"store_id": store_id, "amount_usd": 0, "note": "cleanup"}, timeout=30)
    session.delete(f"{BASE}/company/people/{person_id}", timeout=30)
    session.delete(f"{BASE}/stores/{store_id}", timeout=30)


# ---------- helpers ----------
def _entries(session, store_id):
    r = session.get(f"{BASE}/cashflow/entries", params={"store_id": store_id}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _summary(session, store_id):
    r = session.get(f"{BASE}/cashflow/summary", params={"store_id": store_id}, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


# ---------- TEST 1 : capital contribution ----------
def test_1_capital_contribution_creates_single_cashflow_entry(session, ctx):
    req_id = str(uuid.uuid4())
    payload = {"request_id": req_id, "amount": "5000", "date": "2026-10-01", "note": "",
               "person_id": ctx["person_id"], "store_id": ctx["store_id"],
               "currency": "USD", "direction": "contribution"}
    r = session.post(f"{BASE}/company/capital", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    cap_entry = next(e for e in body["entries"] if e["id"] == req_id)
    ctx["capital_entry_id"] = cap_entry["id"]
    ctx["created"]["capital_ids"].append(cap_entry["id"])

    data = _entries(session, ctx["store_id"])
    rows = [row for row in data["rows"] if row["source_type"] == "CAPITAL_INJECTION"]
    assert len(rows) == 1, rows
    row = rows[0]
    assert row["direction"] == "IN"
    assert row["cash_in"] == 5000.0
    assert row["source_module"] == "Sermaye & Kasa"
    assert row["source_id"] == cap_entry["id"]
    assert row["marketplace"] == ""
    assert row["store_id"] == ctx["store_id"]

    s = _summary(session, ctx["store_id"])
    assert s["cash_in"] == 5000.0
    assert s["opening_cash"] == 0.0
    assert s["opening_source"] == "sermaye_kasa"


# ---------- TEST 2 : withdrawal, idempotency, no duplicates on repeated GET ----------
def test_2_withdrawal_and_idempotent_reload(session, ctx):
    req_id = str(uuid.uuid4())
    payload = {"request_id": req_id, "amount": "500", "date": "2026-10-05", "note": "",
               "person_id": ctx["person_id"], "store_id": ctx["store_id"],
               "currency": "USD", "direction": "withdrawal"}
    r = session.post(f"{BASE}/company/capital", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    body = r.json()
    wd = next(e for e in body["entries"] if e["id"] == req_id)
    ctx["withdrawal_id"] = wd["id"]
    ctx["created"]["capital_ids"].append(wd["id"])

    def _check():
        data = _entries(session, ctx["store_id"])
        wd_rows = [r for r in data["rows"] if r["source_type"] == "OWNER_WITHDRAWAL"]
        inj_rows = [r for r in data["rows"] if r["source_type"] == "CAPITAL_INJECTION"]
        assert len(wd_rows) == 1 and len(inj_rows) == 1, data["rows"]
        assert wd_rows[0]["cash_out"] == 500.0
        return data

    for _ in range(3):
        _check()

    s = _summary(session, ctx["store_id"])
    assert s["net_cash_flow"] == 4500.0
    assert s["closing_cash"] == 4500.0

    # Concurrent GETs (via threads)
    import concurrent.futures as cf
    with cf.ThreadPoolExecutor(max_workers=5) as ex:
        results = list(ex.map(lambda _: _entries(session, ctx["store_id"]), range(5)))
    for data in results:
        wd_rows = [r for r in data["rows"] if r["source_type"] == "OWNER_WITHDRAWAL"]
        assert len(wd_rows) == 1

    # Re-POST same request_id -> still one entry
    r = session.post(f"{BASE}/company/capital", json=payload, timeout=30)
    assert r.status_code in (200, 201), r.text
    _check()


# ---------- TEST 3 : P&L unchanged ----------
def test_3_profit_loss_unaffected(session, ctx):
    params = {"store_id": ctx["store_id"], "start_date": "2026-01-01", "end_date": "2026-12-31"}
    ds = session.get(f"{BASE}/dashboard/summary", params=params, timeout=30).json()
    assert ds.get("revenue", 0) in (0, 0.0)
    assert ds.get("expenses", 0) in (0, 0.0)
    assert ds.get("net_profit", 0) in (0, 0.0)

    ps = session.get(f"{BASE}/portfolio/summary", params=params, timeout=30)
    assert ps.status_code == 200, ps.text
    pj = ps.json()
    # Totals should be zero across the board (no real orders)
    totals = pj.get("totals") or pj
    for k in ("revenue", "net_profit", "profit"):
        if k in totals:
            assert float(totals[k] or 0) == 0.0, (k, totals[k])

    # No transactions created for this store
    tx = session.get(f"{BASE}/transactions", params={"store_id": ctx["store_id"]}, timeout=30)
    assert tx.status_code == 200
    body = tx.json()
    items = body if isinstance(body, list) else (body.get("items") or body.get("transactions") or [])
    assert len(items) == 0, items


# ---------- TEST 4 : edit + delete + company /cash scope ----------
def test_4_edit_delete_and_company_cash_scope(session, ctx):
    # Edit injection to 6000
    put_payload = {"amount": "6000", "date": "2026-10-01", "note": "",
                   "person_id": ctx["person_id"], "store_id": ctx["store_id"],
                   "currency": "USD", "direction": "contribution"}
    r = session.put(f"{BASE}/company/capital/{ctx['capital_entry_id']}", json=put_payload, timeout=30)
    assert r.status_code == 200, r.text

    data = _entries(session, ctx["store_id"])
    inj = [r for r in data["rows"] if r["source_type"] == "CAPITAL_INJECTION"]
    assert len(inj) == 1 and inj[0]["cash_in"] == 6000.0, inj

    # Delete withdrawal
    r = session.delete(f"{BASE}/company/capital/{ctx['withdrawal_id']}", timeout=30)
    assert r.status_code == 200, r.text
    data = _entries(session, ctx["store_id"])
    wd = [r for r in data["rows"] if r["source_type"] == "OWNER_WITHDRAWAL"]
    assert len(wd) == 0, wd
    ctx["created"]["capital_ids"].remove(ctx["withdrawal_id"])

    # Company /cash deposit -> appears in ALL scope, NOT per-store
    cash_req = str(uuid.uuid4())
    rc = session.post(f"{BASE}/company/cash",
                      json={"request_id": cash_req, "amount": "200", "date": "2026-10-03",
                            "note": "", "currency": "USD", "direction": "in"}, timeout=30)
    assert rc.status_code in (200, 201), rc.text
    cash_id = rc.json()["id"]
    ctx["created"]["cash_ids"].append(cash_id)

    # ALL scope
    all_data = session.get(f"{BASE}/cashflow/entries", timeout=30).json()
    cash_rows = [r for r in all_data["rows"]
                 if r["source_type"] == "CASH_DEPOSIT" and r["source_id"] == cash_id]
    assert len(cash_rows) == 1, cash_rows
    assert cash_rows[0]["store_name"] == "Şirket (Genel)"
    assert cash_rows[0]["cash_in"] == 200.0

    # Per-store scope -> should NOT include company cash
    per_store = _entries(session, ctx["store_id"])
    assert not any(r["source_id"] == cash_id for r in per_store["rows"]), per_store["rows"]

    # Delete company cash
    rd = session.delete(f"{BASE}/company/cash/{cash_id}", timeout=30)
    assert rd.status_code == 200, rd.text
    all_data2 = session.get(f"{BASE}/cashflow/entries", timeout=30).json()
    assert not any(r["source_id"] == cash_id for r in all_data2["rows"])
    ctx["created"]["cash_ids"].remove(cash_id)


# ---------- TEST 5 : opening cash superseded by capital ----------
def test_5_opening_balance_superseded_by_capital(session, ctx):
    r = session.put(f"{BASE}/cashflow/opening-balance",
                    json={"store_id": ctx["store_id"], "amount_usd": 5000, "note": "manual"},
                    timeout=30)
    assert r.status_code == 200, r.text

    s = _summary(session, ctx["store_id"])
    assert s["opening_cash"] == 0.0, s
    assert s["opening_source"] == "sermaye_kasa"
    assert ctx["store_id"] in s.get("manual_opening_superseded_store_ids", [])

    lb = session.get(f"{BASE}/cashflow/opening-balances", timeout=30).json()
    row = next(b for b in lb["balances"] if b["store_id"] == ctx["store_id"])
    assert row["superseded_by_capital"] is True
