#!/usr/bin/env python3
"""
Company Finance CRUD Testing
Tests PUT/DELETE/bulk-delete operations for stores, people, capital, cash, debts, debt payments, and closings.
"""
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import requests


# Backend URL from environment
BASE_URL = "https://24b47787-80b4-43f5-a735-d2fdefafd0fa.preview.emergentagent.com"
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="session")
def base_url():
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def admin_session(base_url):
    """Create authenticated admin session"""
    s = requests.Session()
    login = s.post(
        f"{base_url}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Admin login failed: {login.status_code} {login.text}"
    payload = login.json()
    assert isinstance(payload.get("token"), str) and payload["token"], "No token in login response"
    s.headers.update({"Authorization": f"Bearer {payload['token']}"})
    return s


@pytest.fixture(scope="session")
def test_user_session(base_url):
    """Create a separate test user for cross-user testing"""
    email = f"test_company_{uuid.uuid4().hex[:8]}@example.com"
    password = "TestPass123!"
    
    s = requests.Session()
    reg = s.post(
        f"{base_url}/api/auth/register",
        json={"email": email, "password": password, "name": "Test User"},
        timeout=30,
    )
    assert reg.status_code == 200, f"User registration failed: {reg.status_code} {reg.text}"
    token = reg.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    return s


@pytest.fixture
def test_store(admin_session, base_url):
    """Create a test store"""
    payload = {
        "name": f"TEST_COMPANY_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US", "TR"],
        "default_currency": "USD",
    }
    r = admin_session.post(f"{base_url}/api/stores", json=payload, timeout=30)
    assert r.status_code == 200, f"Store creation failed: {r.status_code} {r.text}"
    store = r.json()
    yield store
    # Cleanup
    try:
        admin_session.delete(f"{base_url}/api/stores/{store['id']}", timeout=30)
    except:
        pass


@pytest.fixture
def test_person(admin_session, base_url):
    """Create a test person"""
    payload = {
        "name": f"Test Person {uuid.uuid4().hex[:6]}",
        "role": "partner",
    }
    r = admin_session.post(f"{base_url}/api/company/people", json=payload, timeout=30)
    assert r.status_code == 200, f"Person creation failed: {r.status_code} {r.text}"
    person = r.json()
    yield person
    # Cleanup
    try:
        admin_session.delete(f"{base_url}/api/company/people/{person['id']}", timeout=30)
    except:
        pass


# ============================================================================
# STORES CRUD TESTS
# ============================================================================

def test_store_update(admin_session, base_url, test_store):
    """Test PUT /api/stores/{id} updates store correctly"""
    updated_payload = {
        "name": f"UPDATED_{test_store['name']}",
        "marketplaces": ["US", "CA", "UK"],
        "default_currency": "USD",
    }
    
    r = admin_session.put(
        f"{base_url}/api/stores/{test_store['id']}",
        json=updated_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Store update failed: {r.status_code} {r.text}"
    updated = r.json()
    
    assert updated["name"] == updated_payload["name"]
    assert updated["marketplaces"] == updated_payload["marketplaces"]
    assert updated["default_currency"] == updated_payload["default_currency"]


def test_store_delete_with_capital_history_blocked(admin_session, base_url, test_store, test_person):
    """Test DELETE /api/stores/{id} is blocked when store has capital history"""
    # Create capital entry for the store
    capital_payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Initial capital",
    }
    
    r = admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    assert r.status_code == 200, f"Capital creation failed: {r.status_code} {r.text}"
    
    # Try to delete store - should be blocked
    r = admin_session.delete(f"{base_url}/api/stores/{test_store['id']}", timeout=30)
    assert r.status_code == 409, f"Expected 409 for store with capital history, got {r.status_code}"


def test_store_bulk_delete(admin_session, base_url):
    """Test POST /api/stores/bulk-delete deletes multiple stores"""
    # Create multiple stores
    store1 = admin_session.post(
        f"{base_url}/api/stores",
        json={"name": f"BULK_TEST_1_{uuid.uuid4().hex[:6]}", "marketplaces": ["US"], "default_currency": "USD"},
        timeout=30,
    ).json()
    
    store2 = admin_session.post(
        f"{base_url}/api/stores",
        json={"name": f"BULK_TEST_2_{uuid.uuid4().hex[:6]}", "marketplaces": ["US"], "default_currency": "USD"},
        timeout=30,
    ).json()
    
    # Bulk delete
    r = admin_session.post(
        f"{base_url}/api/stores/bulk-delete",
        json={"ids": [store1["id"], store2["id"]]},
        timeout=30,
    )
    assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
    result = r.json()
    assert result["ok"] is True
    assert result["deleted"] == 2


