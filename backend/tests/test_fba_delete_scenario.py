"""Single-scenario regression for FBA sale deletion -> FIFO reversal and
lot delete guard. Creates its own TEST_FBA_DEL_<rand> store and cleans up."""
import os
import uuid
from datetime import date

import pytest
import requests

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
ORIGIN = "https://fba-finance-hub.preview.emergentagent.com"
ADMIN = {"email": "admin@amzsuite.com", "password": "admin123"}
TODAY = date.today().isoformat()


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json", "Origin": ORIGIN})
    r = s.post(f"{BASE_URL}/api/auth/login", json=ADMIN, timeout=30)
    assert r.status_code == 200, f"login failed {r.status_code} {r.text}"
    token = r.json()["access_token"] if "access_token" in r.json() else r.json().get("token")
    assert token, f"no token in {r.json()}"
    s.headers["Authorization"] = f"Bearer {token}"
    return s


@pytest.fixture(scope="module")
def store(session):
    name = f"TEST_FBA_DEL_{uuid.uuid4().hex[:6]}"
    r = session.post(f"{BASE_URL}/api/stores",
                     json={"name": name, "marketplaces": ["US"]}, timeout=30)
    assert r.status_code == 200, f"create store {r.status_code} {r.text}"
    sid = r.json()["id"]
    yield {"id": sid, "name": name}
    # teardown
    session.delete(f"{BASE_URL}/api/stores/{sid}", timeout=30)


def _create_lot(session, store_id, sku="TEST-SKU-1"):
    r = session.post(f"{BASE_URL}/api/fba/lots", json={
        "store_id": store_id, "sku": sku, "asin": "B0TESTDEL1",
        "original_quantity": 1, "product_unit_cost_usd": 10,
        "inbound_shipping_total_usd": 0, "purchase_date": TODAY,
    }, timeout=30)
    assert r.status_code in (200, 201), f"lot create {r.status_code} {r.text}"
    return r.json()


def _get_lot(session, store_id, lot_id):
    r = session.get(f"{BASE_URL}/api/fba/lots", params={"store_id": store_id}, timeout=30)
    assert r.status_code == 200, r.text
    lots = r.json().get("lots") if isinstance(r.json(), dict) else r.json()
    return next((l for l in lots if l["id"] == lot_id), None)


def _manual_sale(session, store_id, sku="TEST-SKU-1", qty=1, amount=30):
    r = session.post(f"{BASE_URL}/api/fba/manual-sale", json={
        "store_id": store_id, "marketplace": "US", "sku": sku,
        "quantity": qty, "amount": amount, "date": TODAY,
    }, timeout=30)
    assert r.status_code in (200, 201), f"manual-sale {r.status_code} {r.text}"
    return r.json()


