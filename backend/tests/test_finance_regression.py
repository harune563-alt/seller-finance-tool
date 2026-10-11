import io
import os
import uuid
from pathlib import Path
from datetime import date

import pytest
import requests


# Core auth + transactions + csv regression coverage for finance workflows
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def admin_session(base_url):
    s = requests.Session()
    r = s.post(f"{base_url}/api/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data.get("token"), str) and data["token"]
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return s


@pytest.fixture
def isolated_store(admin_session, base_url):
    payload = {
        "name": f"TEST_ISO_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US", "CA"],
        "default_currency": "USD",
    }
    r = admin_session.post(f"{base_url}/api/stores", json=payload)
    assert r.status_code == 200
    store = r.json()
    assert store["marketplaces"] == ["US", "CA"]
    yield store
    admin_session.delete(f"{base_url}/api/stores/{store['id']}")


def _tx_payload(store_id, **overrides):
    payload = {
        "store_id": store_id,
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 1000,
        "currency": "USD",
        "date": date.today().isoformat(),
        "description": "",
        "order_id": f"TEST-ORDER-{uuid.uuid4().hex[:6]}",
        "product_cost": 0,
        "shipping_cost": 0,
        "extra_cost": 0,
        "product_cost_recovery": 0,
        "shipping_cost_recovery": 0,
    }
    payload.update(overrides)
    return payload


def test_auth_login_sets_cookie_and_token(base_url):
    r = requests.post(f"{base_url}/api/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})
    assert r.status_code == 200
    assert isinstance(r.json().get("token"), str)
    cookie = r.headers.get("set-cookie", "")
    assert "access_token=" in cookie
    assert "HttpOnly" in cookie or "httponly" in cookie.lower()


def test_auth_me_with_bearer(admin_session, base_url):
    r = admin_session.get(f"{base_url}/api/auth/me")
    assert r.status_code == 200
    data = r.json()
    assert data["email"] == "admin@amzsuite.com"


def test_store_creation_isolated_marketplaces(admin_session, base_url, isolated_store):
    r = admin_session.get(f"{base_url}/api/stores")
    assert r.status_code == 200
    stores = r.json()
    hit = [s for s in stores if s["id"] == isolated_store["id"]]
    assert len(hit) == 1
    assert hit[0]["marketplaces"] == ["US", "CA"]
    assert hit[0]["default_currency"] == "USD"


def test_income_costs_flow_and_summary(admin_session, base_url, isolated_store):
    order_id = f"TEST-ORDER-{uuid.uuid4().hex[:6]}"
    create = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(
            isolated_store["id"],
            order_id=order_id,
            amount=1000,
            product_cost=400,
            shipping_cost=100,
            extra_cost=20,
        ),
    )
    assert create.status_code == 200
    tx = create.json()
    assert tx["category"] == "Order payments"
    assert tx["product_cost"] == 400
    assert tx["shipping_cost"] == 100
    assert tx["extra_cost"] == 20

    rows = admin_session.get(f"{base_url}/api/transactions", params={"store_id": isolated_store["id"], "marketplace": "US"})
    assert rows.status_code == 200
    created = [r for r in rows.json() if r["id"] == tx["id"]]
    assert len(created) == 1

    s = admin_session.get(f"{base_url}/api/dashboard/summary", params={"store_id": isolated_store["id"], "marketplace": "US", "currency": "USD"})
    assert s.status_code == 200
    data = s.json()
    assert data["revenue"] == 1000
    assert data["expenses"] == 520
    assert data["net_profit"] == 480


def test_refunds_fees_affect_summary(admin_session, base_url, isolated_store):
    order_id = f"TEST-ORDER-{uuid.uuid4().hex[:6]}"
    sale = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(isolated_store["id"], order_id=order_id, amount=1000, product_cost=400, shipping_cost=100, extra_cost=20),
    )
    assert sale.status_code == 200

    refund = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(
            isolated_store["id"],
            type="expense",
            category="Refunds",
            amount=1000,
            order_id=order_id,
            product_cost=0,
            shipping_cost=0,
            extra_cost=0,
            product_cost_recovery=400,
            shipping_cost_recovery=80,
        ),
    )
    assert refund.status_code == 200

    fee = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(
            isolated_store["id"],
            type="expense",
            category="Service Fees",
            amount=20,
            order_id=order_id,
            product_cost=0,
            shipping_cost=0,
            extra_cost=0,
        ),
    )
    assert fee.status_code == 200

    s = admin_session.get(f"{base_url}/api/dashboard/summary", params={"store_id": isolated_store["id"], "marketplace": "US", "currency": "USD"})
    assert s.status_code == 200
    data = s.json()
    assert data["revenue"] == 1000
    assert data["expenses"] == 1060
    assert data["net_profit"] == -60
    assert data["margin"] == -6