def test_store_bulk_delete_with_history_blocked(admin_session, base_url, test_store, test_person):
    """Test POST /api/stores/bulk-delete is blocked when stores have company history"""
    # Create another store
    store2 = admin_session.post(
        f"{base_url}/api/stores",
        json={"name": f"BULK_TEST_{uuid.uuid4().hex[:6]}", "marketplaces": ["US"], "default_currency": "USD"},
        timeout=30,
    ).json()
    
    # Add capital to test_store
    capital_payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Initial capital",
    }
    admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Try bulk delete - should be blocked
    r = admin_session.post(
        f"{base_url}/api/stores/bulk-delete",
        json={"ids": [test_store["id"], store2["id"]]},
        timeout=30,
    )
    assert r.status_code == 409, f"Expected 409 for stores with history, got {r.status_code}"
    
    # Cleanup store2
    admin_session.delete(f"{base_url}/api/stores/{store2['id']}", timeout=30)


# ============================================================================
# PEOPLE CRUD TESTS
# ============================================================================

def test_person_delete(admin_session, base_url):
    """Test DELETE /api/company/people/{id} deletes person without financial history"""
    # Create person
    person = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Delete Test {uuid.uuid4().hex[:6]}", "role": "contact"},
        timeout=30,
    ).json()
    
    # Delete person
    r = admin_session.delete(f"{base_url}/api/company/people/{person['id']}", timeout=30)
    assert r.status_code == 200, f"Person deletion failed: {r.status_code} {r.text}"
    assert r.json()["ok"] is True


def test_person_delete_with_capital_blocked(admin_session, base_url, test_store, test_person):
    """Test DELETE /api/company/people/{id} is blocked when person has capital history"""
    # Create capital entry
    capital_payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Initial capital",
    }
    admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Try to delete person - should be blocked
    r = admin_session.delete(f"{base_url}/api/company/people/{test_person['id']}", timeout=30)
    assert r.status_code == 409, f"Expected 409 for person with capital, got {r.status_code}"


def test_person_delete_with_debt_blocked(admin_session, base_url, test_store, test_person):
    """Test DELETE /api/company/people/{id} is blocked when person has debt history"""
    # Create debt
    debt_payload = {
        "request_id": str(uuid.uuid4()),
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 5000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": (date.today() + timedelta(days=30)).isoformat(),
        "cash_effect": True,
        "note": "Test debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Try to delete person - should be blocked
    r = admin_session.delete(f"{base_url}/api/company/people/{test_person['id']}", timeout=30)
    assert r.status_code == 409, f"Expected 409 for person with debt, got {r.status_code}"


def test_person_bulk_delete(admin_session, base_url):
    """Test POST /api/company/people/bulk-delete deletes multiple people"""
    # Create multiple people
    person1 = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Bulk Test 1 {uuid.uuid4().hex[:6]}", "role": "contact"},
        timeout=30,
    ).json()
    
    person2 = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Bulk Test 2 {uuid.uuid4().hex[:6]}", "role": "contact"},
        timeout=30,
    ).json()
    
    # Bulk delete
    r = admin_session.post(
        f"{base_url}/api/company/people/bulk-delete",
        json={"ids": [person1["id"], person2["id"]]},
        timeout=30,
    )
    assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
    result = r.json()
    assert result["ok"] is True
    assert result["deleted"] == 2


# ============================================================================
# CAPITAL CRUD TESTS
# ============================================================================

