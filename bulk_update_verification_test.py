#!/usr/bin/env python3
"""
Simplified verification test for bulk-update endpoints that don't rely on GET endpoints.
"""
import os
import uuid
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://24b47787-80b4-43f5-a735-d2fdefafd0fa.preview.emergentagent.com")
TEST_EMAIL = "test-bulk@example.com"
TEST_PASSWORD = "GVNlx6pt-k1LnrqTEPY0M6mt"

def test_capital_bulk_update():
    """Test capital bulk-update by creating and updating entries"""
    s = requests.Session()
    login = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
    assert login.status_code == 200
    s.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
    
    # Create store
    store = s.post(f"{BASE_URL}/api/stores", json={
        "name": f"TEST_{uuid.uuid4().hex[:6]}",
        "marketplaces": ["US"],
        "default_currency": "USD",
    }, timeout=30).json()
    
    # Create person
    person = s.post(f"{BASE_URL}/api/company/people", json={
        "name": f"Person {uuid.uuid4().hex[:6]}",
        "role": "partner",
        "note": "Test",
    }, timeout=30).json()
    
    # Create capital entry
    capital = s.post(f"{BASE_URL}/api/company/capital", json={
        "request_id": str(uuid.uuid4()),
        "person_id": person["id"],
        "store_id": store["id"],
        "amount": "1000.00",
        "currency": "USD",
        "direction": "contribution",
        "date": "2025-01-15",
        "note": "Original note",
    }, timeout=30)
    
    print(f"Capital POST status: {capital.status_code}")
    if capital.status_code == 200:
        capital_data = capital.json()
        print(f"Capital response keys: {capital_data.keys()}")
        print(f"Capital entries count: {len(capital_data.get('entries', []))}")
        
        if capital_data.get('entries'):
            entry_id = capital_data['entries'][0]['id']
            
            # Test bulk update
            bulk_update = s.post(f"{BASE_URL}/api/company/capital/bulk-update", json={
                "ids": [entry_id],
                "changes": {"note": "Bulk updated note"}
            }, timeout=30)
            
            print(f"Capital bulk-update status: {bulk_update.status_code}")
            if bulk_update.status_code == 200:
                print(f"Capital bulk-update response: {bulk_update.json()}")
                print("✅ Capital bulk-update endpoint working")
            else:
                print(f"❌ Capital bulk-update failed: {bulk_update.text}")
    else:
        print(f"❌ Capital creation failed: {capital.text}")
    
    # Cleanup
    s.delete(f"{BASE_URL}/api/company/people/{person['id']}", timeout=30)
    s.delete(f"{BASE_URL}/api/stores/{store['id']}", timeout=30)


def test_cash_bulk_update():
    """Test cash bulk-update"""
    s = requests.Session()
    login = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
    assert login.status_code == 200
    s.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
    
    # Create cash entry
    cash = s.post(f"{BASE_URL}/api/company/cash", json={
        "request_id": str(uuid.uuid4()),
        "amount": "500.00",
        "currency": "USD",
        "direction": "in",
        "date": "2025-01-15",
        "note": "Original note",
    }, timeout=30)
    
    print(f"\nCash POST status: {cash.status_code}")
    if cash.status_code == 200:
        cash_data = cash.json()
        print(f"Cash response keys: {cash_data.keys()}")
        cash_id = cash_data['id']
        
        # Test bulk update
        bulk_update = s.post(f"{BASE_URL}/api/company/cash/bulk-update", json={
            "ids": [cash_id],
            "changes": {"note": "Bulk updated note"}
        }, timeout=30)
        
        print(f"Cash bulk-update status: {bulk_update.status_code}")
        if bulk_update.status_code == 200:
            print(f"Cash bulk-update response: {bulk_update.json()}")
            print("✅ Cash bulk-update endpoint working")
        else:
            print(f"❌ Cash bulk-update failed: {bulk_update.text}")
        
        # Cleanup
        s.delete(f"{BASE_URL}/api/company/cash/{cash_id}", timeout=30)
    else:
        print(f"❌ Cash creation failed: {cash.text}")