def test_transaction_validation_negative_cost_rejected(admin_session, base_url, isolated_store):
    r = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(isolated_store["id"], product_cost=-1),
    )
    assert r.status_code == 422


def test_transaction_validation_zero_amount_rejected(admin_session, base_url, isolated_store):
    r = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(isolated_store["id"], amount=0),
    )
    assert r.status_code == 422


def test_transaction_validation_marketplace_currency_pair(admin_session, base_url, isolated_store):
    r = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(isolated_store["id"], marketplace="CA", currency="USD"),
    )
    assert r.status_code == 400
    assert "Para birimi" in r.json().get("detail", "")


def test_cross_user_cost_update_denied(base_url):
    uniq = uuid.uuid4().hex[:8]
    email = f"test_{uniq}@example.com"
    password = "testpass123"

    reg = requests.post(f"{base_url}/api/auth/register", json={"email": email, "password": password, "name": "Tester"})
    assert reg.status_code == 200
    with Path("/app/memory/test_credentials.md").open("a") as credentials:
        credentials.write(f"\n## Isolation test account\n- Email: {email}\n- Password: {password}\n- Role: user\n")
    user_token = reg.json()["token"]

    admin = requests.Session()
    admin_login = admin.post(f"{base_url}/api/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})
    assert admin_login.status_code == 200
    admin.headers.update({"Authorization": f"Bearer {admin_login.json()['token']}"})

    store = admin.post(
        f"{base_url}/api/stores",
        json={"name": f"TEST_CROSS_{uniq}", "marketplaces": ["US"], "default_currency": "USD"},
    )
    assert store.status_code == 200
    sid = store.json()["id"]

    tx = admin.post(
        f"{base_url}/api/transactions",
        json=_tx_payload(sid, amount=200, product_cost=50),
    )
    assert tx.status_code == 200

    other = requests.Session()
    other.headers.update({"Authorization": f"Bearer {user_token}"})
    patch = other.patch(
        f"{base_url}/api/transactions/{tx.json()['id']}/costs",
        json={"product_cost": 10, "shipping_cost": 0, "extra_cost": 0, "product_cost_recovery": 0, "shipping_cost_recovery": 0},
    )
    assert patch.status_code == 404

    admin.delete(f"{base_url}/api/stores/{sid}")


def test_csv_preview_commit_idempotent(admin_session, base_url, isolated_store):
    csv_body = "Date,Transaction type,Total (USD),Order Id\n2026-02-01,Order,100,TEST-CSV-1\n2026-02-02,Refund,-40,TEST-CSV-1\n2026-02-03,Service Fee,-10,TEST-CSV-1\n"
    files = {"file": ("payments.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    params = {"store_id": isolated_store["id"], "marketplace": "US", "commit": "false"}

    preview = admin_session.post(f"{base_url}/api/transactions/import", files=files, params=params)
    assert preview.status_code == 200
    p = preview.json()
    assert p["committed"] is False
    assert p["accepted"] == 3
    assert p["inserted"] == 0

    rows_before = admin_session.get(f"{base_url}/api/transactions", params={"store_id": isolated_store["id"], "marketplace": "US"})
    assert rows_before.status_code == 200
    assert len(rows_before.json()) == 0

    files2 = {"file": ("payments.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    commit = admin_session.post(f"{base_url}/api/transactions/import", files=files2, params={**params, "commit": "true"})
    assert commit.status_code == 200
    c = commit.json()
    assert c["committed"] is True
    assert c["inserted"] == 3

    files3 = {"file": ("payments.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    repeat = admin_session.post(f"{base_url}/api/transactions/import", files=files3, params={**params, "commit": "true"})
    assert repeat.status_code == 200
    r = repeat.json()
    assert r["inserted"] == 0
    assert r["duplicates"] == 3


def test_csv_unknown_type_and_bad_date_reported(admin_session, base_url, isolated_store):
    csv_body = "Date,Transaction type,Total (USD),Order Id\nBAD-DATE,UnknownType,10,ORD-1\n"
    files = {"file": ("bad.csv", io.BytesIO(csv_body.encode("utf-8")), "text/csv")}
    r = admin_session.post(
        f"{base_url}/api/transactions/import",
        files=files,
        params={"store_id": isolated_store["id"], "marketplace": "US", "commit": "false"},
    )
    assert r.status_code == 200
    data = r.json()
    assert data["accepted"] == 0
    assert data["rejected_count"] >= 1
    assert any("Desteklenmeyen işlem türü" in issue["reason"] or "Tarih" in issue["reason"] for issue in data["issues"])
