"""Focused tests for Detaylı Hareket Raporu (GET /api/reports/transactions + export).

Seeds temporary stores TEST_DTR_A (US,CA) and TEST_DTR_B (US), inserts income/expense
transactions, patches fulfillment_type + amazon_order_items directly in MongoDB
(per the review request), then verifies filters, summary math, parity with the
portfolio summary (same P&L logic), and CSV/XLSX exports.
Cleans up ALL seeded data at the end.
"""
import csv
import io
import os
import uuid
import asyncio

import pytest
import requests
from motor.motor_asyncio import AsyncIOMotorClient

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fba-finance-hub.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"
MONGO_URL = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
DB_NAME = os.environ.get("DB_NAME", "amazon_seller_suite")

ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"


# ---------- fixtures ----------
@pytest.fixture(scope="module")
def auth_headers():
    r = requests.post(f"{API}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}, timeout=20)
    assert r.status_code == 200, r.text
    body = r.json()
    return {"Authorization": f"Bearer {body['token']}"}, body["id"]


@pytest.fixture(scope="module")
def mongo_sync():
    # motor is async; use synchronous pymongo for test setup speed
    from pymongo import MongoClient
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def seeded(auth_headers, mongo_sync):
    headers, user_id = auth_headers
    created_store_ids = []
    created_tx_ids = []
    created_item_ids = []

    def post(path, payload):
        r = requests.post(f"{API}{path}", json=payload, headers={**headers, "Content-Type": "application/json"}, timeout=20)
        assert r.status_code in (200, 201), f"{path} -> {r.status_code} {r.text}"
        return r.json()

    # Stores
    store_a = post("/stores", {"name": "TEST_DTR_A", "marketplaces": ["US", "CA"], "default_currency": "USD"})
    store_b = post("/stores", {"name": "TEST_DTR_B", "marketplaces": ["US"], "default_currency": "USD"})
    created_store_ids += [store_a["id"], store_b["id"]]

    def mk_tx(store_id, marketplace, ttype, category, amount, currency, date, **extra):
        payload = {
            "store_id": store_id, "marketplace": marketplace, "type": ttype,
            "category": category, "amount": amount, "currency": currency, "date": date,
        }
        payload.update(extra)
        tx = post("/transactions", payload)
        created_tx_ids.append(tx["id"])
        return tx

    # Store A / US (FBA) — income with costs
    t1 = mk_tx(store_a["id"], "US", "income", "Order payments", 100.0, "USD", "2026-03-05",
               order_id="111-TESTDTR-0001", sku="SKU-A1", product_cost=20, shipping_cost=5, extra_cost=1,
               description="dtr test fba order")
    # Store A / CA (FBM) — income in CAD with costs
    t2 = mk_tx(store_a["id"], "CA", "income", "Order payments", 140.0, "CAD", "2026-05-10",
               order_id="222-TESTDTR-0002", sku="SKU-A2", product_cost=30, shipping_cost=6, extra_cost=2,
               description="dtr test fbm ca order")
    # Store A / US expense (Service Fees)
    t3 = mk_tx(store_a["id"], "US", "expense", "Service Fees", 15.0, "USD", "2026-04-01",
               description="dtr test service fee")
    # Store A / US refund (expense) — needs order_id
    t4 = mk_tx(store_a["id"], "US", "expense", "Refunds", 10.0, "USD", "2026-06-02",
               order_id="111-TESTDTR-0001", description="dtr test refund")
    # Store B / US income (FBA) different date
    t5 = mk_tx(store_b["id"], "US", "income", "Order payments", 80.0, "USD", "2026-07-15",
               order_id="333-TESTDTR-0003", sku="SKU-B1", product_cost=10, shipping_cost=2,
               description="dtr test store b")
    # Store A / US income outside window (date > end filter)
    t_out = mk_tx(store_a["id"], "US", "income", "Order payments", 50.0, "USD", "2026-10-11",
                  order_id="111-TESTDTR-9999", sku="SKU-OUT", description="dtr outside")

    # Patch fulfillment_type directly (per spec)
    mongo_sync.transactions.update_one({"id": t1["id"]}, {"$set": {"fulfillment_type": "FBA"}})
    mongo_sync.transactions.update_one({"id": t2["id"]}, {"$set": {"fulfillment_type": "FBM"}})
    # t3,t4 => UNKNOWN
    mongo_sync.transactions.update_one({"id": t5["id"]}, {"$set": {"fulfillment_type": "FBA"}})
    mongo_sync.transactions.update_one({"id": t_out["id"]}, {"$set": {"fulfillment_type": "FBA"}})

    # Insert amazon_order_items for t1, t2
    items = [
        {"user_id": user_id, "store_id": store_a["id"], "amazon_order_id": "111-TESTDTR-0001",
         "order_item_id": "ITEM-A1-1", "sku": "SKU-A1", "asin": "B0TESTDTRA1",
         "product_name": "Test DTR Alpha Widget", "quantity": "1", "resolved_fulfillment": "FBA"},
        {"user_id": user_id, "store_id": store_a["id"], "amazon_order_id": "222-TESTDTR-0002",
         "order_item_id": "ITEM-A2-1", "sku": "SKU-A2", "asin": "B0TESTDTRA2",
         "product_name": "Test DTR Beta Gadget", "quantity": "1", "resolved_fulfillment": "FBM"},
        {"user_id": user_id, "store_id": store_b["id"], "amazon_order_id": "333-TESTDTR-0003",
         "order_item_id": "ITEM-B1-1", "sku": "SKU-B1", "asin": "B0TESTDTRB1",
         "product_name": "Test DTR Gamma Thing", "quantity": "1", "resolved_fulfillment": "FBA"},
    ]
    for it in items:
        it["_test_id"] = str(uuid.uuid4())
        mongo_sync.amazon_order_items.insert_one(it)
        created_item_ids.append(it["_test_id"])

    data = {
        "headers": headers, "user_id": user_id,
        "store_a": store_a["id"], "store_b": store_b["id"],
        "t1": t1["id"], "t2": t2["id"], "t3": t3["id"], "t4": t4["id"], "t5": t5["id"], "t_out": t_out["id"],
    }
    yield data

    # Teardown
    for tid in created_tx_ids:
        requests.delete(f"{API}/transactions/{tid}", headers=headers, timeout=15)
    mongo_sync.amazon_order_items.delete_many({"_test_id": {"$in": created_item_ids}})
    for sid in created_store_ids:
        requests.delete(f"{API}/stores/{sid}", headers=headers, timeout=15)


def _get(headers, path, params=None):
    return requests.get(f"{API}{path}", headers=headers, params=params or {}, timeout=30)


# ---------- tests ----------
BASE_RANGE = {"start_date": "2026-01-01", "end_date": "2026-10-12"}


def test_endpoint_shape(seeded):
    r = _get(seeded["headers"], "/reports/transactions", {**BASE_RANGE, "store_id": seeded["store_a"]})
    assert r.status_code == 200, r.text
    body = r.json()
    for k in ("items", "total", "page", "page_size", "total_pages", "summary", "facets"):
        assert k in body
    for k in ("total_income", "total_expense", "total_effective_cost", "net_profit", "margin",
              "record_count", "fba_profit", "fbm_profit", "incomplete_count"):
        assert k in body["summary"]


def test_date_store_marketplace_combined(seeded):
    # store_a + marketplace US + date (narrower, excludes t_out on 2026-10-11)
    # -> should include t1,t3,t4 (NOT t2 CA, NOT t_out date, NOT t5 store B)
    r = _get(seeded["headers"], "/reports/transactions",
             {"start_date": "2026-01-01", "end_date": "2026-09-30",
              "store_id": seeded["store_a"], "marketplace": "US", "page_size": 100})
    assert r.status_code == 200
    body = r.json()
    ids = {row["id"] for row in body["items"]}
    assert seeded["t1"] in ids
    assert seeded["t3"] in ids
    assert seeded["t4"] in ids
    assert seeded["t2"] not in ids  # CA
    assert seeded["t5"] not in ids  # store B
    assert seeded["t_out"] not in ids  # out of date range


def test_fulfillment_filter(seeded):
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "fulfillment": "FBA", "page_size": 100})
    assert r.status_code == 200
    body = r.json()
    for row in body["items"]:
        assert row["fulfillment"] == "FBA"
    ids = {r["id"] for r in body["items"]}
    assert seeded["t1"] in ids
    assert seeded["t2"] not in ids  # FBM
    # Summary fba_profit should be non-null when there are only FBA rows
    assert body["summary"]["fba_profit"] is not None

    r2 = _get(seeded["headers"], "/reports/transactions",
              {**BASE_RANGE, "store_id": seeded["store_a"], "fulfillment": "FBM", "page_size": 100})
    assert r2.status_code == 200
    body2 = r2.json()
    for row in body2["items"]:
        assert row["fulfillment"] == "FBM"
    assert seeded["t2"] in {r["id"] for r in body2["items"]}


