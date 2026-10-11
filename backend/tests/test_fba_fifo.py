"""Focused FBA lots / FIFO / report tests (isolated test user + store)."""
import os
import uuid

import pytest
import requests

BASE = os.environ.get("REACT_APP_BACKEND_URL") or open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = f"{BASE}/api"
S = requests.Session()
S.headers["Origin"] = BASE
ST = {}
HEADER = ("amazon-order-id\tpurchase-date\torder-status\tfulfillment-channel\tproduct-name\tsku\tasin\t"
          "item-status\tquantity\tcurrency\titem-price\torder-item-id\n")


def tsv(rows):
    return HEADER + "".join(f"{o}\t{d}T10:00:00+00:00\tShipped\tAmazon\tProd {s}\t{s}\tASIN-{s}\tShipped\t{q}\tUSD\t10\t{o}-1\n"
                            for o, d, s, q in rows)


def import_orders(rows):
    r = S.post(f"{API}/amazon-orders/import?commit=true",
               files={"file": ("orders.txt", tsv(rows).encode(), "text/plain")})
    assert r.status_code == 200, r.text


def income(order_id, amount, day="2026-01-05"):
    r = S.post(f"{API}/transactions", json={"store_id": ST["store"], "marketplace": "US", "type": "income",
                                            "category": "Order payments", "amount": amount, "currency": "USD",
                                            "date": day, "order_id": order_id})
    assert r.status_code == 200, r.text
    return r.json()


def lot(sku, qty, unit, inbound, day):
    r = S.post(f"{API}/fba/lots", json={"store_id": ST["store"], "marketplace": "US", "sku": sku,
                                        "asin": f"ASIN-{sku}", "product_name": f"Prod {sku}", "purchase_date": day,
                                        "original_quantity": qty, "product_unit_cost_usd": unit,
                                        "inbound_shipping_total_usd": inbound})
    assert r.status_code == 200, r.text
    return r.json()


def orders():
    r = S.get(f"{API}/fba/orders", params={"store_id": ST["store"]})
    assert r.status_code == 200, r.text
    return r.json()


def order(oid):
    return next(o for o in orders()["orders"] if o["order_id"] == oid)


def lots():
    return {l["id"]: l for l in S.get(f"{API}/fba/lots", params={"store_id": ST["store"]}).json()}


def tx_count():
    return len(S.get(f"{API}/transactions", params={"store_id": ST["store"], "limit": 1000}).json())


@pytest.fixture(scope="module", autouse=True)
def setup():
    email = f"fba_{uuid.uuid4().hex[:8]}@test.com"
    r = S.post(f"{API}/auth/register", json={"email": email, "password": "Test12345!", "name": "FBA"})
    assert r.status_code == 200, r.text
    S.headers["Authorization"] = f"Bearer {r.json().get('token') or r.json().get('access_token')}"
    ST["store"] = S.post(f"{API}/stores", json={"name": "FBA Test", "marketplaces": ["US"],
                                                "default_currency": "USD"}).json()["id"]
    ST["p"] = uuid.uuid4().hex[:6]
    yield


def oid(n):
    return f"111-{ST['p']}-{n:07d}"


def test_1_lot_costs():
    l = lot("SKU-A", 100, 8, 150, "2025-12-01")
    ST["lotA"] = l["id"]
    assert l["inbound_shipping_unit_usd"] == 1.5 and l["landed_unit_cost_usd"] == 9.5
    assert l["remaining_value_usd"] == 950 and l["lot_status"] == "OPEN"


def test_2_order_consumes_lot_and_6_same_transaction():
    tx = income(oid(1), 50)
    before = tx_count()
    import_orders([(oid(1), "2026-01-05", "SKU-A", 2)])
    o = order(oid(1))
    assert o["total_cost_usd"] == 19 and o["cost_status"] == "costed" and o["allocated_units"] == 2
    assert o["net_profit_usd"] == 31 and o["margin_percent"] == 62
    assert lots()[ST["lotA"]]["remaining_quantity"] == 98
    assert tx_count() == before
    txs = [t for t in S.get(f"{API}/transactions", params={"store_id": ST["store"]}).json() if t["order_id"] == oid(1)]
    assert len(txs) == 1 and txs[0]["id"] == tx["id"] and txs[0]["amount"] == 50
    assert txs[0]["fba_fifo"]["cost_source"] == "FBA FIFO" and txs[0]["fba_fifo"]["total_cost_usd"] == 19


def test_3_fifo_older_lot_first_and_history_stable():
    ST["lotB"] = lot("SKU-A", 100, 10, 100, "2026-01-10")["id"]
    assert order(oid(1))["total_cost_usd"] == 19
    income(oid(2), 60, "2026-01-11")
    import_orders([(oid(2), "2026-01-11", "SKU-A", 3)])
    o = order(oid(2))
    assert o["total_cost_usd"] == 28.5 and {a["lot_id"] for a in o["allocations"]} == {ST["lotA"]}


def test_4_order_crosses_two_lots():
    r = S.post(f"{API}/fba/lots/{ST['lotA']}/adjust", json={"adjustment_type": "correct_remaining", "value": 1, "note": "count"})
    assert r.status_code == 200 and r.json()["remaining_quantity"] == 1
    income(oid(3), 70, "2026-01-12")
    import_orders([(oid(3), "2026-01-12", "SKU-A", 3)])
    o = order(oid(3))
    split = {a["lot_id"]: a["quantity"] for a in o["allocations"]}
    assert split == {ST["lotA"]: 1, ST["lotB"]: 2} and o["total_cost_usd"] == 31.5
    hist = S.get(f"{API}/fba/lots/{ST['lotA']}/history").json()
    assert any(a["adjustment_type"] == "correct_remaining" and a["previous_value"]["remaining_quantity"] == 95
               for a in hist["adjustments"])


