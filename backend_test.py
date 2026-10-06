#!/usr/bin/env python3
"""
Backend-only verification for transaction update and bulk delete operations.
Tests PUT /api/transactions/{id}, DELETE /api/transactions/{id}, and POST /api/transactions/bulk-delete.
"""
import os
import uuid
from datetime import date, timedelta
from decimal import Decimal

import pytest
import requests


# Backend URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://24b47787-80b4-43f5-a735-d2fdefafd0fa.preview.emergentagent.com")
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
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
    email = f"test_update_{uuid.uuid4().hex[:8]}@example.com"
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
def isolated_store(admin_session, base_url):
    """Create an isolated test store"""
    payload = {
        "name": f"TEST_UPDATE_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US", "CA", "UK"],
        "default_currency": "USD",
    }
    r = admin_session.post(f"{base_url}/api/stores", json=payload, timeout=30)
    assert r.status_code == 200, f"Store creation failed: {r.status_code} {r.text}"
    store = r.json()
    yield store
    # Cleanup
    admin_session.delete(f"{base_url}/api/stores/{store['id']}", timeout=30)


def _tx_payload(store_id, **overrides):
    """Helper to create transaction payload"""
    payload = {
        "store_id": store_id,
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 100.0,
        "currency": "USD",
        "date": date.today().isoformat(),
        "description": "Test transaction",
        "order_id": f"TEST-{uuid.uuid4().hex[:6]}",
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    payload.update(overrides)
    return payload


def _create_tx(session, base_url, payload):
    """Helper to create a transaction"""
    r = session.post(f"{base_url}/api/transactions", json=payload, timeout=30)
    assert r.status_code == 200, f"Transaction creation failed: {r.status_code} {r.text}"
    return r.json()


# ============================================================================
# Test 1: Full transaction update with all editable fields
# ============================================================================
def test_transaction_full_update_all_fields(admin_session, base_url, isolated_store):
    """Test PUT /api/transactions/{id} can update all editable fields"""
    # Create an income transaction
    original = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            marketplace="US",
            amount=100.0,
            date="2025-01-15",
            description="Original description",
            order_id="ORIG-001",
            product_cost=20.0,
            shipping_cost=5.0,
            extra_cost=2.0,
        ),
    )
    
    # Update all editable fields
    updated_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",  # Same marketplace
        "type": "income",
        "category": "Order payments",
        "amount": 150.0,  # Changed
        "currency": "USD",
        "date": "2025-01-20",  # Changed
        "description": "Updated description",  # Changed
        "order_id": "UPDATED-002",  # Changed
        "payment_reference": "",
        "product_cost": 30.0,  # Changed
        "shipping_cost": 8.0,  # Changed
        "extra_cost": 3.0,  # Changed
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{original['id']}",
        json=updated_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Transaction update failed: {r.status_code} {r.text}"
    updated = r.json()
    
    # Verify all fields were updated
    assert updated["amount"] == 150.0, "Amount not updated"
    assert updated["date"] == "2025-01-20", "Date not updated"
    assert updated["description"] == "Updated description", "Description not updated"
    assert updated["order_id"] == "UPDATED-002", "Order ID not updated"
    assert updated["product_cost"] == 30.0, "Product cost not updated"
    assert updated["shipping_cost"] == 8.0, "Shipping cost not updated"
    assert updated["extra_cost"] == 3.0, "Extra cost not updated"
    
    # Verify FX and USD amounts are recalculated
    assert "amount_usd" in updated, "amount_usd missing"
    assert "usd_costs" in updated, "usd_costs missing"
    assert updated["usd_costs"]["product_cost"] == 30.0
    assert updated["usd_costs"]["shipping_cost"] == 8.0
    assert updated["usd_costs"]["extra_cost"] == 3.0


# ============================================================================
# Test 2: Update expense transaction (refund and service fee)
# ============================================================================
def test_transaction_update_expense_types(admin_session, base_url, isolated_store):
    """Test updating refund and service fee transactions"""
    order_id = f"TEST-{uuid.uuid4().hex[:6]}"
    
    # Create a refund
    refund = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            type="expense",
            category="Refunds",
            amount=50.0,
            order_id=order_id,
            product_cost_recovery=10.0,
            shipping_cost_recovery=5.0,
        ),
    )
    
    # Update refund
    updated_refund_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "expense",
        "category": "Refunds",
        "amount": 60.0,  # Changed
        "currency": "USD",
        "date": refund["date"],
        "description": "Updated refund",
        "order_id": order_id,
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 15.0,  # Changed
        "shipping_cost_recovery": 7.0,  # Changed
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{refund['id']}",
        json=updated_refund_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Refund update failed: {r.status_code} {r.text}"
    updated_refund = r.json()
    assert updated_refund["amount"] == 60.0
    assert updated_refund["product_cost_recovery"] == 15.0
    assert updated_refund["shipping_cost_recovery"] == 7.0
    
    # Create a service fee
    fee = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            type="expense",
            category="Service Fees",
            amount=10.0,
            order_id=order_id,
        ),
    )
    
    # Update service fee
    updated_fee_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "expense",
        "category": "Service Fees",
        "amount": 15.0,  # Changed
        "currency": "USD",
        "date": fee["date"],
        "description": "Updated fee",
        "order_id": order_id,
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{fee['id']}",
        json=updated_fee_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Service fee update failed: {r.status_code} {r.text}"
    updated_fee = r.json()
    assert updated_fee["amount"] == 15.0


