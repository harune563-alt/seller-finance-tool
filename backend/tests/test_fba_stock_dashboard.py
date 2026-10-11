"""Focused tests: lot CSV import, low stock, store-scoped dashboard insights."""
import uuid

import pytest
import requests

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = f"{BASE}/api"
S = requests.Session()
S.headers["Origin"] = BASE
ST = {}
CSV = ("SKU,ASIN,Product Name,Purchase Date,Original Quantity,Product Unit Cost USD,Inbound Shipping Total USD,Lot Reference\n"
       "ZOG-1,B0ZOG,ZoGuard,2026-01-02,100,8,150,PO-1\n")


def lot_import(store, body, commit=True):
    r = S.post(f"{API}/fba/lots/import", params={"store_id": store, "commit": str(commit).lower()},
               files={"file": ("lots.csv", body.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def lots(store):
    return S.get(f"{API}/fba/lots", params={"store_id": store}).json()


@pytest.fixture(scope="module", autouse=True)
def setup():
    r = S.post(f"{API}/auth/register", json={"email": f"st_{uuid.uuid4().hex[:8]}@test.com", "password": "Test12345!", "name": "ST"})
    S.headers["Authorization"] = f"Bearer {r.json().get('token') or r.json().get('access_token')}"
    for k in ("a", "b"):
        ST[k] = S.post(f"{API}/stores", json={"name": f"Store {k}", "marketplaces": ["US"], "default_currency": "USD"}).json()["id"]
    yield


def test_1_import_lot_landed_cost():
    prev = lot_import(ST["a"], CSV, commit=False)
    assert prev["counts"]["new_lot"] == 1 and lots(ST["a"]) == []
    lot_import(ST["a"], CSV)
    [lot] = lots(ST["a"])
    assert lot["inbound_shipping_unit_usd"] == 1.5 and lot["landed_unit_cost_usd"] == 9.5
    assert lot["remaining_quantity"] == 100 and lot["remaining_value_usd"] == 950


def test_2_reimport_no_duplicate_and_update():
    res = lot_import(ST["a"], CSV)
    assert res["counts"] == {"new_lot": 0, "existing_unchanged": 1, "updated": 0, "invalid": 0}
    assert len(lots(ST["a"])) == 1
    res = lot_import(ST["a"], CSV.replace(",150,", ",200,"))
    assert res["counts"]["updated"] == 1 and lots(ST["a"])[0]["landed_unit_cost_usd"] == 10
    bad = lot_import(ST["a"], CSV + "X,,Bad,notadate,-1,a,b,\n", commit=False)
    assert bad["counts"]["invalid"] == 1


def test_3_low_stock_badge():
    lot_id = lots(ST["a"])[0]["id"]
    assert S.put(f"{API}/fba/thresholds", json={"store_id": ST["a"], "sku": "ZOG-1", "threshold": 20}).status_code == 200
    status = lambda: S.get(f"{API}/fba/stock-status", params={"store_id": ST["a"]}).json()[0]["stock_status"]
    assert status() == "HEALTHY"
    S.post(f"{API}/fba/lots/{lot_id}/adjust", json={"adjustment_type": "correct_remaining", "value": 20})
    assert status() == "LOW_STOCK"
    S.post(f"{API}/fba/lots/{lot_id}/adjust", json={"adjustment_type": "correct_remaining", "value": 0})
    assert status() == "OUT_OF_STOCK"
    S.post(f"{API}/fba/lots/{lot_id}/adjust", json={"adjustment_type": "increase_quantity", "value": 50})


def _tx(store, amount):
    r = S.post(f"{API}/transactions", json={"store_id": store, "marketplace": "US", "type": "income", "category": "Order payments",
                                            "amount": amount, "currency": "USD", "date": "2026-02-01", "order_id": f"1-{uuid.uuid4().hex[:8]}"})
    assert r.status_code == 200, r.text


def test_4_and_5_dashboard_store_scope():
    _tx(ST["a"], 100)
    _tx(ST["b"], 40)
    lot_import(ST["b"], CSV.replace("ZOG-1", "B-SKU").replace(",100,8,", ",10,5,"))  # 10 x 5 + 150 = 200
    get = lambda s: S.get(f"{API}/dashboard/insights", params={"store_id": s}).json()
    summ = lambda s: S.get(f"{API}/dashboard/summary", params={} if s == "ALL" else {"store_id": s}).json()
    assert summ("ALL")["revenue"] == 140 and summ(ST["a"])["revenue"] == 100 and summ(ST["b"])["revenue"] == 40
    a, b, all_ = get(ST["a"]), get(ST["b"]), get("ALL")
    assert a["fba_inventory_value_usd"] == 466.67 and b["fba_inventory_value_usd"] == 200
    assert all_["fba_inventory_value_usd"] == 666.67
    assert a["order_count"] == 1 and b["order_count"] == 1 and all_["order_count"] == 2
    assert all_["unclassified"]["revenue"] == 140