def test_direction_filter(seeded):
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "direction": "income", "page_size": 100})
    assert all(row["type"] == "income" for row in r.json()["items"])

    r2 = _get(seeded["headers"], "/reports/transactions",
              {**BASE_RANGE, "store_id": seeded["store_a"], "direction": "expense", "page_size": 100})
    assert all(row["type"] == "expense" for row in r2.json()["items"])


def test_order_id_sku_asin_q_filters(seeded):
    # order_id
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "order_id": "111-TESTDTR-0001", "page_size": 100})
    body = r.json()
    ids = {row["id"] for row in body["items"]}
    # Should include both t1 (income) and t4 (refund) with same order_id
    assert seeded["t1"] in ids and seeded["t4"] in ids
    assert seeded["t2"] not in ids

    # sku
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "sku": "SKU-A1", "page_size": 100})
    assert seeded["t1"] in {row["id"] for row in r.json()["items"]}

    # asin (from amazon_order_items)
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "asin": "B0TESTDTRA2", "page_size": 100})
    ids = {row["id"] for row in r.json()["items"]}
    assert seeded["t2"] in ids

    # q general search - case insensitive, matches product_name
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "q": "beta gadget", "page_size": 100})
    ids = {row["id"] for row in r.json()["items"]}
    assert seeded["t2"] in ids
    assert seeded["t1"] not in ids

    # q matches description
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "q": "service fee", "page_size": 100})
    assert seeded["t3"] in {row["id"] for row in r.json()["items"]}