# ============================================================================
# Test 3: Update payout transaction
# ============================================================================
def test_transaction_update_payout(admin_session, base_url, isolated_store):
    """Test updating payout transactions"""
    # Create a payout
    payout = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            type="payout",
            category="Oluşturuldu",
            amount=100.0,
            order_id="",
            payment_reference="PAY-001",
        ),
    )
    
    # Update payout
    updated_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "payout",
        "category": "Bankada",  # Changed status
        "amount": 120.0,  # Changed
        "currency": "USD",
        "date": payout["date"],
        "description": "Updated payout",
        "order_id": "",
        "payment_reference": "PAY-002",  # Changed
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{payout['id']}",
        json=updated_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Payout update failed: {r.status_code} {r.text}"
    updated = r.json()
    assert updated["amount"] == 120.0
    assert updated["category"] == "Bankada"
    assert updated["payment_reference"] == "PAY-002"


# ============================================================================
# Test 4: Update CAD transaction and verify FX recalculation
# ============================================================================
def test_transaction_update_cad_fx_recalculation(admin_session, base_url, isolated_store):
    """Test updating CAD transaction recalculates FX and USD amounts"""
    # Create a CAD transaction
    test_date = (date.today() - timedelta(days=7)).isoformat()
    cad_tx = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            marketplace="CA",
            currency="CAD",
            amount=100.0,
            date=test_date,
            product_cost=20.0,
        ),
    )
    
    original_fx = cad_tx["fx"]
    original_amount_usd = cad_tx["amount_usd"]
    
    # Update amount
    updated_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "CA",
        "type": "income",
        "category": "Order payments",
        "amount": 150.0,  # Changed
        "currency": "CAD",
        "date": test_date,  # Same date
        "description": "Updated CAD transaction",
        "order_id": cad_tx["order_id"],
        "payment_reference": "",
        "product_cost": 30.0,  # Changed
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{cad_tx['id']}",
        json=updated_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"CAD transaction update failed: {r.status_code} {r.text}"
    updated = r.json()
    
    # Verify FX is recalculated
    assert updated["amount"] == 150.0
    assert updated["currency"] == "CAD"
    assert "amount_usd" in updated
    assert "fx" in updated
    # FX rate should be the same for the same date
    assert updated["fx"]["rate"] == original_fx["rate"]
    # But amount_usd should be different
    assert updated["amount_usd"] != original_amount_usd


# ============================================================================
# Test 5: Validation - Invalid category/type combination
# ============================================================================
def test_transaction_update_invalid_category_type(admin_session, base_url, isolated_store):
    """Test that invalid category/type combinations are rejected"""
    # Create an income transaction
    tx = _create_tx(
        admin_session,
        base_url,
        _tx_payload(isolated_store["id"], amount=100.0),
    )
    
    # Try to update with invalid category for income
    invalid_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Refunds",  # Invalid: Refunds is expense
        "amount": 100.0,
        "currency": "USD",
        "date": tx["date"],
        "description": "",
        "order_id": tx["order_id"],
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{tx['id']}",
        json=invalid_payload,
        timeout=30,
    )
    assert r.status_code == 400, f"Expected 400 for invalid category/type, got {r.status_code}"


# ============================================================================
# Test 6: Validation - Marketplace/currency mismatch
# ============================================================================
def test_transaction_update_marketplace_currency_mismatch(admin_session, base_url, isolated_store):
    """Test that marketplace/currency mismatch is rejected"""
    # Create a US transaction
    tx = _create_tx(
        admin_session,
        base_url,
        _tx_payload(isolated_store["id"], marketplace="US", currency="USD"),
    )
    
    # Try to update with mismatched currency
    invalid_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 100.0,
        "currency": "CAD",  # Invalid: US marketplace requires USD
        "date": tx["date"],
        "description": "",
        "order_id": tx["order_id"],
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{tx['id']}",
        json=invalid_payload,
        timeout=30,
    )
    assert r.status_code == 400, f"Expected 400 for marketplace/currency mismatch, got {r.status_code}"


