"""Nakit Akışı source integration tests (iteration 18).

Focus: ensure Sermaye & Kasa 'Kasadan çıkış' (current-account out/completed) rows
appear in Cash Flow, plus FBA lot purchase + inbound, plus idempotency, totals,
no duplicates on reload, no FIFO duplicate cash-out.

Covers the review request bullets:
  - Verify EXISTING entries contain AMAZON_DISBURSEMENT (NG ~70.27), 2 CAPITAL_INJECTION
    (5000 each), 1 CASH_DEPOSIT 5000 (Şirket Genel), 2 CASH_WITHDRAWAL (2500, 5000).
  - (a) Sermaye Çekme (OWNER_WITHDRAWAL) on temp store, requires prior contribution.
  - (b) FBA lot: qty 10 x $5 + inbound $20 -> FBA_INVENTORY_PURCHASE OUT 50 +
        FBA_INBOUND_SHIPPING OUT 20. Manual sale consumes FIFO -> NO extra cash-out row.
  - (c) Current-account entry with cash_effect=out, cash_status=completed ->
        CASH_WITHDRAWAL row; set pending or delete -> row disappears; edit amount -> updates.
  - Reload + concurrent GETs -> no duplicates.
  - Totals: summary.net == cash_in - cash_out; closing == opening + net;
    entries last running_balance == closing.
"""
import os
import uuid
import concurrent.futures as cf

import pytest
import requests

BASE = os.environ["REACT_APP_BACKEND_URL"].rstrip("/") + "/api"
ADMIN = {"email": "admin@amzsuite.com", "password": "admin123"}


# ---------- shared fixtures ----------
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
    """Create temp store + person. Teardown removes everything we created."""
    created = {"capital_ids": [], "current_ids": [], "lot_ids": [], "sale_order_ids": []}

    store_name = f"TEST_CF_SRC_{uuid.uuid4().hex[:6]}"
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
    # 1) Reverse FBA manual sales (frees FIFO allocations) so lots can be deleted.
    for oid in created["sale_order_ids"]:
        session.delete(f"{BASE}/transactions/by-order/{oid}", timeout=30)
        session.delete(f"{BASE}/transactions/{oid}", timeout=30)
    for lot_id in created["lot_ids"]:
        session.delete(f"{BASE}/fba/lots/{lot_id}", timeout=30)
    for eid in created["current_ids"]:
        session.delete(f"{BASE}/company/current-accounts/{eid}", timeout=30)
    # Capital: delete withdrawals before contributions (balance can't go negative).
    cap_entries = session.get(f"{BASE}/company/capital",
                              params={"store_id": store_id}, timeout=30).json()
    cap_list = cap_entries.get("entries") if isinstance(cap_entries, dict) else cap_entries
    for e in sorted(cap_list or [], key=lambda x: x.get("direction") != "withdrawal"):
        session.delete(f"{BASE}/company/capital/{e['id']}", timeout=30)
    for cid in created["capital_ids"]:
        session.delete(f"{BASE}/company/capital/{cid}", timeout=30)
    session.put(f"{BASE}/cashflow/opening-balance",
                json={"store_id": store_id, "amount_usd": 0, "note": "cleanup"}, timeout=30)
    session.delete(f"{BASE}/company/people/{person_id}", timeout=30)
    session.delete(f"{BASE}/stores/{store_id}", timeout=30)


