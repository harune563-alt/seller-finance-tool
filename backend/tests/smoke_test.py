"""Runtime smoke tests for restored repo (READ-ONLY verification)."""
import os
import requests
import pytest

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://tamam-seller.preview.emergentagent.com").rstrip("/")
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Content-Type": "application/json"})
    return s


@pytest.fixture(scope="module")
def auth_session(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, f"login failed: {r.status_code} {r.text}"
    return session


def test_login_admin(session):
    r = session.post(f"{BASE_URL}/api/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
    assert r.status_code == 200, r.text
    # Check cookie set
    cookies = r.cookies
    assert len(cookies) > 0 or "token" in r.json() or "access_token" in r.json(), f"no cookie or token: {r.json()}"


def test_auth_me(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/auth/me")
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("email") == ADMIN_EMAIL


def test_dashboard_summary(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/dashboard/summary")
    assert r.status_code == 200, r.text


def test_stores(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/stores")
    assert r.status_code == 200, r.text


def test_sellerflash_history(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/sellerflash/history")
    assert r.status_code == 200, r.text


def test_transactions_import_history(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/transactions/import/history")
    assert r.status_code == 200, r.text


def test_fx_to_usd(auth_session):
    r = auth_session.get(f"{BASE_URL}/api/fx/to-usd", params={"currency": "TRY", "date": "2024-10-07"})
    assert r.status_code == 200, r.text
    data = r.json()
    # Expect a rate field
    assert "rate" in data or "value" in data or "amount" in data, f"unexpected: {data}"


def test_cors_preflight_allowed():
    headers = {
        "Origin": "https://tamam-seller.preview.emergentagent.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    r = requests.options(f"{BASE_URL}/api/auth/login", headers=headers)
    assert r.status_code in (200, 204), r.text
    assert r.headers.get("access-control-allow-origin") == "https://tamam-seller.preview.emergentagent.com"


def test_cors_preflight_denied_evil():
    headers = {
        "Origin": "https://evil.example.com",
        "Access-Control-Request-Method": "POST",
        "Access-Control-Request-Headers": "content-type",
    }
    r = requests.options(f"{BASE_URL}/api/auth/login", headers=headers)
    # Evil origin should NOT get allow-origin matching it
    allow = r.headers.get("access-control-allow-origin")
    assert allow != "https://evil.example.com", f"Evil origin allowed! {allow}"