# ============================================================================
# Test 7: Validation - Future date FX unavailable
# ============================================================================
def test_transaction_update_future_date_rejected(admin_session, base_url, isolated_store):
    """Test that future dates are rejected for FX"""
    # Create a CAD transaction
    test_date = (date.today() - timedelta(days=7)).isoformat()
    tx = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            marketplace="CA",
            currency="CAD",
            date=test_date,
        ),
    )
    
    # Try to update with future date
    future_date = (date.today() + timedelta(days=5)).isoformat()
    invalid_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "CA",
        "type": "income",
        "category": "Order payments",
        "amount": 100.0,
        "currency": "CAD",
        "date": future_date,  # Future date
        "description": "",
        "order_id": tx["order_id"],
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{tx['id']}",
        json=invalid_payload,
        timeout=30,
    )
    assert r.status_code == 422, f"Expected 422 for future date, got {r.status_code}"


# ============================================================================
# Test 8: Cross-user update denied
# ============================================================================
def test_transaction_update_cross_user_denied(admin_session, test_user_session, base_url, isolated_store):
    """Test that users cannot update other users' transactions"""
    # Admin creates a transaction
    tx = _create_tx(
        admin_session,
        base_url,
        _tx_payload(isolated_store["id"], amount=100.0),
    )
    
    # Test user tries to update admin's transaction
    update_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 200.0,
        "currency": "USD",
        "date": tx["date"],
        "description": "Hacked",
        "order_id": tx["order_id"],
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = test_user_session.put(
        f"{base_url}/api/transactions/{tx['id']}",
        json=update_payload,
        timeout=30,
    )
    assert r.status_code == 404, f"Expected 404 for cross-user update, got {r.status_code}"


# ============================================================================
# Test 9: Single transaction deletion
# ============================================================================
def test_transaction_single_delete(admin_session, base_url, isolated_store):
    """Test DELETE /api/transactions/{id} deletes a single transaction"""
    # Create a transaction
    tx = _create_tx(
        admin_session,
        base_url,
        _tx_payload(isolated_store["id"], amount=100.0),
    )
    
    # Delete it
    r = admin_session.delete(f"{base_url}/api/transactions/{tx['id']}", timeout=30)
    assert r.status_code == 200, f"Transaction deletion failed: {r.status_code} {r.text}"
    assert r.json()["ok"] is True
    
    # Verify it's gone
    list_r = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"]},
        timeout=30,
    )
    assert list_r.status_code == 200
    transactions = list_r.json()
    assert not any(t["id"] == tx["id"] for t in transactions), "Transaction still exists after deletion"


# ============================================================================
# Test 10: Bulk transaction deletion
# ============================================================================
def test_transaction_bulk_delete(admin_session, base_url, isolated_store):
    """Test POST /api/transactions/bulk-delete deletes multiple transactions"""
    # Create multiple transactions
    tx1 = _create_tx(admin_session, base_url, _tx_payload(isolated_store["id"], amount=100.0))
    tx2 = _create_tx(admin_session, base_url, _tx_payload(isolated_store["id"], amount=200.0))
    tx3 = _create_tx(admin_session, base_url, _tx_payload(isolated_store["id"], amount=300.0))
    
    # Bulk delete tx1 and tx2
    r = admin_session.post(
        f"{base_url}/api/transactions/bulk-delete",
        json={"ids": [tx1["id"], tx2["id"]]},
        timeout=30,
    )
    assert r.status_code == 200, f"Bulk delete failed: {r.status_code} {r.text}"
    result = r.json()
    assert result["ok"] is True
    assert result["deleted"] == 2, f"Expected 2 deleted, got {result['deleted']}"
    
    # Verify only tx3 remains
    list_r = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"]},
        timeout=30,
    )
    assert list_r.status_code == 200
    transactions = list_r.json()
    remaining_ids = [t["id"] for t in transactions]
    assert tx1["id"] not in remaining_ids, "tx1 still exists"
    assert tx2["id"] not in remaining_ids, "tx2 still exists"
    assert tx3["id"] in remaining_ids, "tx3 was deleted"


