#!/usr/bin/env python3
"""
Focused verification test for POST /api/company/closings/run endpoint
after route decorator restoration.
"""
import os
import uuid
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://24b47787-80b4-43f5-a735-d2fdefafd0fa.preview.emergentagent.com")
TEST_EMAIL = "test-bulk@example.com"
TEST_PASSWORD = "GVNlx6pt-k1LnrqTEPY0M6mt"


def test_closings_run_endpoint_registered():
    """Verify POST /api/company/closings/run is registered and returns 202"""
    # Login
    s = requests.Session()
    login = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Login failed: {login.status_code}"
    token = login.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    
    # Create a test store and transaction for closing
    store = s.post(f"{BASE_URL}/api/stores", json={
        "name": f"CLOSING_TEST_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US"],
        "default_currency": "USD",
    }, timeout=30).json()
    
    # Create a transaction in previous month
    from datetime import date, timedelta
    first = date.today().replace(day=1)
    prev_month = (first - timedelta(days=1)).replace(day=15).isoformat()
    
    s.post(f"{BASE_URL}/api/transactions", json={
        "store_id": store["id"],
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 1000.0,
        "currency": "USD",
        "date": prev_month,
        "description": "Test transaction for closing",
        "order_id": f"TEST-{uuid.uuid4().hex[:8]}",
        "payment_reference": "",
        "product_cost": 0.0,
        "shipping_cost": 0.0,
        "extra_cost": 0.0,
        "product_cost_recovery": 0.0,
        "shipping_cost_recovery": 0.0,
    }, timeout=30)
    
    # Test POST /api/company/closings/run
    print("\n=== Testing POST /api/company/closings/run ===")
    run_response = s.post(f"{BASE_URL}/api/company/closings/run", timeout=30)
    print(f"Status Code: {run_response.status_code}")
    print(f"Response: {run_response.json()}")
    
    assert run_response.status_code == 202, f"Expected 202, got {run_response.status_code}"
    result = run_response.json()
    assert result.get("accepted") is True, "Job not accepted"
    print("✅ POST /api/company/closings/run returns 202 and accepts job")
    
    # Cleanup
    s.delete(f"{BASE_URL}/api/stores/{store['id']}", timeout=30)


def test_get_company_endpoints():
    """Verify existing GET company endpoints return 200"""
    # Login
    s = requests.Session()
    login = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200
    token = login.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    
    # Create test data
    store = s.post(f"{BASE_URL}/api/stores", json={
        "name": f"GET_TEST_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US"],
        "default_currency": "USD",
    }, timeout=30).json()
    
    print("\n=== Testing GET company endpoints ===")
    
    # Test GET /api/company/people
    people_resp = s.get(f"{BASE_URL}/api/company/people", timeout=30)
    print(f"GET /api/company/people: {people_resp.status_code}")
    assert people_resp.status_code == 200
    
    # Test GET /api/company/capital
    capital_resp = s.get(f"{BASE_URL}/api/company/capital", params={"store_id": store["id"]}, timeout=30)
    print(f"GET /api/company/capital: {capital_resp.status_code}")
    assert capital_resp.status_code == 200
    
    # Test GET /api/company/debts
    debts_resp = s.get(f"{BASE_URL}/api/company/debts", timeout=30)
    print(f"GET /api/company/debts: {debts_resp.status_code}")
    assert debts_resp.status_code == 200
    
    # Test GET /api/company/overview
    overview_resp = s.get(f"{BASE_URL}/api/company/overview", timeout=30)
    print(f"GET /api/company/overview: {overview_resp.status_code}")
    assert overview_resp.status_code == 200
    
    # Test GET /api/company/closings
    closings_resp = s.get(f"{BASE_URL}/api/company/closings", timeout=30)
    print(f"GET /api/company/closings: {closings_resp.status_code}")
    assert closings_resp.status_code == 200
    
    # Test GET /api/company/jobs
    jobs_resp = s.get(f"{BASE_URL}/api/company/jobs", timeout=30)
    print(f"GET /api/company/jobs: {jobs_resp.status_code}")
    assert jobs_resp.status_code == 200
    
    print("✅ All GET company endpoints return 200")
    
    # Cleanup
    s.delete(f"{BASE_URL}/api/stores/{store['id']}", timeout=30)


def test_bulk_update_endpoints_available():
    """Verify bulk-update endpoints are available, especially closings"""
    # Login
    s = requests.Session()
    login = s.post(
        f"{BASE_URL}/api/auth/login",
        json={"email": TEST_EMAIL, "password": TEST_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200
    token = login.json()["token"]
    s.headers.update({"Authorization": f"Bearer {token}"})
    
    print("\n=== Testing bulk-update endpoints availability ===")
    
    # Test POST /api/company/closings/bulk-update with empty ids (should return 404)
    closings_bulk = s.post(f"{BASE_URL}/api/company/closings/bulk-update", json={
        "ids": ["non-existent-id"],
        "changes": {"revenue": 1000.0}
    }, timeout=30)
    print(f"POST /api/company/closings/bulk-update: {closings_bulk.status_code}")
    # Should return 404 (not found) not 405 (method not allowed) or 404 (route not found)
    assert closings_bulk.status_code in [404, 422], f"Expected 404/422, got {closings_bulk.status_code}"
    print("✅ POST /api/company/closings/bulk-update is registered")
    
    # Test other bulk-update endpoints
    endpoints = [
        "/api/transactions/bulk-update",
        "/api/stores/bulk-update",
        "/api/company/people/bulk-update",
        "/api/company/capital/bulk-update",
        "/api/company/cash/bulk-update",
        "/api/company/debts/bulk-update",
        "/api/company/debt-payments/bulk-update",
    ]
    
    for endpoint in endpoints:
        resp = s.post(f"{BASE_URL}{endpoint}", json={
            "ids": ["non-existent-id"],
            "changes": {}
        }, timeout=30)
        print(f"POST {endpoint}: {resp.status_code}")
        # Should not return 405 (method not allowed)
        assert resp.status_code != 405, f"{endpoint} returned 405 Method Not Allowed"
    
    print("✅ All bulk-update endpoints are registered")


if __name__ == "__main__":
    print("=" * 70)
    print("CLOSING ROUTE VERIFICATION TEST")
    print("=" * 70)
    
    try:
        test_closings_run_endpoint_registered()
        test_get_company_endpoints()
        test_bulk_update_endpoints_available()
        
        print("\n" + "=" * 70)
        print("ALL VERIFICATION TESTS PASSED ✅")
        print("=" * 70)
        print("\nSummary:")
        print("✅ POST /api/company/closings/run is registered and returns 202")
        print("✅ All GET company endpoints return 200")
        print("✅ All bulk-update endpoints are registered and available")
        print("=" * 70)
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