def test_summary_math_matches_row_sums(seeded):
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "page_size": 100})
    body = r.json()
    s = body["summary"]
    if s["total_income"] is None:
        pytest.skip("incomplete FX for seeded test data")
    rows = body["items"]
    # record_count
    assert s["record_count"] == len(rows) == body["total"]
    total_income_rows = sum(r["amount_usd"] for r in rows if r["type"] == "income" and r["amount_usd"] is not None)
    total_expense_rows = sum(r["amount_usd"] for r in rows if r["type"] == "expense" and r["amount_usd"] is not None)
    total_cost_rows = sum(r["total_cost"] for r in rows if r["total_cost"] is not None)
    net_rows = sum(r["net_profit"] for r in rows if r["net_profit"] is not None)
    assert abs(s["total_income"] - total_income_rows) < 0.02
    assert abs(s["total_expense"] - total_expense_rows) < 0.02
    assert abs(s["total_effective_cost"] - total_cost_rows) < 0.05
    assert abs(s["net_profit"] - net_rows) < 0.05
    # net = income - expense - cost
    assert abs(s["net_profit"] - (s["total_income"] - s["total_expense"] - s["total_effective_cost"])) < 0.05


def test_parity_with_portfolio_summary(seeded):
    params = {**BASE_RANGE, "store_id": seeded["store_a"], "marketplace": "ALL", "currency": "ALL"}
    r_dtr = _get(seeded["headers"], "/reports/transactions", {**params, "page_size": 100})
    r_pf = _get(seeded["headers"], "/portfolio/summary", params)
    assert r_dtr.status_code == 200 and r_pf.status_code == 200, (r_dtr.text, r_pf.text)
    s = r_dtr.json()["summary"]
    pf = r_pf.json()
    if s["net_profit"] is None or pf.get("net_profit") is None:
        pytest.skip("incomplete FX")
    assert abs(s["net_profit"] - pf["net_profit"]) < 0.05, f"DTR {s['net_profit']} vs portfolio {pf['net_profit']}"


def test_pagination(seeded):
    r = _get(seeded["headers"], "/reports/transactions",
             {**BASE_RANGE, "store_id": seeded["store_a"], "page_size": 25})
    assert r.status_code == 200
    assert r.json()["page_size"] == 25
    # invalid page size
    r2 = _get(seeded["headers"], "/reports/transactions",
              {**BASE_RANGE, "store_id": seeded["store_a"], "page_size": 30})
    assert r2.status_code == 422


def test_export_csv_matches_filtered(seeded):
    params = {**BASE_RANGE, "store_id": seeded["store_a"], "direction": "income", "page_size": 100}
    # get expected IDs
    rj = _get(seeded["headers"], "/reports/transactions", params).json()
    expected_order_ids = sorted(row["order_id"] for row in rj["items"] if row["order_id"])
    # fetch CSV
    r = requests.get(f"{API}/reports/transactions/export",
                     headers=seeded["headers"], params={**params, "format": "csv"}, timeout=30)
    assert r.status_code == 200, r.text
    text = r.content.decode("utf-8-sig")
    reader = csv.reader(io.StringIO(text))
    rows = list(reader)
    assert len(rows) >= 1
    header = rows[0]
    for col in ("Order ID", "Order Item ID", "SKU", "ASIN", "Kaynak", "Fulfillment", "Döviz"):
        assert col in header, f"missing header {col}"
    data_rows = rows[1:]
    assert len(data_rows) == rj["total"] == len(rj["items"])
    idx = header.index("Order ID")
    csv_order_ids = sorted(r[idx] for r in data_rows if r[idx])
    assert csv_order_ids == expected_order_ids


def test_export_xlsx_download(seeded):
    params = {**BASE_RANGE, "store_id": seeded["store_a"], "fulfillment": "FBA", "page_size": 100}
    r = requests.get(f"{API}/reports/transactions/export",
                     headers=seeded["headers"], params={**params, "format": "xlsx"}, timeout=30)
    assert r.status_code == 200
    assert r.headers.get("content-type", "").startswith("application/vnd.openxmlformats")
    assert len(r.content) > 500  # non-empty xlsx


def test_detail_endpoint(seeded):
    r = _get(seeded["headers"], f"/reports/transactions/{seeded['t1']}/detail")
    assert r.status_code == 200
    body = r.json()
    assert body["row"]["id"] == seeded["t1"]
    assert body["record"]["id"] == seeded["t1"]
    assert isinstance(body.get("order_items"), list)
    # 404 for non-existent
    r2 = _get(seeded["headers"], "/reports/transactions/nonexistent-id/detail")
    assert r2.status_code == 404