def test_5_missing_cost_then_lot_added():
    income(oid(4), 40, "2026-01-13")
    import_orders([(oid(4), "2026-01-13", "SKU-B", 1)])
    o = order(oid(4))
    assert o["cost_status"] == "missing" and o["total_cost_usd"] == 0 and o["net_profit_usd"] is None
    lot("SKU-B", 10, 5, 10, "2026-01-01")
    o = order(oid(4))
    assert o["cost_status"] == "costed" and o["total_cost_usd"] == 6 and o["net_profit_usd"] == 34


def test_7_asin_report_matches_orders():
    data = orders()
    for key in ("amazon_net_revenue_usd", "product_cost_usd", "inbound_cost_usd", "total_fba_cost_usd", "net_profit_usd"):
        assert round(sum(a[key] for a in data["asin_report"]), 2) == data["summary"][key]
    assert round(sum(o["total_cost_usd"] for o in data["orders"]), 2) == data["summary"]["total_fba_cost_usd"]
    assert data["summary"]["orders"] == 4 and data["summary"]["units_sold"] == 9


def test_8_inventory_value():
    inv = S.get(f"{API}/fba/inventory", params={"store_id": ST["store"]}).json()
    expected = round(sum(l["remaining_quantity"] * l["landed_unit_cost_usd"] for l in lots().values()
                         if l["lot_status"] == "OPEN"), 2)
    assert inv["totals"]["inventory_value_usd"] == expected == 98 * 11 + 9 * 6
    cf = S.get(f"{API}/fba/cash-flow-metrics", params={"store_id": ST["store"]}).json()
    assert cf["current_inventory_value"] == expected and cf["realized_inventory_cost"] == 85


def test_9_repeated_processing_idempotent():
    before_tx, before_lots = tx_count(), lots()
    import_orders([(oid(1), "2026-01-05", "SKU-A", 2), (oid(3), "2026-01-12", "SKU-A", 3)])
    assert S.post(f"{API}/fba/allocate", params={"store_id": ST["store"]}).json()["created_allocations"] == 0
    assert tx_count() == before_tx
    assert {k: v["remaining_quantity"] for k, v in lots().items()} == {k: v["remaining_quantity"] for k, v in before_lots.items()}


def test_10_refund_no_stock_increase():
    before = {k: v["remaining_quantity"] for k, v in lots().items()}
    r = S.post(f"{API}/transactions", json={"store_id": ST["store"], "marketplace": "US", "type": "expense",
                                            "category": "Refunds", "amount": 50, "currency": "USD",
                                            "date": "2026-01-20", "order_id": oid(1)})
    assert r.status_code == 200, r.text
    import_orders([(oid(1), "2026-01-05", "SKU-A", 2)])
    orders()
    assert {k: v["remaining_quantity"] for k, v in lots().items()} == before


def _totals(**extra):
    d = S.get(f"{API}/dashboard/summary", params={"store_id": ST["store"], **extra}).json()
    p = S.get(f"{API}/portfolio/summary", params={"store_id": ST["store"], "start_date": "2026-01-01",
                                                  "end_date": "2026-01-31", **extra}).json()
    return d, p


def test_11_aggregate_uses_fifo_once_everywhere():
    # O5: manual product cost (must be ignored for FBA) + extra cost (kept)
    r = S.post(f"{API}/transactions", json={"store_id": ST["store"], "marketplace": "US", "type": "income",
                                            "category": "Order payments", "amount": 100, "currency": "USD",
                                            "date": "2026-01-25", "order_id": oid(5), "product_cost": 7, "extra_cost": 2})
    assert r.status_code == 200, r.text
    import_orders([(oid(5), "2026-01-25", "SKU-B", 1)])
    data = orders()
    o5 = next(o for o in data["orders"] if o["order_id"] == oid(5))
    assert o5["total_cost_usd"] == 6 and o5["net_profit_usd"] == 92
    count = tx_count()
    d1, p1 = _totals()
    d2, p2 = _totals()
    assert tx_count() == count and d1 == d2
    revenue = 50 + 60 + 70 + 40 + 100
    refunds = 50
    fifo = 19 + 28.5 + 31.5 + 6 + 6
    for t in (d1, p1):
        assert t["revenue"] == revenue
        assert round(t["expenses"], 2) == round(refunds + fifo + 2, 2)
        assert round(t["net_profit"], 2) == round(revenue - refunds - fifo - 2, 2)
    inv = S.get(f"{API}/fba/inventory", params={"store_id": ST["store"]}).json()["totals"]["inventory_value_usd"]
    assert inv > 0 and round(d1["expenses"], 2) == round(refunds + fifo + 2, 2)
    search = S.get(f"{API}/transactions/search", params={"store_id": ST["store"], "outcome": "profit", "page_size": 100}).json()
    assert oid(5) in {t["order_id"] for t in search["items"]}
    loss = S.get(f"{API}/transactions/search", params={"store_id": ST["store"], "outcome": "loss", "page_size": 100}).json()
    assert {t["order_id"] for t in loss["items"]} == {oid(1)}  # 50 - 50 refund - 19 fifo < 0
