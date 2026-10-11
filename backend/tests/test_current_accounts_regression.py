import os
import uuid
from datetime import date

import pytest
import requests
from pymongo import MongoClient


# Current Accounts (Cari Hesap Ekstresi) regression tests
TEST_EMAIL = "company-test-76940be4f3@example.com"
TEST_PASSWORD = "T3st!Comp@ny2026#A"


def _read_env(path: str, key: str):
    if not os.path.exists(path):
        return None
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            raw = line.strip()
            if not raw or raw.startswith("#") or "=" not in raw:
                continue
            k, v = raw.split("=", 1)
            if k.strip() == key:
                return v.strip().strip('"').strip("'")
    return None


@pytest.fixture(scope="session")
def base_url():
    value = os.environ.get("REACT_APP_BACKEND_URL") or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
    if not value:
        pytest.skip("REACT_APP_BACKEND_URL not configured")
    return value.rstrip("/")


@pytest.fixture(scope="session")
def api_session(base_url):
    s = requests.Session()
    login = s.post(
        f"{base_url}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    if login.status_code != 200:
        pytest.skip(f"login failed: {login.status_code} {login.text[:200]}")
    s.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
    return s


@pytest.fixture(scope="session")
def user_id(api_session, base_url):
    me = api_session.get(f"{base_url}/api/auth/me", timeout=30)
    assert me.status_code == 200
    return me.json()["id"]


@pytest.fixture(scope="session", autouse=True)
def cleanup(user_id):
    created_people = {"ids": []}
    yield created_people
    mongo_url = _read_env("/app/backend/.env", "MONGO_URL")
    db_name = _read_env("/app/backend/.env", "DB_NAME")
    if not mongo_url or not db_name:
        return
    client = MongoClient(mongo_url)
    db = client[db_name]
    db.company_current_entries.delete_many({"user_id": user_id})
    db.company_people.delete_many({"user_id": user_id, "name": {"$regex": "^TEST_CARI_"}})
    client.close()


def _today():
    return date.today().isoformat()


@pytest.fixture
def person(api_session, base_url, cleanup):
    name = f"TEST_CARI_{uuid.uuid4().hex[:8]}"
    r = api_session.post(f"{base_url}/api/company/people", json={"name": name, "role": "contact", "note": "cari"}, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    cleanup["ids"].append(data["id"])
    return data


def _entry(**overrides):
    body = {
        "request_id": str(uuid.uuid4()),
        "amount": "100.00",
        "date": _today(),
        "note": "",
        "person_id": None,
        "direction": "payable",
        "currency": "USD",
        "cash_effect": "none",
        "cash_status": "pending",
    }
    body.update(overrides)
    return body


# POST creates payable + cash_effect=out + completed; summary totals and balance_after
def test_create_payable_completed_cash_out(api_session, base_url, person):
    payload = _entry(person_id=person["id"], direction="payable", cash_effect="out", cash_status="completed", amount="100.00")
    r = api_session.post(f"{base_url}/api/company/current-accounts", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data["person_id"] == person["id"]
    assert data["direction"] == "payable"
    assert data["cash_effect"] == "out"
    assert data["cash_status"] == "completed"
    assert data["amount"] == 100.0
    # list
    s = api_session.get(f"{base_url}/api/company/current-accounts", params={"person_id": person["id"]}, timeout=30)
    assert s.status_code == 200
    sdata = s.json()
    assert any(e["person_id"] == person["id"] for e in sdata["summaries"])
    summary = next(e for e in sdata["summaries"] if e["person_id"] == person["id"] and e["currency"] == "USD")
    assert summary["total_payable"] == 100.0
    assert summary["total_receivable"] == 0.0
    assert summary["net_balance"] == 100.0
    assert summary["entry_count"] == 1
    assert sdata["entries"][0]["balance_after"] == 100.0


# Receivable + cash_effect=in + pending => increases receivable/net but NOT overview cash balance
def test_pending_receivable_does_not_affect_cash(api_session, base_url, person):
    overview_before = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_before = next(b for b in overview_before["balances"] if b["currency"] == "USD")["cash_balance"]
    payload = _entry(person_id=person["id"], direction="receivable", cash_effect="in", cash_status="pending", amount="50.00")
    r = api_session.post(f"{base_url}/api/company/current-accounts", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    entry_id = r.json()["id"]
    overview_after = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_after = next(b for b in overview_after["balances"] if b["currency"] == "USD")["cash_balance"]
    assert usd_after == usd_before, "pending movement must not affect cash"
    assert not any(e["id"] == entry_id and e.get("source") == "current_account" for e in overview_after["ledger"])
    s = api_session.get(f"{base_url}/api/company/current-accounts", params={"person_id": person["id"], "currency": "USD"}, timeout=30).json()
    summary = next(e for e in s["summaries"] if e["person_id"] == person["id"])
    assert summary["total_receivable"] == 50.0


# Completed cash in/out appear in overview ledger with current_account source and move cash balance
def test_completed_cash_effects_in_overview(api_session, base_url, person):
    before = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_before = next(b for b in before["balances"] if b["currency"] == "USD")["cash_balance"]
    r_in = api_session.post(f"{base_url}/api/company/current-accounts", json=_entry(person_id=person["id"], direction="receivable", cash_effect="in", cash_status="completed", amount="200.00"), timeout=30)
    assert r_in.status_code == 200
    r_out = api_session.post(f"{base_url}/api/company/current-accounts", json=_entry(person_id=person["id"], direction="payable", cash_effect="out", cash_status="completed", amount="30.00"), timeout=30)
    assert r_out.status_code == 200
    after = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_after = next(b for b in after["balances"] if b["currency"] == "USD")["cash_balance"]
    assert round(usd_after - usd_before, 2) == 170.0
    sources = [e for e in after["ledger"] if e.get("source") == "current_account"]
    kinds = {e["kind"] for e in sources}
    assert "current_cash_in" in kinds and "current_cash_out" in kinds


# PUT edits and avoids duplicate ledger rows; DELETE reverses effect
def test_update_and_delete_adjust_overview(api_session, base_url, person):
    create = api_session.post(f"{base_url}/api/company/current-accounts", json=_entry(person_id=person["id"], direction="receivable", cash_effect="in", cash_status="completed", amount="40.00"), timeout=30)
    assert create.status_code == 200
    entry_id = create.json()["id"]
    before = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_before = next(b for b in before["balances"] if b["currency"] == "USD")["cash_balance"]
    # change amount & cash_effect to out
    update_body = {
        "amount": "25.00", "date": _today(), "note": "edited", "request_id": str(uuid.uuid4()),
        "person_id": person["id"], "direction": "receivable", "currency": "USD", "cash_effect": "out", "cash_status": "completed",
    }
    upd = api_session.put(f"{base_url}/api/company/current-accounts/{entry_id}", json=update_body, timeout=30)
    assert upd.status_code == 200, upd.text
    after = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_after = next(b for b in after["balances"] if b["currency"] == "USD")["cash_balance"]
    # was +40 (in completed), now -25 (out completed) => delta -65
    assert round(usd_after - usd_before, 2) == -65.0
    ledger_rows = [e for e in after["ledger"] if e["id"] == entry_id and e.get("source") == "current_account"]
    assert len(ledger_rows) == 1
    # delete reverses
    rm = api_session.delete(f"{base_url}/api/company/current-accounts/{entry_id}", timeout=30)
    assert rm.status_code == 200
    final = api_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_final = next(b for b in final["balances"] if b["currency"] == "USD")["cash_balance"]
    assert round(usd_final - usd_after, 2) == 25.0


# Idempotency: same request_id returns same entry; conflicting payload => 409
def test_idempotent_and_conflict(api_session, base_url, person):
    req = str(uuid.uuid4())
    body = _entry(request_id=req, person_id=person["id"], amount="10.00", direction="payable", cash_effect="none", cash_status="pending")
    r1 = api_session.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r1.status_code == 200
    r2 = api_session.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r2.status_code == 200
    assert r1.json()["id"] == r2.json()["id"]
    conflict = dict(body)
    conflict["amount"] = "20.00"
    r3 = api_session.post(f"{base_url}/api/company/current-accounts", json=conflict, timeout=30)
    assert r3.status_code == 409, r3.text


# Filter + chronological statement with balance_after
def test_filter_and_balance_sequence(api_session, base_url, person):
    for amt, direction in [("10.00", "payable"), ("4.00", "receivable"), ("6.00", "payable")]:
        r = api_session.post(f"{base_url}/api/company/current-accounts", json=_entry(person_id=person["id"], amount=amt, direction=direction, cash_effect="none", cash_status="pending"), timeout=30)
        assert r.status_code == 200
    data = api_session.get(f"{base_url}/api/company/current-accounts", params={"person_id": person["id"], "currency": "USD"}, timeout=30).json()
    # all entries filtered to this person
    assert all(e["person_id"] == person["id"] for e in data["entries"])
    # at least 3 entries present; running balance_after values must appear
    balances = [e["balance_after"] for e in sorted(data["entries"], key=lambda x: (x["date"], x["created_at"]))]
    # cumulative = +10 -4 +6 = 12 at the end
    assert balances[-1] == 12.0


# Legacy debts endpoint still works
def test_legacy_debts_endpoint_intact(api_session, base_url, person):
    body = {
        "request_id": str(uuid.uuid4()), "amount": "15.00", "date": _today(), "note": "legacy",
        "person_id": person["id"], "direction": "payable", "currency": "USD", "cash_effect": False,
    }
    r = api_session.post(f"{base_url}/api/company/debts", json=body, timeout=30)
    assert r.status_code == 200, r.text
    debt_id = r.json()["id"]
    # payment decorator sanity
    pay = api_session.post(f"{base_url}/api/company/debts/{debt_id}/payments", json={
        "request_id": str(uuid.uuid4()), "amount": "5.00", "date": _today(), "note": ""}, timeout=30)
    assert pay.status_code == 200, pay.text
    assert pay.json()["remaining"] == 10.0
    # clean up this debt so cleanup doesn't block
    api_session.delete(f"{base_url}/api/company/debts/{debt_id}", timeout=30)


# Deleting a person who has current entries returns 409
def test_delete_person_with_current_entries_blocked(api_session, base_url, person):
    r = api_session.post(f"{base_url}/api/company/current-accounts", json=_entry(person_id=person["id"], amount="1.00", direction="payable"), timeout=30)
    assert r.status_code == 200
    d = api_session.delete(f"{base_url}/api/company/people/{person['id']}", timeout=30)
    assert d.status_code == 409
    bd = api_session.post(f"{base_url}/api/company/people/bulk-delete", json={"ids": [person["id"]]}, timeout=30)
    assert bd.status_code == 409
