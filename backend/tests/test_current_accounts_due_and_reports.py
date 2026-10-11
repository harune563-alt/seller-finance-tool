"""Regression tests for Cari Hesap Ekstresi iteration 10:
- due_date / due_status (none/upcoming/due_soon/overdue/completed)
- bulk-complete and bulk-delete endpoints
- Excel + PDF report endpoints (filters + 422 validation)
- Overview reconciliation: only completed current cash effects appear
"""
import os
import uuid
from datetime import date, timedelta

import pytest
import requests
from pymongo import MongoClient


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
    v = os.environ.get("REACT_APP_BACKEND_URL") or _read_env("/app/frontend/.env", "REACT_APP_BACKEND_URL")
    if not v:
        pytest.skip("REACT_APP_BACKEND_URL missing")
    return v.rstrip("/")


@pytest.fixture(scope="session")
def api(base_url):
    s = requests.Session()
    r = s.post(f"{base_url}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
    if r.status_code != 200:
        pytest.skip(f"login failed: {r.status_code}")
    s.headers.update({"Authorization": f"Bearer {r.json()['token']}"})
    return s


@pytest.fixture(scope="session")
def user_id(api, base_url):
    me = api.get(f"{base_url}/api/auth/me", timeout=30)
    return me.json()["id"]


@pytest.fixture(scope="session", autouse=True)
def cleanup(user_id):
    yield
    mongo_url = _read_env("/app/backend/.env", "MONGO_URL")
    db_name = _read_env("/app/backend/.env", "DB_NAME")
    if not mongo_url or not db_name:
        return
    cl = MongoClient(mongo_url)
    db = cl[db_name]
    db.company_current_entries.delete_many({"user_id": user_id})
    db.company_people.delete_many({"user_id": user_id, "name": {"$regex": "^TEST_CARI_"}})
    cl.close()


def _today():
    return date.today().isoformat()


def _future(days):
    return (date.today() + timedelta(days=days)).isoformat()


def _past(days):
    return (date.today() - timedelta(days=days)).isoformat()


@pytest.fixture
def person(api, base_url):
    name = f"TEST_CARI_{uuid.uuid4().hex[:8]}"
    r = api.post(f"{base_url}/api/company/people", json={"name": name, "role": "contact", "note": ""}, timeout=30)
    assert r.status_code == 200
    return r.json()


def _entry(**ov):
    body = {
        "request_id": str(uuid.uuid4()),
        "amount": "10.00",
        "date": _today(),
        "note": "",
        "person_id": None,
        "direction": "payable",
        "currency": "USD",
        "cash_effect": "none",
        "cash_status": "pending",
    }
    body.update(ov)
    return body


# -- due_date / due_status --------------------------------------------------
def test_due_date_required_not_before_date(api, base_url, person):
    body = _entry(person_id=person["id"], date=_today(), due_date=_past(1))
    r = api.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r.status_code == 422


def test_due_status_none_when_no_due_date(api, base_url, person):
    body = _entry(person_id=person["id"])
    r = api.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r.status_code == 200
    assert r.json()["due_status"] == "none"


def test_due_status_due_soon_within_3_days(api, base_url, person):
    body = _entry(person_id=person["id"], due_date=_future(3))
    r = api.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r.status_code == 200
    assert r.json()["due_status"] == "due_soon"


def test_due_status_upcoming_when_far(api, base_url, person):
    body = _entry(person_id=person["id"], due_date=_future(30))
    r = api.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r.json()["due_status"] == "upcoming"


def test_due_status_overdue_when_past_and_pending(api, base_url, person):
    # entry date in past, due_date in past => overdue (and >= date)
    body = _entry(person_id=person["id"], date=_past(10), due_date=_past(2))
    r = api.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["due_status"] == "overdue"


def test_due_status_completed_overrides(api, base_url, person):
    body = _entry(person_id=person["id"], due_date=_future(1), cash_effect="out", cash_status="completed")
    r = api.post(f"{base_url}/api/company/current-accounts", json=body, timeout=30)
    assert r.status_code == 200
    assert r.json()["due_status"] == "completed"


# -- bulk-complete ----------------------------------------------------------
def test_bulk_complete_flips_pending_to_completed_and_cash_hits_overview(api, base_url, person):
    before = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_before = next(b for b in before["balances"] if b["currency"] == "USD")["cash_balance"]
    ids = []
    for amt, eff in [("12.00", "in"), ("5.00", "out")]:
        r = api.post(
            f"{base_url}/api/company/current-accounts",
            json=_entry(person_id=person["id"], amount=amt, direction="receivable" if eff == "in" else "payable", cash_effect=eff, cash_status="pending"),
            timeout=30,
        )
        assert r.status_code == 200
        ids.append(r.json()["id"])

    mid = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_mid = next(b for b in mid["balances"] if b["currency"] == "USD")["cash_balance"]
    assert usd_mid == usd_before, "pending must not affect cash"

    r = api.post(f"{base_url}/api/company/current-accounts/bulk-complete", json={"ids": ids}, timeout=30)
    assert r.status_code == 200, r.text
    assert r.json()["updated"] == 2

    after = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_after = next(b for b in after["balances"] if b["currency"] == "USD")["cash_balance"]
    assert round(usd_after - usd_before, 2) == 7.0  # +12 -5

    ledger_ids = [e["id"] for e in after["ledger"] if e.get("source") == "current_account" and e["id"] in ids]
    # exactly once each
    assert sorted(ledger_ids) == sorted(ids)

    # Second call is idempotent (matched_count==0 for pending-only => 404 OR 0 updated)
    r2 = api.post(f"{base_url}/api/company/current-accounts/bulk-complete", json={"ids": ids}, timeout=30)
    assert r2.status_code in (200, 404)
    final = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_final = next(b for b in final["balances"] if b["currency"] == "USD")["cash_balance"]
    assert round(usd_final - usd_after, 2) == 0.0


# -- bulk-delete ------------------------------------------------------------
def test_bulk_delete_removes_entries_and_cash(api, base_url, person):
    before = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_before = next(b for b in before["balances"] if b["currency"] == "USD")["cash_balance"]
    ids = []
    for amt in ["3.00", "4.00"]:
        r = api.post(
            f"{base_url}/api/company/current-accounts",
            json=_entry(person_id=person["id"], amount=amt, direction="payable", cash_effect="out", cash_status="completed"),
            timeout=30,
        )
        ids.append(r.json()["id"])
    mid = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_mid = next(b for b in mid["balances"] if b["currency"] == "USD")["cash_balance"]
    assert round(usd_mid - usd_before, 2) == -7.0

    d = api.post(f"{base_url}/api/company/current-accounts/bulk-delete", json={"ids": ids}, timeout=30)
    assert d.status_code == 200
    assert d.json()["deleted"] == 2
    after = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_after = next(b for b in after["balances"] if b["currency"] == "USD")["cash_balance"]
    assert round(usd_after - usd_before, 2) == 0.0
    assert not [e for e in after["ledger"] if e.get("id") in ids]


def test_bulk_delete_empty_returns_404(api, base_url):
    r = api.post(f"{base_url}/api/company/current-accounts/bulk-delete", json={"ids": [str(uuid.uuid4())]}, timeout=30)
    assert r.status_code == 404


# -- Excel report -----------------------------------------------------------
def test_excel_report_valid_xlsx(api, base_url, person):
    api.post(
        f"{base_url}/api/company/current-accounts",
        json=_entry(person_id=person["id"], amount="22.00", direction="payable", note="Türkçe şçğüö"),
        timeout=30,
    )
    r = api.get(
        f"{base_url}/api/company/current-accounts/report/excel",
        params={"person_id": person["id"], "currency": "USD", "start_date": _past(30), "end_date": _today()},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:200]
    assert r.content[:2] == b"PK", "not an xlsx"
    assert "spreadsheetml" in r.headers.get("content-type", "")


def test_excel_report_422_on_bad_date_range(api, base_url):
    r = api.get(
        f"{base_url}/api/company/current-accounts/report/excel",
        params={"start_date": _today(), "end_date": _past(5)},
        timeout=30,
    )
    assert r.status_code == 422


# -- PDF report -------------------------------------------------------------
def test_pdf_report_valid_pdf_with_turkish(api, base_url, person):
    api.post(
        f"{base_url}/api/company/current-accounts",
        json=_entry(person_id=person["id"], amount="33.00", direction="receivable", note="İçerik ÖĞÜŞ"),
        timeout=30,
    )
    r = api.get(
        f"{base_url}/api/company/current-accounts/report/pdf",
        params={"person_id": person["id"], "currency": "USD", "start_date": _past(30), "end_date": _today()},
        timeout=60,
    )
    assert r.status_code == 200, r.text[:300]
    assert r.content[:4] == b"%PDF", "not a pdf"
    assert "application/pdf" in r.headers.get("content-type", "")


def test_pdf_report_422_on_bad_date_range(api, base_url):
    r = api.get(
        f"{base_url}/api/company/current-accounts/report/pdf",
        params={"start_date": _today(), "end_date": _past(1)},
        timeout=30,
    )
    assert r.status_code == 422


# -- Overview reconciliation: only completed effects appear once -----------
def test_overview_contains_only_completed_current_cash_once(api, base_url, person):
    # pending entry
    r1 = api.post(
        f"{base_url}/api/company/current-accounts",
        json=_entry(person_id=person["id"], amount="9.00", direction="receivable", cash_effect="in", cash_status="pending"),
        timeout=30,
    )
    pending_id = r1.json()["id"]
    # completed entry
    r2 = api.post(
        f"{base_url}/api/company/current-accounts",
        json=_entry(person_id=person["id"], amount="11.00", direction="receivable", cash_effect="in", cash_status="completed"),
        timeout=30,
    )
    completed_id = r2.json()["id"]
    ov = api.get(f"{base_url}/api/company/overview", timeout=30).json()
    src_rows = [e for e in ov["ledger"] if e.get("source") == "current_account"]
    ids = [e["id"] for e in src_rows]
    assert pending_id not in ids
    assert ids.count(completed_id) == 1