# ============================================================================
# Test 11: Cross-user bulk delete denied
# ============================================================================
def test_transaction_bulk_delete_cross_user_denied(admin_session, test_user_session, base_url, isolated_store):
    """Test that users cannot delete other users' transactions via bulk delete"""
    # Admin creates transactions
    tx1 = _create_tx(admin_session, base_url, _tx_payload(isolated_store["id"], amount=100.0))
    tx2 = _create_tx(admin_session, base_url, _tx_payload(isolated_store["id"], amount=200.0))
    
    # Test user tries to bulk delete admin's transactions
    r = test_user_session.post(
        f"{base_url}/api/transactions/bulk-delete",
        json={"ids": [tx1["id"], tx2["id"]]},
        timeout=30,
    )
    assert r.status_code == 404, f"Expected 404 for cross-user bulk delete, got {r.status_code}"
    
    # Verify transactions still exist
    list_r = admin_session.get(
        f"{base_url}/api/transactions",
        params={"store_id": isolated_store["id"]},
        timeout=30,
    )
    assert list_r.status_code == 200
    transactions = list_r.json()
    remaining_ids = [t["id"] for t in transactions]
    assert tx1["id"] in remaining_ids, "tx1 was deleted"
    assert tx2["id"] in remaining_ids, "tx2 was deleted"


# ============================================================================
# Test 12: Payout update affects summary and native balance
# ============================================================================
def test_payout_update_affects_summary(admin_session, base_url, isolated_store):
    """Test that payout updates affect summary and native balance correctly"""
    # Create an income transaction
    income = _create_tx(
        admin_session,
        base_url,
        _tx_payload(isolated_store["id"], amount=1000.0),
    )
    
    # Create a payout
    payout = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            type="payout",
            category="Bankada",
            amount=500.0,
            order_id="",
        ),
    )
    
    # Get summary before update
    summary_before = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "US", "currency": "USD"},
        timeout=30,
    )
    assert summary_before.status_code == 200
    before_data = summary_before.json()
    
    # Update payout amount
    updated_payload = {
        "store_id": isolated_store["id"],
        "marketplace": "US",
        "type": "payout",
        "category": "Bankada",
        "amount": 700.0,  # Changed from 500 to 700
        "currency": "USD",
        "date": payout["date"],
        "description": "",
        "order_id": "",
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }
    
    r = admin_session.put(
        f"{base_url}/api/transactions/{payout['id']}",
        json=updated_payload,
        timeout=30,
    )
    assert r.status_code == 200, f"Payout update failed: {r.status_code} {r.text}"
    
    # Get summary after update
    summary_after = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "US", "currency": "USD"},
        timeout=30,
    )
    assert summary_after.status_code == 200
    after_data = summary_after.json()
    
    # Verify native balance changed
    usd_balance_before = next((b for b in before_data["native_balances"] if b["currency"] == "USD"), None)
    usd_balance_after = next((b for b in after_data["native_balances"] if b["currency"] == "USD"), None)
    
    assert usd_balance_before is not None
    assert usd_balance_after is not None
    
    # Payouts received should increase by 200 (700 - 500)
    assert usd_balance_after["payouts_received"] == usd_balance_before["payouts_received"] + 200.0


# ============================================================================
# Test 13: Payout deletion affects summary
# ============================================================================
def test_payout_deletion_affects_summary(admin_session, base_url, isolated_store):
    """Test that payout deletion affects summary correctly"""
    # Create an income transaction
    income = _create_tx(
        admin_session,
        base_url,
        _tx_payload(isolated_store["id"], amount=1000.0),
    )
    
    # Create a payout
    payout = _create_tx(
        admin_session,
        base_url,
        _tx_payload(
            isolated_store["id"],
            type="payout",
            category="Bankada",
            amount=500.0,
            order_id="",
        ),
    )
    
    # Get summary before deletion
    summary_before = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "US", "currency": "USD"},
        timeout=30,
    )
    assert summary_before.status_code == 200
    before_data = summary_before.json()
    
    # Delete payout
    r = admin_session.delete(f"{base_url}/api/transactions/{payout['id']}", timeout=30)
    assert r.status_code == 200
    
    # Get summary after deletion
    summary_after = admin_session.get(
        f"{base_url}/api/dashboard/summary",
        params={"store_id": isolated_store["id"], "marketplace": "US", "currency": "USD"},
        timeout=30,
    )
    assert summary_after.status_code == 200
    after_data = summary_after.json()
    
    # Verify native balance changed
    usd_balance_before = next((b for b in before_data["native_balances"] if b["currency"] == "USD"), None)
    usd_balance_after = next((b for b in after_data["native_balances"] if b["currency"] == "USD"), None)
    
    assert usd_balance_before is not None
    assert usd_balance_after is not None
    
    # Payouts received should decrease by 500
    assert usd_balance_after["payouts_received"] == usd_balance_before["payouts_received"] - 500.0


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