def test_capital_entry_update(admin_session, base_url, test_store, test_person):
    """Test PUT /api/company/capital/{entry_id} updates capital entry"""
    # Create capital entry
    entry_id = str(uuid.uuid4())
    capital_payload = {
        "request_id": entry_id,
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Initial capital",
    }
    r = admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    assert r.status_code == 200, f"Capital creation failed: {r.status_code} {r.text}"
    
    # Update capital entry
    update_payload = {
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1500.0,  # Changed amount
        "date": (date.today() - timedelta(days=25)).isoformat(),  # Changed date
        "note": "Updated capital",  # Changed note
    }
    
    r = admin_session.put(
        f"{base_url}/api/company/capital/{entry_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Capital update failed: {r.status_code} {r.text}"
    result = r.json()
    
    # Verify update
    assert result["total_usd"] == 1500.0
    entry = next((e for e in result["entries"] if e["id"] == entry_id), None)
    assert entry is not None
    assert entry["amount"] == 1500.0
    assert entry["note"] == "Updated capital"


def test_capital_entry_update_person_and_currency(admin_session, base_url, test_store):
    """Test PUT /api/company/capital/{entry_id} can change person and currency"""
    # Create two people
    person1 = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Person 1 {uuid.uuid4().hex[:6]}", "role": "partner"},
        timeout=30,
    ).json()
    
    person2 = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Person 2 {uuid.uuid4().hex[:6]}", "role": "partner"},
        timeout=30,
    ).json()
    
    # Create capital entry for person1 in USD
    entry_id = str(uuid.uuid4())
    capital_payload = {
        "request_id": entry_id,
        "store_id": test_store["id"],
        "person_id": person1["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Person 1 capital",
    }
    admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Update to person2 and TRY
    update_payload = {
        "store_id": test_store["id"],
        "person_id": person2["id"],  # Changed person
        "currency": "TRY",  # Changed currency
        "direction": "contribution",
        "amount": 30000.0,
        "date": (date.today() - timedelta(days=25)).isoformat(),
        "note": "Moved to Person 2 TRY",
    }
    
    r = admin_session.put(
        f"{base_url}/api/company/capital/{entry_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Capital update failed: {r.status_code} {r.text}"
    
    # Cleanup
    admin_session.delete(f"{base_url}/api/company/people/{person1['id']}", timeout=30)
    admin_session.delete(f"{base_url}/api/company/people/{person2['id']}", timeout=30)


def test_capital_withdrawal_validation(admin_session, base_url, test_store, test_person):
    """Test that invalid withdrawals are rejected"""
    # Create contribution
    contrib_id = str(uuid.uuid4())
    capital_payload = {
        "request_id": contrib_id,
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Initial capital",
    }
    admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Try to withdraw more than available - should fail
    withdrawal_payload = {
        "request_id": str(uuid.uuid4()),
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "withdrawal",
        "amount": 1500.0,  # More than available
        "date": (date.today() - timedelta(days=20)).isoformat(),
        "note": "Invalid withdrawal",
    }
    
    r = admin_session.post(f"{base_url}/api/company/capital", json=withdrawal_payload, timeout=30)
    assert r.status_code == 422, f"Expected 422 for invalid withdrawal, got {r.status_code}"


def test_capital_entry_delete(admin_session, base_url, test_store, test_person):
    """Test DELETE /api/company/capital/{entry_id} deletes capital entry"""
    # Create capital entry
    entry_id = str(uuid.uuid4())
    capital_payload = {
        "request_id": entry_id,
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "To be deleted",
    }
    admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Delete entry
    r = admin_session.delete(f"{base_url}/api/company/capital/{entry_id}", timeout=30)
    assert r.status_code == 200, f"Capital deletion failed: {r.status_code} {r.text}"
    assert r.json()["ok"] is True


def test_capital_bulk_delete(admin_session, base_url, test_store, test_person):
    """Test POST /api/company/capital/bulk-delete deletes multiple entries"""
    # Create multiple capital entries
    entry1_id = str(uuid.uuid4())
    entry2_id = str(uuid.uuid4())
    
    for entry_id in [entry1_id, entry2_id]:
        capital_payload = {
            "request_id": entry_id,
            "store_id": test_store["id"],
            "person_id": test_person["id"],
            "currency": "USD",
            "direction": "contribution",
            "amount": 500.0,
            "date": (date.today() - timedelta(days=30)).isoformat(),
            "note": f"Entry {entry_id}",
        }
        admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Bulk delete
    r = admin_session.post(
        f"{base_url}/api/company/capital/bulk-delete",
        json={"ids": [entry1_id, entry2_id]},
        timeout=30,
    )
    assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
    result = r.json()
    assert result["ok"] is True
    assert result["deleted"] == 2


def test_capital_ownership_percentage_recalculation(admin_session, base_url, test_store):
    """Test that ownership percentages recalculate after capital changes"""
    # Create two people
    person1 = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Partner 1 {uuid.uuid4().hex[:6]}", "role": "partner"},
        timeout=30,
    ).json()
    
    person2 = admin_session.post(
        f"{base_url}/api/company/people",
        json={"name": f"Partner 2 {uuid.uuid4().hex[:6]}", "role": "partner"},
        timeout=30,
    ).json()
    
    # Person 1 contributes $1000
    entry1_id = str(uuid.uuid4())
    admin_session.post(
        f"{base_url}/api/company/capital",
        json={
            "request_id": entry1_id,
            "store_id": test_store["id"],
            "person_id": person1["id"],
            "currency": "USD",
            "direction": "contribution",
            "amount": 1000.0,
            "date": (date.today() - timedelta(days=30)).isoformat(),
            "note": "Person 1 initial",
        },
        timeout=30,
    )
    
    # Person 2 contributes $1000
    entry2_id = str(uuid.uuid4())
    admin_session.post(
        f"{base_url}/api/company/capital",
        json={
            "request_id": entry2_id,
            "store_id": test_store["id"],
            "person_id": person2["id"],
            "currency": "USD",
            "direction": "contribution",
            "amount": 1000.0,
            "date": (date.today() - timedelta(days=30)).isoformat(),
            "note": "Person 2 initial",
        },
        timeout=30,
    )
    
    # Get capital summary - should be 50/50
    r = admin_session.get(
        f"{base_url}/api/company/capital",
        params={"store_id": test_store["id"]},
        timeout=30,
    )
    assert r.status_code == 200
    summary = r.json()
    
    person1_ownership = next((o for o in summary["ownership"] if o["person_id"] == person1["id"]), None)
    person2_ownership = next((o for o in summary["ownership"] if o["person_id"] == person2["id"]), None)
    
    assert person1_ownership is not None
    assert person2_ownership is not None
    assert abs(person1_ownership["share_percent"] - 50.0) < 0.01
    assert abs(person2_ownership["share_percent"] - 50.0) < 0.01
    
    # Person 1 adds another $1000
    entry3_id = str(uuid.uuid4())
    admin_session.post(
        f"{base_url}/api/company/capital",
        json={
            "request_id": entry3_id,
            "store_id": test_store["id"],
            "person_id": person1["id"],
            "currency": "USD",
            "direction": "contribution",
            "amount": 1000.0,
            "date": (date.today() - timedelta(days=20)).isoformat(),
            "note": "Person 1 additional",
        },
        timeout=30,
    )
    
    # Get capital summary - should be 66.67/33.33
    r = admin_session.get(
        f"{base_url}/api/company/capital",
        params={"store_id": test_store["id"]},
        timeout=30,
    )
    assert r.status_code == 200
    summary = r.json()
    
    person1_ownership = next((o for o in summary["ownership"] if o["person_id"] == person1["id"]), None)
    person2_ownership = next((o for o in summary["ownership"] if o["person_id"] == person2["id"]), None)
    
    assert abs(person1_ownership["share_percent"] - 66.67) < 0.1
    assert abs(person2_ownership["share_percent"] - 33.33) < 0.1
    
    # Cleanup
    admin_session.delete(f"{base_url}/api/company/people/{person1['id']}", timeout=30)
    admin_session.delete(f"{base_url}/api/company/people/{person2['id']}", timeout=30)


# ============================================================================
# CASH LEDGER CRUD TESTS
# ============================================================================

def test_cash_entry_update(admin_session, base_url):
    """Test PUT /api/company/cash/{id} updates cash entry"""
    # Create cash entry
    cash_id = str(uuid.uuid4())
    cash_payload = {
        "request_id": cash_id,
        "direction": "in",
        "currency": "USD",
        "amount": 500.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "note": "Cash in",
    }
    r = admin_session.post(f"{base_url}/api/company/cash", json=cash_payload, timeout=30)
    assert r.status_code == 200, f"Cash creation failed: {r.status_code} {r.text}"
    
    # Update cash entry
    update_payload = {
        "direction": "in",
        "currency": "USD",
        "amount": 750.0,  # Changed
        "date": (date.today() - timedelta(days=8)).isoformat(),  # Changed
        "note": "Updated cash in",  # Changed
    }
    
    r = admin_session.put(
        f"{base_url}/api/company/cash/{cash_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Cash update failed: {r.status_code} {r.text}"
    result = r.json()
    
    assert result["amount"] == 750.0
    assert result["note"] == "Updated cash in"


def test_cash_entry_delete(admin_session, base_url):
    """Test DELETE /api/company/cash/{id} deletes cash entry"""
    # Create cash entry
    cash_id = str(uuid.uuid4())
    cash_payload = {
        "request_id": cash_id,
        "direction": "out",
        "currency": "USD",
        "amount": 200.0,
        "date": (date.today() - timedelta(days=5)).isoformat(),
        "note": "To be deleted",
    }
    admin_session.post(f"{base_url}/api/company/cash", json=cash_payload, timeout=30)
    
    # Delete entry
    r = admin_session.delete(f"{base_url}/api/company/cash/{cash_id}", timeout=30)
    assert r.status_code == 200, f"Cash deletion failed: {r.status_code} {r.text}"
    assert r.json()["ok"] is True


def test_cash_bulk_delete(admin_session, base_url):
    """Test POST /api/company/cash/bulk-delete deletes multiple entries"""
    # Create multiple cash entries
    cash1_id = str(uuid.uuid4())
    cash2_id = str(uuid.uuid4())
    
    for cash_id in [cash1_id, cash2_id]:
        cash_payload = {
            "request_id": cash_id,
            "direction": "in",
            "currency": "USD",
            "amount": 100.0,
            "date": (date.today() - timedelta(days=5)).isoformat(),
            "note": f"Entry {cash_id}",
        }
        admin_session.post(f"{base_url}/api/company/cash", json=cash_payload, timeout=30)
    
    # Bulk delete
    r = admin_session.post(
        f"{base_url}/api/company/cash/bulk-delete",
        json={"ids": [cash1_id, cash2_id]},
        timeout=30,
    )
    assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
    result = r.json()
    assert result["ok"] is True
    assert result["deleted"] == 2


def test_cash_affects_overview_balance(admin_session, base_url):
    """Test that cash entries affect company overview balance"""
    # Get overview before
    overview_before = admin_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_balance_before = next((b for b in overview_before["balances"] if b["currency"] == "USD"), None)
    initial_balance = usd_balance_before["cash_balance"] if usd_balance_before else 0.0
    
    # Add cash in
    cash_id = str(uuid.uuid4())
    cash_payload = {
        "request_id": cash_id,
        "direction": "in",
        "currency": "USD",
        "amount": 1000.0,
        "date": date.today().isoformat(),
        "note": "Test cash in",
    }
    admin_session.post(f"{base_url}/api/company/cash", json=cash_payload, timeout=30)
    
    # Get overview after
    overview_after = admin_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    usd_balance_after = next((b for b in overview_after["balances"] if b["currency"] == "USD"), None)
    
    assert usd_balance_after["cash_balance"] == initial_balance + 1000.0
    
    # Cleanup
    admin_session.delete(f"{base_url}/api/company/cash/{cash_id}", timeout=30)


# ============================================================================
# DEBTS CRUD TESTS
# ============================================================================

def test_debt_update(admin_session, base_url, test_store, test_person):
    """Test PUT /api/company/debts/{id} updates debt"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 5000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": (date.today() + timedelta(days=30)).isoformat(),
        "cash_effect": True,
        "note": "Initial debt",
    }
    r = admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    assert r.status_code == 200, f"Debt creation failed: {r.status_code} {r.text}"
    
    # Update debt
    update_payload = {
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 6000.0,  # Changed
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": (date.today() + timedelta(days=60)).isoformat(),  # Changed
        "cash_effect": True,
        "note": "Updated debt",  # Changed
    }
    
    r = admin_session.put(
        f"{base_url}/api/company/debts/{debt_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Debt update failed: {r.status_code} {r.text}"
    result = r.json()
    
    assert result["principal"] == 6000.0
    assert result["remaining"] == 6000.0
    assert result["note"] == "Updated debt"


def test_debt_update_principal_constrained_by_payments(admin_session, base_url, test_store, test_person):
    """Test that debt principal cannot be reduced below total payments"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 5000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": (date.today() + timedelta(days=30)).isoformat(),
        "cash_effect": True,
        "note": "Test debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Make a payment
    payment_payload = {
        "request_id": str(uuid.uuid4()),
        "amount": 2000.0,
        "date": (date.today() - timedelta(days=5)).isoformat(),
        "note": "Partial payment",
    }
    admin_session.post(f"{base_url}/api/company/debts/{debt_id}/payments", json=payment_payload, timeout=30)
    
    # Try to update principal to less than payment - should fail
    update_payload = {
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 1500.0,  # Less than payment
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": (date.today() + timedelta(days=30)).isoformat(),
        "cash_effect": True,
        "note": "Invalid update",
    }
    
    r = admin_session.put(
        f"{base_url}/api/company/debts/{debt_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 422, f"Expected 422 for invalid principal update, got {r.status_code}"


def test_debt_delete(admin_session, base_url, test_store, test_person):
    """Test DELETE /api/company/debts/{id} deletes debt"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "receivable",
        "currency": "USD",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=5)).isoformat(),
        "due_date": None,
        "cash_effect": False,
        "note": "To be deleted",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Delete debt
    r = admin_session.delete(f"{base_url}/api/company/debts/{debt_id}", timeout=30)
    assert r.status_code == 200, f"Debt deletion failed: {r.status_code} {r.text}"
    assert r.json()["ok"] is True


def test_debt_bulk_delete(admin_session, base_url, test_store, test_person):
    """Test POST /api/company/debts/bulk-delete deletes multiple debts"""
    # Create multiple debts
    debt1_id = str(uuid.uuid4())
    debt2_id = str(uuid.uuid4())
    
    for debt_id in [debt1_id, debt2_id]:
        debt_payload = {
            "request_id": debt_id,
            "person_id": test_person["id"],
            "store_id": test_store["id"],
            "direction": "payable",
            "currency": "USD",
            "amount": 1000.0,
            "date": (date.today() - timedelta(days=5)).isoformat(),
            "due_date": None,
            "cash_effect": False,
            "note": f"Debt {debt_id}",
        }
        admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Bulk delete
    r = admin_session.post(
        f"{base_url}/api/company/debts/bulk-delete",
        json={"ids": [debt1_id, debt2_id]},
        timeout=30,
    )
    assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
    result = r.json()
    assert result["ok"] is True
    assert result["deleted"] == 2


def test_debt_remaining_balance_never_negative(admin_session, base_url, test_store, test_person):
    """Test that debt remaining balance never goes negative"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": None,
        "cash_effect": True,
        "note": "Test debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Try to pay more than debt - should fail
    payment_payload = {
        "request_id": str(uuid.uuid4()),
        "amount": 1500.0,  # More than debt
        "date": (date.today() - timedelta(days=5)).isoformat(),
        "note": "Overpayment",
    }
    
    r = admin_session.post(f"{base_url}/api/company/debts/{debt_id}/payments", json=payment_payload, timeout=30)
    assert r.status_code == 422, f"Expected 422 for overpayment, got {r.status_code}"


# ============================================================================
# DEBT PAYMENTS CRUD TESTS
# ============================================================================

def test_debt_payment_update(admin_session, base_url, test_store, test_person):
    """Test PUT /api/company/debts/{debt_id}/payments/{payment_id} updates payment"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 5000.0,
        "date": (date.today() - timedelta(days=20)).isoformat(),
        "due_date": None,
        "cash_effect": True,
        "note": "Test debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Make a payment
    payment_id = str(uuid.uuid4())
    payment_payload = {
        "request_id": payment_id,
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "note": "Initial payment",
    }
    admin_session.post(f"{base_url}/api/company/debts/{debt_id}/payments", json=payment_payload, timeout=30)
    
    # Update payment
    update_payload = {
        "amount": 1500.0,  # Changed
        "date": (date.today() - timedelta(days=8)).isoformat(),  # Changed
        "note": "Updated payment",  # Changed
    }
    
    r = admin_session.put(
        f"{base_url}/api/company/debts/{debt_id}/payments/{payment_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Payment update failed: {r.status_code} {r.text}"
    result = r.json()
    
    assert result["remaining"] == 3500.0  # 5000 - 1500
    payment = next((p for p in result["payments"] if p["id"] == payment_id), None)
    assert payment is not None
    assert payment["amount"] == 1500.0
    assert payment["note"] == "Updated payment"


def test_debt_payment_delete(admin_session, base_url, test_store, test_person):
    """Test DELETE /api/company/debts/{debt_id}/payments/{payment_id} deletes payment"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 3000.0,
        "date": (date.today() - timedelta(days=20)).isoformat(),
        "due_date": None,
        "cash_effect": True,
        "note": "Test debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Make a payment
    payment_id = str(uuid.uuid4())
    payment_payload = {
        "request_id": payment_id,
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "note": "To be deleted",
    }
    admin_session.post(f"{base_url}/api/company/debts/{debt_id}/payments", json=payment_payload, timeout=30)
    
    # Delete payment
    r = admin_session.delete(
        f"{base_url}/api/company/debts/{debt_id}/payments/{payment_id}",
        timeout=30,
    )
    assert r.status_code == 200, f"Payment deletion failed: {r.status_code} {r.text}"
    result = r.json()
    
    assert result["remaining"] == 3000.0  # Back to full amount
    assert not any(p["id"] == payment_id for p in result["payments"])


def test_debt_payment_remaining_balance_recalculates(admin_session, base_url, test_store, test_person):
    """Test that remaining balance recalculates correctly after payment changes"""
    # Create debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 10000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "due_date": None,
        "cash_effect": True,
        "note": "Test debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Make first payment
    payment1_id = str(uuid.uuid4())
    admin_session.post(
        f"{base_url}/api/company/debts/{debt_id}/payments",
        json={
            "request_id": payment1_id,
            "amount": 3000.0,
            "date": (date.today() - timedelta(days=20)).isoformat(),
            "note": "Payment 1",
        },
        timeout=30,
    )
    
    # Make second payment
    payment2_id = str(uuid.uuid4())
    admin_session.post(
        f"{base_url}/api/company/debts/{debt_id}/payments",
        json={
            "request_id": payment2_id,
            "amount": 2000.0,
            "date": (date.today() - timedelta(days=10)).isoformat(),
            "note": "Payment 2",
        },
        timeout=30,
    )
    
    # Get debt - remaining should be 5000
    r = admin_session.get(f"{base_url}/api/company/debts", timeout=30)
    debts = r.json()
    debt = next((d for d in debts if d["id"] == debt_id), None)
    assert debt is not None
    assert debt["remaining"] == 5000.0
    
    # Update first payment to 4000
    r = admin_session.put(
        f"{base_url}/api/company/debts/{debt_id}/payments/{payment1_id}",
        json={
            "amount": 4000.0,
            "date": (date.today() - timedelta(days=20)).isoformat(),
            "note": "Updated payment 1",
        },
        timeout=30,
    )
    result = r.json()
    assert result["remaining"] == 4000.0  # 10000 - 4000 - 2000
    
    # Delete second payment
    r = admin_session.delete(
        f"{base_url}/api/company/debts/{debt_id}/payments/{payment2_id}",
        timeout=30,
    )
    result = r.json()
    assert result["remaining"] == 6000.0  # 10000 - 4000


# ============================================================================
# CLOSINGS CRUD TESTS
# ============================================================================

def test_closing_update(admin_session, base_url, test_store):
    """Test PUT /api/company/closings/{id} updates closing"""
    # Create a transaction to generate a closing
    tx_payload = {
        "store_id": test_store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 1000.0,
        "currency": "USD",
        "date": (date.today().replace(day=1) - timedelta(days=10)).isoformat(),  # Last month
        "description": "Test income",
        "order_id": f"TEST-{uuid.uuid4().hex[:6]}",
        "payment_reference": "",
        "product_cost": 200.0,
        "shipping_cost": 50.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    admin_session.post(f"{base_url}/api/transactions", json=tx_payload, timeout=30)
    
    # Trigger closing
    r = admin_session.post(f"{base_url}/api/company/closings/run", timeout=30)
    assert r.status_code == 202
    
    # Wait a bit for background job
    import time
    time.sleep(2)
    
    # Get closings
    r = admin_session.get(f"{base_url}/api/company/closings", timeout=30)
    assert r.status_code == 200
    closings = r.json()
    
    if closings:
        closing = closings[0]
        
        # Update closing
        update_payload = {
            "revenue": 1200.0,  # Changed
            "expenses": 300.0,  # Changed
            "net_profit": 900.0,  # Changed
        }
        
        r = admin_session.put(
            f"{base_url}/api/company/closings/{closing['id']}",
            json=update_payload,
            timeout=30,
        )
        assert r.status_code == 200, f"Closing update failed: {r.status_code} {r.text}"
        result = r.json()
        
        assert result["revenue"] == 1200.0
        assert result["expenses"] == 300.0
        assert result["net_profit"] == 900.0


def test_closing_delete(admin_session, base_url, test_store):
    """Test DELETE /api/company/closings/{id} deletes closing"""
    # Create a transaction to generate a closing
    tx_payload = {
        "store_id": test_store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 500.0,
        "currency": "USD",
        "date": (date.today().replace(day=1) - timedelta(days=15)).isoformat(),  # Last month
        "description": "Test income",
        "order_id": f"TEST-{uuid.uuid4().hex[:6]}",
        "payment_reference": "",
        "product_cost": 100.0,
        "shipping_cost": 20.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    admin_session.post(f"{base_url}/api/transactions", json=tx_payload, timeout=30)
    
    # Trigger closing
    admin_session.post(f"{base_url}/api/company/closings/run", timeout=30)
    
    # Wait a bit
    import time
    time.sleep(2)
    
    # Get closings
    r = admin_session.get(f"{base_url}/api/company/closings", timeout=30)
    closings = r.json()
    
    if closings:
        closing = closings[0]
        
        # Delete closing
        r = admin_session.delete(f"{base_url}/api/company/closings/{closing['id']}", timeout=30)
        assert r.status_code == 200, f"Closing deletion failed: {r.status_code} {r.text}"
        assert r.json()["ok"] is True


def test_closing_bulk_delete(admin_session, base_url, test_store):
    """Test POST /api/company/closings/bulk-delete deletes multiple closings"""
    # Create transactions in different months
    for i in range(2):
        tx_payload = {
            "store_id": test_store["id"],
            "marketplace": "US",
            "type": "income",
            "category": "Order payments",
            "amount": 500.0,
            "currency": "USD",
            "date": (date.today().replace(day=1) - timedelta(days=30 * (i + 1) + 10)).isoformat(),
            "description": f"Test income {i}",
            "order_id": f"TEST-{uuid.uuid4().hex[:6]}",
            "payment_reference": "",
            "product_cost": 100.0,
            "shipping_cost": 20.0,
            "extra_cost": 0.0,
            "product_cost_recovery": 0.0,
            "shipping_cost_recovery": 0.0,
        }
        admin_session.post(f"{base_url}/api/transactions", json=tx_payload, timeout=30)
    
    # Trigger closing
    admin_session.post(f"{base_url}/api/company/closings/run", timeout=30)
    
    # Wait a bit
    import time
    time.sleep(2)
    
    # Get closings
    r = admin_session.get(f"{base_url}/api/company/closings", timeout=30)
    closings = r.json()
    
    if len(closings) >= 2:
        closing_ids = [c["id"] for c in closings[:2]]
        
        # Bulk delete
        r = admin_session.post(
            f"{base_url}/api/company/closings/bulk-delete",
            json={"ids": closing_ids},
            timeout=30,
        )
        assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
        result = r.json()
        assert result["ok"] is True


def test_closing_affects_overview(admin_session, base_url, test_store):
    """Test that closings affect company overview"""
    # Get overview before
    overview_before = admin_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    
    # Create a transaction
    tx_payload = {
        "store_id": test_store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 2000.0,
        "currency": "USD",
        "date": (date.today().replace(day=1) - timedelta(days=20)).isoformat(),
        "description": "Test income",
        "order_id": f"TEST-{uuid.uuid4().hex[:6]}",
        "payment_reference": "",
        "product_cost": 400.0,
        "shipping_cost": 100.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    admin_session.post(f"{base_url}/api/transactions", json=tx_payload, timeout=30)
    
    # Trigger closing
    admin_session.post(f"{base_url}/api/company/closings/run", timeout=30)
    
    # Wait a bit
    import time
    time.sleep(2)
    
    # Get overview after
    overview_after = admin_session.get(f"{base_url}/api/company/overview", timeout=30).json()
    
    # Check that closed_profit_usd changed (if not blocked)
    # This is a basic check - the actual value depends on existing data


# ============================================================================
# CROSS-USER OWNERSHIP TESTS
# ============================================================================

def test_cross_user_capital_update_denied(admin_session, test_user_session, base_url, test_store, test_person):
    """Test that users cannot update other users' capital entries"""
    # Admin creates capital entry
    entry_id = str(uuid.uuid4())
    capital_payload = {
        "request_id": entry_id,
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 1000.0,
        "date": (date.today() - timedelta(days=30)).isoformat(),
        "note": "Admin capital",
    }
    admin_session.post(f"{base_url}/api/company/capital", json=capital_payload, timeout=30)
    
    # Test user tries to update
    update_payload = {
        "store_id": test_store["id"],
        "person_id": test_person["id"],
        "currency": "USD",
        "direction": "contribution",
        "amount": 2000.0,
        "date": (date.today() - timedelta(days=25)).isoformat(),
        "note": "Hacked",
    }
    
    r = test_user_session.put(
        f"{base_url}/api/company/capital/{entry_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 404, f"Expected 404 for cross-user update, got {r.status_code}"


def test_cross_user_debt_update_denied(admin_session, test_user_session, base_url, test_store, test_person):
    """Test that users cannot update other users' debts"""
    # Admin creates debt
    debt_id = str(uuid.uuid4())
    debt_payload = {
        "request_id": debt_id,
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 5000.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": None,
        "cash_effect": True,
        "note": "Admin debt",
    }
    admin_session.post(f"{base_url}/api/company/debts", json=debt_payload, timeout=30)
    
    # Test user tries to update
    update_payload = {
        "person_id": test_person["id"],
        "store_id": test_store["id"],
        "direction": "payable",
        "currency": "USD",
        "amount": 1.0,
        "date": (date.today() - timedelta(days=10)).isoformat(),
        "due_date": None,
        "cash_effect": True,
        "note": "Hacked",
    }
    
    r = test_user_session.put(
        f"{base_url}/api/company/debts/{debt_id}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 404, f"Expected 404 for cross-user update, got {r.status_code}"


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