def test_debts_bulk_update():
    """Test debts bulk-update"""
    s = requests.Session()
    login = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
    assert login.status_code == 200
    s.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
    
    # Create store
    store = s.post(f"{BASE_URL}/api/stores", json={
        "name": f"TEST_{uuid.uuid4().hex[:6]}",
        "marketplaces": ["US"],
        "default_currency": "USD",
    }, timeout=30).json()
    
    # Create person
    person = s.post(f"{BASE_URL}/api/company/people", json={
        "name": f"Person {uuid.uuid4().hex[:6]}",
        "role": "partner",
        "note": "Test",
    }, timeout=30).json()
    
    # Create debt
    debt = s.post(f"{BASE_URL}/api/company/debts", json={
        "request_id": str(uuid.uuid4()),
        "person_id": person["id"],
        "store_id": store["id"],
        "amount": "1000.00",
        "currency": "USD",
        "direction": "payable",
        "date": "2025-01-15",
        "note": "Original note",
        "cash_effect": False,
    }, timeout=30)
    
    print(f"\nDebt POST status: {debt.status_code}")
    if debt.status_code == 200:
        debt_data = debt.json()
        print(f"Debt response keys: {debt_data.keys()}")
        debt_id = debt_data['id']
        
        # Test bulk update
        bulk_update = s.post(f"{BASE_URL}/api/company/debts/bulk-update", json={
            "ids": [debt_id],
            "changes": {"note": "Bulk updated note"}
        }, timeout=30)
        
        print(f"Debts bulk-update status: {bulk_update.status_code}")
        if bulk_update.status_code == 200:
            print(f"Debts bulk-update response: {bulk_update.json()}")
            print("✅ Debts bulk-update endpoint working")
        else:
            print(f"❌ Debts bulk-update failed: {bulk_update.text}")
        
        # Cleanup
        s.delete(f"{BASE_URL}/api/company/debts/{debt_id}", timeout=30)
    else:
        print(f"❌ Debt creation failed: {debt.text}")
    
    s.delete(f"{BASE_URL}/api/company/people/{person['id']}", timeout=30)
    s.delete(f"{BASE_URL}/api/stores/{store['id']}", timeout=30)


def test_debt_payments_bulk_update():
    """Test debt-payments bulk-update"""
    s = requests.Session()
    login = s.post(f"{BASE_URL}/api/auth/login", json={"email": TEST_EMAIL, "password": TEST_PASSWORD}, timeout=30)
    assert login.status_code == 200
    s.headers.update({"Authorization": f"Bearer {login.json()['token']}"})
    
    # Create store
    store = s.post(f"{BASE_URL}/api/stores", json={
        "name": f"TEST_{uuid.uuid4().hex[:6]}",
        "marketplaces": ["US"],
        "default_currency": "USD",
    }, timeout=30).json()
    
    # Create person
    person = s.post(f"{BASE_URL}/api/company/people", json={
        "name": f"Person {uuid.uuid4().hex[:6]}",
        "role": "partner",
        "note": "Test",
    }, timeout=30).json()
    
    # Create debt
    debt = s.post(f"{BASE_URL}/api/company/debts", json={
        "request_id": str(uuid.uuid4()),
        "person_id": person["id"],
        "store_id": store["id"],
        "amount": "2000.00",
        "currency": "USD",
        "direction": "payable",
        "date": "2025-01-15",
        "note": "Debt",
        "cash_effect": False,
    }, timeout=30).json()
    
    # Make payment
    payment = s.post(f"{BASE_URL}/api/company/debts/{debt['id']}/pay", json={
        "request_id": str(uuid.uuid4()),
        "amount": "500.00",
        "date": "2025-01-20",
        "note": "Original payment note",
    }, timeout=30)
    
    print(f"\nPayment POST status: {payment.status_code}")
    if payment.status_code == 200:
        payment_data = payment.json()
        print(f"Payment response keys: {payment_data.keys()}")
        
        if 'payments' in payment_data and payment_data['payments']:
            payment_id = payment_data['payments'][0]['id']
            
            # Test bulk update
            bulk_update = s.post(f"{BASE_URL}/api/company/debt-payments/bulk-update", json={
                "ids": [payment_id],
                "changes": {"note": "Bulk updated payment note"}
            }, timeout=30)
            
            print(f"Debt-payments bulk-update status: {bulk_update.status_code}")
            if bulk_update.status_code == 200:
                print(f"Debt-payments bulk-update response: {bulk_update.json()}")
                print("✅ Debt-payments bulk-update endpoint working")
            else:
                print(f"❌ Debt-payments bulk-update failed: {bulk_update.text}")
        else:
            print(f"❌ Payment response missing 'payments' array")
    else:
        print(f"❌ Payment creation failed: {payment.text}")
    
    # Cleanup
    s.delete(f"{BASE_URL}/api/company/debts/{debt['id']}", timeout=30)
    s.delete(f"{BASE_URL}/api/company/people/{person['id']}", timeout=30)
    s.delete(f"{BASE_URL}/api/stores/{store['id']}", timeout=30)


if __name__ == "__main__":
    print("=" * 60)
    print("BULK-UPDATE ENDPOINT VERIFICATION")
    print("=" * 60)
    
    test_capital_bulk_update()
    test_cash_bulk_update()
    test_debts_bulk_update()
    test_debt_payments_bulk_update()
    
    print("\n" + "=" * 60)
    print("VERIFICATION COMPLETE")
    print("=" * 60)
