"""FBM SellerFlash cost -> Nakit Akışı integration tests (iteration 19).

Covers:
 - Pre-existing NG store transaction yields exactly one FBM_PRODUCT_COST OUT 50,
   FBM_SHIPPING_COST OUT 100, EXTRA_COST OUT 200 (USD, no conversion).
 - SellerFlash CSV import on a temp store adds the FBM cost rows, EXTRA_COST
   stays independent, summary cash_out matches.
 - Re-import stays idempotent (no duplicate rows).
 - Partial completion: product-only -> only FBM_PRODUCT_COST; later shipping ->
   FBM_SHIPPING_COST added, product row unchanged, no dupes.
"""
import io
import uuid

import pytest
import requests

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0].strip()
API = f"{BASE}/api"

ADMIN = {"email": "admin@amzsuite.com", "password": "admin123"}

NG_STORE = "74b2c875-7556-40b2-8539-28d55d3b8661"
NG_TX = "649f49d0-9841-4d79-b6a5-e527f9b33f80"


@pytest.fixture(scope="module")
def admin_session():
    s = requests.Session()
    s.headers["Origin"] = BASE
    r = s.post(f"{API}/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, r.text
    tok = r.json().get("token") or r.json().get("access_token")
    s.headers["Authorization"] = f"Bearer {tok}"
    return s


def _entries(s, store_id):
    r = s.get(f"{API}/cashflow/entries", params={"store_id": store_id}, timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _rows_for(entries, source_type):
    return [r for r in entries.get("rows", []) if r.get("source_type") == source_type]


def _amt(row):
    return float(row.get("cash_out") if row.get("direction") == "OUT" else row.get("cash_in") or 0)


# -------------------- Test 1: pre-existing NG data --------------------

def test_1_existing_ng_order_fbm_rows(admin_session):
    s = admin_session
    # sanity: the transaction we rely on must exist unchanged
    r = s.get(f"{API}/transactions", params={"store_id": NG_STORE, "limit": 2000}, timeout=60)
    assert r.status_code == 200
    tx = next((t for t in r.json() if t["id"] == NG_TX), None)
    assert tx is not None, "pre-existing NG transaction missing"
    assert tx.get("cost_currency") == "USD"
    assert float(tx.get("product_cost") or 0) == 50
    assert float(tx.get("shipping_cost") or 0) == 100
    assert float(tx.get("extra_cost") or 0) == 200

    e = _entries(s, NG_STORE)
    # NG order id may be stored on tx but is excluded from fbm row order_id if missing
    oid = tx.get("order_id") or ""
    prod = _rows_for(e, "FBM_PRODUCT_COST")
    ship = _rows_for(e, "FBM_SHIPPING_COST")
    extra = _rows_for(e, "EXTRA_COST")
    # Filter to this transaction via source_id suffix (fbm key = order_id or tx_id)
    def _for_tx(rows):
        return [r for r in rows if r.get("source_id", "").endswith(NG_TX) or (oid and r.get("order_id") == oid)]
    prod_tx = _for_tx(prod)
    ship_tx = _for_tx(ship)
    extra_tx = [r for r in extra if r.get("source_id", "").endswith(NG_TX)]

    assert len(prod_tx) == 1, f"expected 1 FBM_PRODUCT_COST row, got {len(prod_tx)}"
    assert len(ship_tx) == 1
    assert len(extra_tx) == 1

    assert _amt(prod_tx[0]) == 50.0
    assert _amt(ship_tx[0]) == 100.0
    assert _amt(extra_tx[0]) == 200.0
    for row in (prod_tx[0], ship_tx[0], extra_tx[0]):
        assert row["direction"] == "OUT"
        assert (row.get("original_currency") or "USD") == "USD"


# -------------------- Shared state for subsequent tests --------------------

STATE: dict = {}


@pytest.fixture(scope="module")
def temp_store(admin_session):
    s = admin_session
    r = s.post(f"{API}/stores", json={"name": f"TEST_FBM_CF_{uuid.uuid4().hex[:6]}",
                                       "marketplaces": ["US"], "default_currency": "USD"}, timeout=30)
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    STATE["store"] = sid
    STATE["txids"] = []
    yield sid
    # teardown
    # Delete sellerflash_costs for this store
    try:
        unmatched = s.get(f"{API}/sellerflash/unmatched", params={"store_id": sid}, timeout=30).json()
    except Exception:
        unmatched = {"items": []}
    # best-effort: no public delete for sellerflash_costs — rely on cascade via store delete
    for tx_id in STATE.get("txids", []):
        s.delete(f"{API}/transactions/{tx_id}", timeout=30)
    s.delete(f"{API}/stores/{sid}", timeout=30)


def _sf_csv(rows):
    body = "Seller Order Id,Product Cost,Initial Shipment Cost,Marketplace\n"
    for oid, pc, sc in rows:
        body += f"{oid},{'' if pc is None else pc},{'' if sc is None else sc},Amazon.com\n"
    return body.encode()


def _import_sf(s, store_id, rows, commit=True):
    r = s.post(f"{API}/sellerflash/import",
               params={"store_id": store_id, "commit": "true" if commit else "false"},
               files={"file": ("sf.csv", _sf_csv(rows), "text/csv")},
               timeout=60)
    assert r.status_code == 200, r.text
    return r.json()


def _mk_income(s, store_id, order_id, currency="USD", extra_cost=0):
    payload = {"store_id": store_id, "marketplace": "US", "type": "income",
               "category": "Order payments", "amount": 100, "currency": currency,
               "date": "2026-02-02", "order_id": order_id,
               "fulfillment_type": "FBM", "extra_cost": extra_cost}
    r = s.post(f"{API}/transactions", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    tid = r.json()["id"]
    STATE["txids"].append(tid)
    return tid


# -------------------- Test 2: SellerFlash drives FBM cash out --------------------

def test_2_sellerflash_fbm_cashflow(admin_session, temp_store):
    s = admin_session
    sid = temp_store
    oid = f"111-{uuid.uuid4().hex[:7]}-{uuid.uuid4().hex[:7]}"
    STATE["oid1"] = oid
    _mk_income(s, sid, oid, extra_cost=3)
    _import_sf(s, sid, [(oid, 20, 8)], commit=True)

    e = _entries(s, sid)
    prod = [r for r in _rows_for(e, "FBM_PRODUCT_COST") if r.get("order_id") == oid]
    ship = [r for r in _rows_for(e, "FBM_SHIPPING_COST") if r.get("order_id") == oid]
    extra = _rows_for(e, "EXTRA_COST")
    assert len(prod) == 1 and _amt(prod[0]) == 20.0
    assert len(ship) == 1 and _amt(ship[0]) == 8.0
    assert len(extra) == 1 and _amt(extra[0]) == 3.0

    summary = s.get(f"{API}/cashflow/summary", params={"store_id": sid}, timeout=30).json()
    assert float(summary["cash_out"]) == 31.0, summary


# -------------------- Test 3: Re-import idempotent --------------------

def test_3_reimport_idempotent(admin_session, temp_store):
    s = admin_session
    sid = temp_store
    oid = STATE["oid1"]
    for _ in range(3):
        _import_sf(s, sid, [(oid, 20, 8)], commit=True)
        e = _entries(s, sid)
        prod = [r for r in _rows_for(e, "FBM_PRODUCT_COST") if r.get("order_id") == oid]
        ship = [r for r in _rows_for(e, "FBM_SHIPPING_COST") if r.get("order_id") == oid]
        assert len(prod) == 1 and len(ship) == 1
    summary = s.get(f"{API}/cashflow/summary", params={"store_id": sid}, timeout=30).json()
    assert float(summary["cash_out"]) == 31.0


# -------------------- Test 4: partial completion --------------------

def test_4_partial_completion(admin_session, temp_store):
    s = admin_session
    sid = temp_store
    oid = f"111-{uuid.uuid4().hex[:7]}-{uuid.uuid4().hex[:7]}"
    STATE["oid2"] = oid
    _mk_income(s, sid, oid, extra_cost=0)

    # product only
    _import_sf(s, sid, [(oid, 15, None)], commit=True)
    e = _entries(s, sid)
    prod = [r for r in _rows_for(e, "FBM_PRODUCT_COST") if r.get("order_id") == oid]
    ship = [r for r in _rows_for(e, "FBM_SHIPPING_COST") if r.get("order_id") == oid]
    assert len(prod) == 1 and _amt(prod[0]) == 15.0
    assert len(ship) == 0, "shipping should not emit a row when blank"

    # add shipping, product unchanged
    _import_sf(s, sid, [(oid, None, 4)], commit=True)
    e = _entries(s, sid)
    prod = [r for r in _rows_for(e, "FBM_PRODUCT_COST") if r.get("order_id") == oid]
    ship = [r for r in _rows_for(e, "FBM_SHIPPING_COST") if r.get("order_id") == oid]
    assert len(prod) == 1 and _amt(prod[0]) == 15.0
    assert len(ship) == 1 and _amt(ship[0]) == 4.0
