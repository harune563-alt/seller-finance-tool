import os
import re
from datetime import datetime, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor

import pytest
import requests
from pymongo import MongoClient


# Auth hardening regression: lockout, reset, indexes, CORS and cookie-origin guard
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
TEST_EMAIL = "test_3a991703@example.com"
TEST_PASSWORD = "testpass123"
BAD_PASSWORD = "wrongpass123"
ALLOWED_ORIGIN = "https://amazon-payments-dev.preview.emergentagent.com"
UNTRUSTED_ORIGIN = "https://evil.example.com"


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def mongo_db():
    mongo_url = os.environ.get("MONGO_URL")
    db_name = os.environ.get("DB_NAME")
    if not mongo_url or not db_name:
        pytest.skip("MONGO_URL or DB_NAME not set")
    client = MongoClient(mongo_url)
    db = client[db_name]
    yield db
    client.close()


def _identifier_regex(email: str):
    return {"$regex": f":{re.escape(email.lower())}$"}


def _clear_attempts(db, email: str):
    db.login_attempts.delete_many({"identifier": _identifier_regex(email)})


def _get_attempt_entry(db, email: str):
    return db.login_attempts.find_one({"identifier": _identifier_regex(email)}, sort=[("expires_at", -1)])


def _bad_login(base_url: str, email: str):
    return requests.post(f"{base_url}/api/auth/login", json={"email": email, "password": BAD_PASSWORD}, timeout=20)


def test_hash_and_required_indexes_present(mongo_db):
    admin = mongo_db.users.find_one({"email": "admin@amzsuite.com"})
    assert admin is not None
    assert isinstance(admin.get("password_hash"), str)
    assert admin["password_hash"].startswith("$2b$")

    user_indexes = mongo_db.users.index_information()
    assert any(idx.get("unique") and idx.get("key") == [("email", 1)] for idx in user_indexes.values())

    attempt_indexes = mongo_db.login_attempts.index_information()
    assert any(idx.get("unique") and idx.get("key") == [("identifier", 1)] for idx in attempt_indexes.values())
    assert any(idx.get("key") == [("expires_at", 1)] and idx.get("expireAfterSeconds") == 0 for idx in attempt_indexes.values())


def test_login_me_still_work(base_url):
    session = requests.Session()
    login = session.post(f"{base_url}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert login.status_code == 200
    cookie = login.headers.get("set-cookie", "")
    assert "access_token=" in cookie
    assert "httponly" in cookie.lower()

    token = login.json().get("token")
    assert isinstance(token, str) and token

    me_cookie = session.get(f"{base_url}/api/auth/me", timeout=20)
    assert me_cookie.status_code == 200
    assert me_cookie.json()["email"] == TEST_EMAIL

    me_bearer = requests.get(f"{base_url}/api/auth/me", headers={"Authorization": f"Bearer {token}"}, timeout=20)
    assert me_bearer.status_code == 200
    assert me_bearer.json()["email"] == TEST_EMAIL


def test_success_before_limit_resets_counter(base_url, mongo_db):
    _clear_attempts(mongo_db, TEST_EMAIL)

    first = _bad_login(base_url, TEST_EMAIL)
    second = _bad_login(base_url, TEST_EMAIL)
    assert first.status_code == 401
    assert second.status_code == 401

    ok = requests.post(f"{base_url}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert ok.status_code == 200

    assert _get_attempt_entry(mongo_db, TEST_EMAIL) is None


def test_five_invalid_attempts_lockout_and_retry_after(base_url, mongo_db):
    _clear_attempts(mongo_db, TEST_EMAIL)

    statuses = []
    for _ in range(5):
        statuses.append(_bad_login(base_url, TEST_EMAIL).status_code)
    assert statuses[:4] == [401, 401, 401, 401]
    assert statuses[4] == 429

    blocked = requests.post(f"{base_url}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert blocked.status_code == 429
    retry_after = blocked.headers.get("Retry-After")
    assert retry_after is not None
    assert int(retry_after) >= 1


def test_expired_lockout_allows_valid_login(base_url, mongo_db):
    _clear_attempts(mongo_db, TEST_EMAIL)

    for _ in range(5):
        _bad_login(base_url, TEST_EMAIL)

    entry = _get_attempt_entry(mongo_db, TEST_EMAIL)
    assert entry is not None

    mongo_db.login_attempts.update_one(
        {"_id": entry["_id"]},
        {"$set": {"attempts": 5, "expires_at": datetime.now(timezone.utc) - timedelta(seconds=10)}},
    )

    unlocked = requests.post(f"{base_url}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert unlocked.status_code == 200


def test_concurrent_bad_attempts_counted_atomically(base_url, mongo_db):
    _clear_attempts(mongo_db, TEST_EMAIL)

    with ThreadPoolExecutor(max_workers=6) as pool:
        responses = list(pool.map(lambda _: _bad_login(base_url, TEST_EMAIL), range(6)))

    statuses = [r.status_code for r in responses]
    assert statuses.count(429) >= 1
    assert statuses.count(401) >= 1

    entry = _get_attempt_entry(mongo_db, TEST_EMAIL)
    assert entry is not None
    assert entry["attempts"] >= 5


def test_cors_preflight_allowed_origin(base_url):
    r = requests.options(
        f"{base_url}/api/auth/login",
        headers={
            "Origin": ALLOWED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout=20,
    )
    assert r.status_code in (200, 204)
    assert r.headers.get("access-control-allow-origin") == ALLOWED_ORIGIN
    assert r.headers.get("access-control-allow-credentials") == "true"


def test_cors_preflight_untrusted_origin_not_allowed(base_url):
    r = requests.options(
        f"{base_url}/api/auth/login",
        headers={
            "Origin": UNTRUSTED_ORIGIN,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
        timeout=20,
    )
    assert r.status_code in (200, 400, 403)
    assert r.headers.get("access-control-allow-origin") != UNTRUSTED_ORIGIN


def test_cross_origin_cookie_mutation_blocked_403(base_url, mongo_db):
    _clear_attempts(mongo_db, TEST_EMAIL)

    session = requests.Session()
    login = session.post(f"{base_url}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=20)
    assert login.status_code == 200

    response = session.post(
        f"{base_url}/api/stores",
        headers={"Origin": UNTRUSTED_ORIGIN},
        json={"name": "TEST_BLOCKED_ORIGIN", "marketplaces": ["US"], "default_currency": "USD"},
        timeout=20,
    )
    assert response.status_code == 403