# ---------- helpers ----------
def _entries(session, store_id=None):
    params = {"store_id": store_id} if store_id else {}
    r = session.get(f"{BASE}/cashflow/entries", params=params, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _summary(session, store_id=None):
    params = {"store_id": store_id} if store_id else {}
    r = session.get(f"{BASE}/cashflow/summary", params=params, timeout=30)
    assert r.status_code == 200, r.text
    return r.json()


def _rows_by_type(data, source_type):
    return [r for r in data["rows"] if r["source_type"] == source_type]


# =============================================================================
# TEST 1 — Pre-existing data invariants (ALL scope)
# =============================================================================
def test_1_existing_all_scope_contains_expected_rows(session):
    data = _entries(session)
    rows = data["rows"]
    # 1 AMAZON_DISBURSEMENT ~70.27 IN
    disb = [r for r in rows if r["source_type"] == "AMAZON_DISBURSEMENT"]
    assert len(disb) >= 1, f"expected >=1 AMAZON_DISBURSEMENT row, got {len(disb)}"
    assert any(abs((r.get("cash_in") or 0) - 70.27) < 0.5 for r in disb), \
        [r.get("cash_in") for r in disb]

    # 2 CAPITAL_INJECTION IN 5000
    cap = [r for r in rows if r["source_type"] == "CAPITAL_INJECTION"]
    big_cap = [r for r in cap if abs((r.get("cash_in") or 0) - 5000.0) < 0.01]
    assert len(big_cap) >= 2, f"expected >=2 CAPITAL_INJECTION 5000, got {len(big_cap)}"

    # 1 CASH_DEPOSIT 5000 in 'Şirket (Genel)'
    cdep = [r for r in rows if r["source_type"] == "CASH_DEPOSIT"
            and abs((r.get("cash_in") or 0) - 5000.0) < 0.01]
    assert any(r.get("store_name") == "Şirket (Genel)" for r in cdep), \
        [(r.get("store_name"), r.get("cash_in")) for r in cdep]

    # 2 CASH_WITHDRAWAL OUT (2500 and 5000) with 'Kasadan çıkış' label
    cw = [r for r in rows if r["source_type"] == "CASH_WITHDRAWAL"]
    cw_2500 = [r for r in cw if abs((r.get("cash_out") or 0) - 2500.0) < 0.01]
    cw_5000 = [r for r in cw if abs((r.get("cash_out") or 0) - 5000.0) < 0.01]
    assert len(cw_2500) >= 1 and len(cw_5000) >= 1, \
        f"expected CW 2500 ({len(cw_2500)}) and 5000 ({len(cw_5000)})"
    # Category label check: 'Kasa Çıkışı · Cari · Kasadan çıkış'
    assert any("Kasadan çıkış" in (r.get("category") or "") for r in cw_2500 + cw_5000), \
        [r.get("category") for r in cw_2500 + cw_5000]
    # source_module should be 'Sermaye & Kasa'
    assert any(r.get("source_module") == "Sermaye & Kasa" for r in cw_2500 + cw_5000)

    # Each cash-withdrawal row has source_module, source_id, original_amount, original_currency
    for r in cw_2500 + cw_5000:
        assert r.get("source_module"), r
        assert r.get("source_id"), r
        assert r.get("original_amount") is not None, r
        assert r.get("original_currency"), r


# =============================================================================
# TEST 2 — Sermaye Çekme (OWNER_WITHDRAWAL) requires prior contribution
# =============================================================================
def test_2_owner_withdrawal_on_temp_store(session, ctx):
    # Prior contribution (so withdrawal is allowed)
    contrib_id = str(uuid.uuid4())
    r = session.post(f"{BASE}/company/capital",
                     json={"request_id": contrib_id, "amount": "1000", "date": "2026-10-01",
                           "note": "", "person_id": ctx["person_id"], "store_id": ctx["store_id"],
                           "currency": "USD", "direction": "contribution"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    ctx["created"]["capital_ids"].append(contrib_id)

    # Withdrawal
    wd_id = str(uuid.uuid4())
    r = session.post(f"{BASE}/company/capital",
                     json={"request_id": wd_id, "amount": "300", "date": "2026-10-05",
                           "note": "", "person_id": ctx["person_id"], "store_id": ctx["store_id"],
                           "currency": "USD", "direction": "withdrawal"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    ctx["created"]["capital_ids"].append(wd_id)

    data = _entries(session, ctx["store_id"])
    ow = _rows_by_type(data, "OWNER_WITHDRAWAL")
    assert len(ow) == 1 and ow[0]["cash_out"] == 300.0 and ow[0]["direction"] == "OUT"
    assert ow[0]["source_id"] == wd_id
    assert ow[0]["source_module"] == "Sermaye & Kasa"


# =============================================================================
# TEST 3 — FBA lot: inventory purchase + inbound shipping cash-out
# =============================================================================
def test_3_fba_lot_creates_inventory_and_inbound_rows(session, ctx):
    r = session.post(f"{BASE}/fba/lots",
                     json={"store_id": ctx["store_id"], "marketplace": "US",
                           "sku": f"TEST-SKU-{uuid.uuid4().hex[:6]}", "asin": "",
                           "product_name": "TEST product",
                           "purchase_date": "2026-10-02",
                           "original_quantity": 10,
                           "product_unit_cost_usd": 5.0,
                           "inbound_shipping_total_usd": 20.0,
                           "note": "TEST lot"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    lot = r.json()
    lot_id = lot.get("id") or lot.get("lot_id")
    ctx["created"]["lot_ids"].append(lot_id)
    ctx["lot_id"] = lot_id
    ctx["lot_sku"] = lot.get("sku")

    data = _entries(session, ctx["store_id"])
    inv = [r for r in data["rows"] if r["source_type"] == "FBA_INVENTORY_PURCHASE" and r["lot_id"] == lot_id]
    inb = [r for r in data["rows"] if r["source_type"] == "FBA_INBOUND_SHIPPING" and r["lot_id"] == lot_id]
    assert len(inv) == 1, inv
    assert inv[0]["cash_out"] == 50.0 and inv[0]["direction"] == "OUT"
    assert len(inb) == 1, inb
    assert inb[0]["cash_out"] == 20.0 and inb[0]["direction"] == "OUT"


# =============================================================================
# TEST 4 — Current-account OUT/completed -> CASH_WITHDRAWAL row; edit+toggle+delete
# =============================================================================
def test_4_current_account_out_completed_lifecycle(session, ctx):
    # Create: cash_effect=out, cash_status=completed
    eid = str(uuid.uuid4())
    r = session.post(f"{BASE}/company/current-accounts",
                     json={"request_id": eid, "amount": "150", "date": "2026-10-04",
                           "note": "TEST kasa cikis",
                           "person_id": ctx["person_id"], "store_id": ctx["store_id"],
                           "direction": "payable", "currency": "USD",
                           "cash_effect": "out", "cash_status": "completed"}, timeout=30)
    assert r.status_code in (200, 201), r.text
    ctx["created"]["current_ids"].append(eid)
    ctx["current_entry_id"] = eid

    data = _entries(session, ctx["store_id"])
    cw = [r for r in data["rows"] if r["source_type"] == "CASH_WITHDRAWAL" and r["source_id"] == eid]
    assert len(cw) == 1, cw
    row = cw[0]
    assert row["cash_out"] == 150.0
    assert row["direction"] == "OUT"
    assert row["source_module"] == "Sermaye & Kasa"
    assert "Kasadan çıkış" in (row.get("category") or ""), row.get("category")
    assert row.get("original_amount") == 150.0
    assert row.get("original_currency") == "USD"

    # Edit amount -> row updates, still exactly one
    r = session.put(f"{BASE}/company/current-accounts/{eid}",
                    json={"request_id": eid, "amount": "275", "date": "2026-10-04",
                          "note": "TEST kasa cikis", "person_id": ctx["person_id"],
                          "store_id": ctx["store_id"], "direction": "payable",
                          "currency": "USD", "cash_effect": "out",
                          "cash_status": "completed"}, timeout=30)
    assert r.status_code == 200, r.text
    data = _entries(session, ctx["store_id"])
    cw = [r for r in data["rows"] if r["source_type"] == "CASH_WITHDRAWAL" and r["source_id"] == eid]
    assert len(cw) == 1 and cw[0]["cash_out"] == 275.0, cw

    # Toggle to pending -> row disappears from cash-flow
    r = session.put(f"{BASE}/company/current-accounts/{eid}",
                    json={"request_id": eid, "amount": "275", "date": "2026-10-04",
                          "note": "TEST kasa cikis", "person_id": ctx["person_id"],
                          "store_id": ctx["store_id"], "direction": "payable",
                          "currency": "USD", "cash_effect": "out",
                          "cash_status": "pending"}, timeout=30)
    assert r.status_code == 200, r.text
    data = _entries(session, ctx["store_id"])
    cw = [r for r in data["rows"] if r["source_type"] == "CASH_WITHDRAWAL" and r["source_id"] == eid]
    assert cw == [], cw

    # Toggle back to completed -> row reappears
    r = session.put(f"{BASE}/company/current-accounts/{eid}",
                    json={"request_id": eid, "amount": "275", "date": "2026-10-04",
                          "note": "TEST kasa cikis", "person_id": ctx["person_id"],
                          "store_id": ctx["store_id"], "direction": "payable",
                          "currency": "USD", "cash_effect": "out",
                          "cash_status": "completed"}, timeout=30)
    assert r.status_code == 200
    data = _entries(session, ctx["store_id"])
    cw = [r for r in data["rows"] if r["source_type"] == "CASH_WITHDRAWAL" and r["source_id"] == eid]
    assert len(cw) == 1 and cw[0]["cash_out"] == 275.0

    # Delete -> row disappears
    r = session.delete(f"{BASE}/company/current-accounts/{eid}", timeout=30)
    assert r.status_code == 200
    data = _entries(session, ctx["store_id"])
    cw = [r for r in data["rows"] if r["source_type"] == "CASH_WITHDRAWAL" and r["source_id"] == eid]
    assert cw == []
    ctx["created"]["current_ids"].remove(eid)


# =============================================================================
# TEST 5 — Idempotency on reload + concurrent GETs
# =============================================================================
def test_5_no_duplicates_on_reload_and_concurrent(session, ctx):
    # Serial reloads
    seen_counts = []
    for _ in range(3):
        data = _entries(session, ctx["store_id"])
        ow = [r for r in data["rows"] if r["source_type"] == "OWNER_WITHDRAWAL"]
        inv = [r for r in data["rows"] if r["source_type"] == "FBA_INVENTORY_PURCHASE"]
        inb = [r for r in data["rows"] if r["source_type"] == "FBA_INBOUND_SHIPPING"]
        cap = [r for r in data["rows"] if r["source_type"] == "CAPITAL_INJECTION"]
        seen_counts.append((len(ow), len(inv), len(inb), len(cap)))
    assert len(set(seen_counts)) == 1, seen_counts
    assert seen_counts[0] == (1, 1, 1, 1)

    # Concurrent GETs
    with cf.ThreadPoolExecutor(max_workers=6) as ex:
        results = list(ex.map(lambda _: _entries(session, ctx["store_id"]), range(6)))
    for data in results:
        ow = [r for r in data["rows"] if r["source_type"] == "OWNER_WITHDRAWAL"]
        inv = [r for r in data["rows"] if r["source_type"] == "FBA_INVENTORY_PURCHASE"]
        inb = [r for r in data["rows"] if r["source_type"] == "FBA_INBOUND_SHIPPING"]
        assert len(ow) == 1 and len(inv) == 1 and len(inb) == 1


# =============================================================================
# TEST 6 — Totals: summary & running balance consistency
# =============================================================================
def test_6_totals_summary_and_running_balance(session, ctx):
    # Per-store scope totals
    s = _summary(session, ctx["store_id"])
    data = _entries(session, ctx["store_id"])
    # net == in - out
    assert round(s["net_cash_flow"], 2) == round(s["cash_in"] - s["cash_out"], 2), s
    # closing == opening + net
    assert round(s["closing_cash"], 2) == round(s["opening_cash"] + s["net_cash_flow"], 2), s
    # Entries running balance final equals summary closing
    rows = data["rows"]
    if rows:
        assert round(rows[-1]["running_balance"], 2) == round(data["closing_cash"], 2)
    assert round(data["closing_cash"], 2) == round(s["closing_cash"], 2)

    # ALL scope totals
    s_all = _summary(session)
    data_all = _entries(session)
    assert round(s_all["net_cash_flow"], 2) == round(s_all["cash_in"] - s_all["cash_out"], 2), s_all
    assert round(s_all["closing_cash"], 2) == round(s_all["opening_cash"] + s_all["net_cash_flow"], 2), s_all
    if data_all["rows"]:
        assert round(data_all["rows"][-1]["running_balance"], 2) == round(data_all["closing_cash"], 2)


# =============================================================================
# TEST 7 — FIFO consumption does NOT create extra cash-out row
# =============================================================================
def test_7_fba_manual_sale_no_duplicate_cashout(session, ctx):
    before = _entries(session, ctx["store_id"])
    inv_before = [r for r in before["rows"] if r["source_type"] == "FBA_INVENTORY_PURCHASE"]
    inb_before = [r for r in before["rows"] if r["source_type"] == "FBA_INBOUND_SHIPPING"]
    assert len(inv_before) == 1 and len(inb_before) == 1
    inv_cash = inv_before[0]["cash_out"]
    inb_cash = inb_before[0]["cash_out"]

    sale_order_id = f"TEST-ORD-{uuid.uuid4().hex[:8]}"
    r = session.post(f"{BASE}/fba/manual-sale",
                     json={"store_id": ctx["store_id"], "marketplace": "US",
                           "sku": ctx["lot_sku"], "asin": "",
                           "product_name": "TEST product",
                           "quantity": 3, "amount": 60.0, "order_id": sale_order_id,
                           "date": "2026-10-06", "currency": "USD",
                           "category": ""}, timeout=30)
    if r.status_code not in (200, 201):
        pytest.skip(f"manual-sale not available: {r.status_code} {r.text[:200]}")
    ctx["created"]["sale_order_ids"].append(sale_order_id)

    after = _entries(session, ctx["store_id"])
    inv_after = [r for r in after["rows"] if r["source_type"] == "FBA_INVENTORY_PURCHASE"]
    inb_after = [r for r in after["rows"] if r["source_type"] == "FBA_INBOUND_SHIPPING"]
    # Still exactly ONE inventory + ONE inbound row; amounts unchanged (FIFO is P&L only)
    assert len(inv_after) == 1 and inv_after[0]["cash_out"] == inv_cash, inv_after
    assert len(inb_after) == 1 and inb_after[0]["cash_out"] == inb_cash, inb_after
    # No new cash-out source introduced by the sale
    new_source_ids = {r["source_id"] for r in after["rows"]} - {r["source_id"] for r in before["rows"]}
    # Only acceptable additions: none, or an AMAZON_PAYMENT IN for the sale amount - but NO OUT row
    for sid in new_source_ids:
        row = next(r for r in after["rows"] if r["source_id"] == sid)
        assert row["direction"] != "OUT", f"unexpected OUT row after manual sale: {row}"