# ---------- Tests ----------
class TestFbaDeleteScenario:
    def test_01_full_cycle_single_delete(self, session, store):
        sid = store["id"]
        lot = _create_lot(session, sid)
        lot_id = lot["id"]

        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 1
        assert got.get("consumed_quantity", 0) == 0
        assert got["lot_status"] == "OPEN"

        sale = _manual_sale(session, sid)
        tx_id = sale["transaction_id"]
        order_id = sale["order_id"]
        assert tx_id and order_id

        # After sale: lot depleted, sku-lookup insufficient, orders shows it
        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 0
        assert got["consumed_quantity"] == 1
        assert got["lot_status"] == "DEPLETED"

        r = session.get(f"{BASE_URL}/api/fba/sku-lookup", params={
            "store_id": sid, "sku": "TEST-SKU-1", "quantity": 1}, timeout=30)
        assert r.status_code == 200, r.text
        assert r.json()["fifo_preview"]["sufficient"] is False

        r = session.get(f"{BASE_URL}/api/fba/orders", params={"store_id": sid}, timeout=30)
        assert r.status_code == 200
        orders_data = r.json()
        order_ids = [o["order_id"] for o in orders_data["orders"]]
        assert order_id in order_ids
        asin_report = orders_data.get("asin_report", [])
        assert any(a.get("asin") == "B0TESTDEL1" for a in asin_report), f"ASIN missing in report {asin_report}"

        r = session.get(f"{BASE_URL}/api/fba/inventory", params={"store_id": sid}, timeout=30)
        assert r.status_code == 200
        assert r.json()["totals"]["remaining_units"] == 0

        # LOT GUARD: delete lot blocked
        r = session.delete(f"{BASE_URL}/api/fba/lots/{lot_id}", timeout=30)
        assert r.status_code == 409, f"expected 409, got {r.status_code} {r.text}"
        assert "aktif FBA sat" in r.text
        # ensure lot still exists
        assert _get_lot(session, sid, lot_id) is not None

        # Delete the sale transaction
        r = session.delete(f"{BASE_URL}/api/transactions/{tx_id}", timeout=30)
        assert r.status_code == 200, f"delete tx {r.status_code} {r.text}"
        body = r.json()
        assert body.get("reversed_allocations", 0) >= 1, f"no reversal {body}"

        # Verify: lot back, allocations reversed, orders empty
        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 1, got
        assert got["consumed_quantity"] == 0, got
        assert got["lot_status"] == "OPEN", got

        r = session.get(f"{BASE_URL}/api/fba/orders", params={"store_id": sid}, timeout=30)
        assert order_id not in [o["order_id"] for o in r.json()["orders"]]

        r = session.get(f"{BASE_URL}/api/fba/inventory", params={"store_id": sid}, timeout=30)
        assert r.json()["totals"]["remaining_units"] == 1

        r = session.get(f"{BASE_URL}/api/fba/sku-lookup", params={
            "store_id": sid, "sku": "TEST-SKU-1", "quantity": 1}, timeout=30)
        assert r.json()["fifo_preview"]["sufficient"] is True

        # allocation doc status = reversed via lot history
        r = session.get(f"{BASE_URL}/api/fba/lots/{lot_id}/history", timeout=30)
        assert r.status_code == 200, r.text
        allocs = r.json().get("allocations", [])
        order_allocs = [a for a in allocs if a.get("amazon_order_id") == order_id]
        assert order_allocs, "allocation record not found in history"
        assert all(a["status"] == "reversed" for a in order_allocs), order_allocs

        # Dashboard summary should NOT include deleted 30 USD income
        r = session.get(f"{BASE_URL}/api/dashboard/summary", params={"store_id": sid}, timeout=30)
        assert r.status_code == 200
        summary = r.json()
        # income_usd (or similar) should not include 30
        income = summary.get("income_usd") or summary.get("income") or 0
        assert float(income) < 30, f"deleted income still counted: {summary}"

        # LOT GUARD after reversal: delete lot succeeds
        r = session.delete(f"{BASE_URL}/api/fba/lots/{lot_id}", timeout=30)
        assert r.status_code == 200, f"lot delete after reversal {r.status_code} {r.text}"
        assert _get_lot(session, sid, lot_id) is None

    def test_02_bulk_delete_reversal(self, session, store):
        sid = store["id"]
        lot = _create_lot(session, sid, sku="TEST-SKU-BULK")
        lot_id = lot["id"]
        sale = _manual_sale(session, sid, sku="TEST-SKU-BULK")
        tx_id = sale["transaction_id"]

        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 0

        r = session.post(f"{BASE_URL}/api/transactions/bulk-delete",
                         json={"ids": [tx_id]}, timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("deleted", 0) >= 1
        assert body.get("reversed_allocations", 0) >= 1, body

        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 1, got
        assert got["lot_status"] == "OPEN"
        # cleanup
        session.delete(f"{BASE_URL}/api/fba/lots/{lot_id}", timeout=30)

    def test_03_partial_order_reverses_when_no_fba_tx_remains(self, session, store):
        """NEW RULE (iteration 14): reversal fires as soon as NO remaining tx with
        fulfillment_type='FBA' exists for the order — even if a non-FBA expense
        still shares the order_id. Then the non-FBA expense delete is a no-op
        with reversed_allocations=0 and must not error."""
        sid = store["id"]
        lot = _create_lot(session, sid, sku="TEST-SKU-PART")
        lot_id = lot["id"]

        sale = _manual_sale(session, sid, sku="TEST-SKU-PART")
        income_tx_id = sale["transaction_id"]
        order_id = sale["order_id"]

        # Add non-FBA expense sharing the same order_id (TransactionIn has no
        # fulfillment_type field, so this row is NOT FBA-fulfilled)
        r = session.post(f"{BASE_URL}/api/transactions", json={
            "store_id": sid, "marketplace": "US", "type": "expense",
            "category": "Service Fees", "amount": 1, "currency": "USD",
            "date": TODAY, "order_id": order_id,
        }, timeout=30)
        assert r.status_code in (200, 201), f"create expense {r.status_code} {r.text}"
        expense_tx_id = r.json()["id"]

        # Delete the income (sole FBA-fulfillment tx). Under the new rule the
        # order has no remaining FBA tx -> allocations should reverse now.
        r = session.delete(f"{BASE_URL}/api/transactions/{income_tx_id}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("reversed_allocations", 0) >= 1, (
            f"expected reversal on last FBA tx delete: {body}")

        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 1, f"lot should be restored now: {got}"
        assert got["consumed_quantity"] == 0, got
        assert got["lot_status"] == "OPEN", got

        r = session.get(f"{BASE_URL}/api/fba/lots/{lot_id}/history", timeout=30)
        order_allocs = [a for a in r.json()["allocations"] if a.get("amazon_order_id") == order_id]
        assert order_allocs and all(a["status"] == "reversed" for a in order_allocs), order_allocs

        # Delete the leftover non-FBA expense: no allocations remain for the
        # order, so this must be a clean no-op (reversed_allocations == 0).
        r = session.delete(f"{BASE_URL}/api/transactions/{expense_tx_id}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("reversed_allocations", 0) == 0, (
            f"second delete should be a no-op: {body}")

        got = _get_lot(session, sid, lot_id)
        assert got["remaining_quantity"] == 1, got
        assert got["lot_status"] == "OPEN", got

        # cleanup
        session.delete(f"{BASE_URL}/api/fba/lots/{lot_id}", timeout=30)

    def test_04_non_fba_order_delete_is_noop(self, session, store):
        """Sanity: a plain manual income with an order_id but no FBA
        fulfillment / allocations must delete cleanly with reversed_allocations=0."""
        sid = store["id"]
        order_id = f"TEST-NONFBA-{uuid.uuid4().hex[:8].upper()}"
        r = session.post(f"{BASE_URL}/api/transactions", json={
            "store_id": sid, "marketplace": "US", "type": "expense",
            "category": "Service Fees", "amount": 5, "currency": "USD",
            "date": TODAY, "order_id": order_id,
        }, timeout=30)
        assert r.status_code in (200, 201), f"create {r.status_code} {r.text}"
        tx_id = r.json()["id"]

        r = session.delete(f"{BASE_URL}/api/transactions/{tx_id}", timeout=30)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body.get("reversed_allocations", 0) == 0, body
        assert body.get("ok") is True
