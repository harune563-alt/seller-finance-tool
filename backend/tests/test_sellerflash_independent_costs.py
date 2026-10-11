"""Focused SellerFlash tests: independent product/shipping fields, USD-only, idempotent, manual preserved."""
import uuid

import pytest
import requests

BASE = open("/app/frontend/.env").read().split("REACT_APP_BACKEND_URL=")[1].split()[0]
API = f"{BASE}/api"
S = requests.Session()
S.headers["Origin"] = BASE
ST = {}


def oid(n):
    return f"702-{ST['p']}-{n:07d}"


def sf(rows):
    body = "Seller Order Id,Product Cost,Initial Shipment Cost,Marketplace\n" + "".join(
        f"{o},{'' if p is None else p},{'' if s is None else s},{mp}\n" for o, p, s, mp in rows)
    r = S.post(f"{API}/sellerflash/import", params={"store_id": ST["store"], "commit": "true"},
               files={"file": ("sf.csv", body.encode(), "text/csv")})
    assert r.status_code == 200, r.text
    return r.json()


def income(order_id, mp="US", currency="USD", amount=100, **costs):
    r = S.post(f"{API}/transactions", json={"store_id": ST["store"], "marketplace": mp, "type": "income",
                                            "category": "Order payments", "amount": amount, "currency": currency,
                                            "date": "2026-02-02", "order_id": order_id, **costs})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def tx(order_id):
    return next(t for t in S.get(f"{API}/transactions", params={"store_id": ST["store"], "limit": 1000}).json()
                if t["order_id"] == order_id)


def rec(order_id):
    return S.get(f"{API}/sellerflash/costs", params={"store_id": ST["store"], "order_id": order_id}).json()["record"]


def status(result, order_id):
    return next(r["match_status"] for r in result["preview"] if r["seller_order_id"] == order_id)


@pytest.fixture(scope="module", autouse=True)
def setup():
    r = S.post(f"{API}/auth/register", json={"email": f"sf_{uuid.uuid4().hex[:8]}@test.com", "password": "Test12345!", "name": "SF"})
    S.headers["Authorization"] = f"Bearer {r.json().get('token') or r.json().get('access_token')}"
    ST["store"] = S.post(f"{API}/stores", json={"name": "SF Test", "marketplaces": ["US", "CA"], "default_currency": "USD"}).json()["id"]
    ST["p"] = uuid.uuid4().hex[:6]
    for n in (1, 2):
        income(oid(n))
    income(oid(3), "CA", "CAD")
    income(oid(4), product_cost=5)
    yield


def test_1_product_only():
    res = sf([(oid(1), 25, None, "Amazon.com")])
    assert status(res, oid(1)) == "new"
    t, r = tx(oid(1)), rec(oid(1))
    assert t["product_cost"] == 25 and t["shipping_cost"] == 0 and r["initial_shipment_cost"] is None


def test_2_shipping_only():
    sf([(oid(2), None, 8.5, "Amazon.com")])
    t, r = tx(oid(2)), rec(oid(2))
    assert t["shipping_cost"] == 8.5 and t["product_cost"] == 0 and r["product_cost"] is None


def test_3_and_5_product_first_then_shipping_blank_product_preserved():
    res = sf([(oid(1), None, 8.5, "Amazon.com")])
    assert status(res, oid(1)) == "partial_cost_completion"
    t, r = tx(oid(1)), rec(oid(1))
    assert (t["product_cost"], t["shipping_cost"]) == (25, 8.5)
    assert (r["product_cost"], r["initial_shipment_cost"]) == (25, 8.5)


def test_4_shipping_first_then_product():
    res = sf([(oid(2), 12, None, "")])
    assert status(res, oid(2)) == "partial_cost_completion"
    t = tx(oid(2))
    assert (t["product_cost"], t["shipping_cost"]) == (12, 8.5)


def test_6_product_update():
    res = sf([(oid(1), 27, None, "Amazon.com")])
    assert status(res, oid(1)) == "updated"
    t = tx(oid(1))
    assert (t["product_cost"], t["shipping_cost"]) == (27, 8.5) and t["usd_costs"]["product_cost"] == 27


def test_7_ca_order_usd_no_fx():
    res = sf([(oid(3), 25, 0, "Amazon.com")])  # SF marketplace US must not block CA Amazon order
    row = next(r for r in res["preview"] if r["seller_order_id"] == oid(3))
    assert row["amazon_match"] and row["cost_currency"] == "USD" and row["marketplace"] == "CA"
    t, r = tx(oid(3)), rec(oid(3))
    assert t["product_cost"] == 25 and t["usd_costs"]["product_cost"] == 25 and t["cost_currency"] == "USD"
    assert t["shipping_cost"] == 0 and r["initial_shipment_cost"] == 0  # explicit zero kept as zero
    assert r["currency"] == "USD" and r["product_cost_usd"] == 25 and not r.get("fx")


def test_8_reimport_idempotent():
    rows = [(oid(1), 27, 8.5, "Amazon.com"), (oid(3), 25, 0, "Amazon.com")]
    sf(rows)
    count = len(S.get(f"{API}/transactions", params={"store_id": ST["store"], "limit": 1000}).json())
    res = sf(rows)
    assert res["applied_costs"] == 0 and {status(res, oid(1)), status(res, oid(3))} == {"existing_unchanged"}
    assert len(S.get(f"{API}/transactions", params={"store_id": ST["store"], "limit": 1000}).json()) == count
    assert len([u for u in S.get(f"{API}/sellerflash/unmatched", params={"store_id": ST["store"]}).json()["items"]]) == 0
    assert (tx(oid(1))["product_cost"], tx(oid(1))["shipping_cost"]) == (27, 8.5)


def test_9_manual_override_preserved():
    res = sf([(oid(4), 30, 4, "Amazon.com")])
    assert status(res, oid(4)) == "manual_override_preserved" and res["applied_costs"] == 0
    t, r = tx(oid(4)), rec(oid(4))
    assert t["product_cost"] == 5 and t["shipping_cost"] == 0
    assert r["product_cost"] == 30  # source/reference value updated separately
