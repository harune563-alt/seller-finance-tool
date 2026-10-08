#!/usr/bin/env python3
"""
CORS Store Creation Bug Verification Test
Tests the fix for user-reported bug: store creation failed with 403 after moving to new Emergent account.
Root cause: CORS_ORIGINS had old UUID preview URL, but frontend runs at https://main-branch-dev.preview.emergentagent.com

This test verifies:
1. POST /api/stores with correct Origin returns 200 (bug is fixed)
2. POST /api/stores with untrusted Origin returns 403 (security check intact)
3. Full user flow: login → create store → verify store appears in list → cleanup
"""
import os
import uuid
import requests
import pytest

# Backend URL from environment
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://main-branch-dev.preview.emergentagent.com")
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

# The current frontend origin (should match CORS_ORIGINS in backend/.env)
TRUSTED_ORIGIN = "https://main-branch-dev.preview.emergentagent.com"
# An untrusted origin to test security
UNTRUSTED_ORIGIN = "https://evil.example.com"


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def admin_session(base_url):
    """Create authenticated admin session with correct Origin header"""
    s = requests.Session()
    # Set the Origin header to the trusted origin
    s.headers.update({"Origin": TRUSTED_ORIGIN})
    
    login = s.post(
        f"{base_url}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=30,
    )
    assert login.status_code == 200, f"Admin login failed: {login.status_code} {login.text}"
    payload = login.json()
    assert isinstance(payload.get("token"), str) and payload["token"], "No token in login response"
    
    # Store the token for later use
    s.token = payload["token"]
    return s


def test_store_creation_with_trusted_origin(admin_session, base_url):
    """
    Test 1: POST /api/stores with trusted Origin header returns 200
    This verifies the CORS fix - store creation should work with the correct origin
    """
    store_name = f"alfa_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": store_name,
        "marketplaces": ["CA"],  # Canada as per user's repro steps
        "default_currency": "USD",
    }
    
    # Make request with trusted origin (already set in session)
    r = admin_session.post(
        f"{base_url}/api/stores",
        json=payload,
        timeout=30,
    )
    
    # Should succeed with 200
    assert r.status_code == 200, f"Store creation failed with trusted origin: {r.status_code} {r.text}"
    
    store = r.json()
    assert store["name"] == store_name, "Store name mismatch"
    assert store["default_currency"] == "USD", "Currency mismatch"
    assert "CA" in store["marketplaces"], "Marketplace not set correctly"
    assert "id" in store, "Store ID missing"
    
    # Verify store appears in list
    list_r = admin_session.get(f"{base_url}/api/stores", timeout=30)
    assert list_r.status_code == 200, f"Store list failed: {list_r.status_code}"
    stores = list_r.json()
    assert any(s["id"] == store["id"] for s in stores), "Created store not in list"
    
    # Cleanup: delete the test store
    delete_r = admin_session.delete(f"{base_url}/api/stores/{store['id']}", timeout=30)
    assert delete_r.status_code == 200, f"Store cleanup failed: {delete_r.status_code}"
    
    print(f"✅ Store creation with trusted origin succeeded: {store['id']}")


def test_store_creation_with_untrusted_origin(admin_session, base_url):
    """
    Test 2: POST /api/stores with untrusted Origin header returns 403
    This verifies the security check is still intact - untrusted origins should be rejected
    """
    store_name = f"evil_test_{uuid.uuid4().hex[:8]}"
    payload = {
        "name": store_name,
        "marketplaces": ["US"],
        "default_currency": "USD",
    }
    
    # Create a new session with untrusted origin
    evil_session = requests.Session()
    evil_session.headers.update({
        "Origin": UNTRUSTED_ORIGIN,
        "Authorization": f"Bearer {admin_session.token}",
    })
    # Copy cookies from admin session
    evil_session.cookies.update(admin_session.cookies)
    
    # Make request with untrusted origin
    r = evil_session.post(
        f"{base_url}/api/stores",
        json=payload,
        timeout=30,
    )
    
    # Should be rejected with 403
    assert r.status_code == 403, f"Expected 403 for untrusted origin, got {r.status_code}"
    
    response_data = r.json()
    assert "İzin verilmeyen istek kaynağı" in response_data.get("detail", ""), \
        f"Expected Turkish error message, got: {response_data}"
    
    print(f"✅ Store creation with untrusted origin correctly rejected with 403")


def test_full_user_flow_exact_repro(admin_session, base_url):
    """
    Test 3: Exact user flow reproduction
    User steps: login → Mağazalar → "Yeni Mağaza" → name "alfa" → USD → Canada (CA) → "Oluştur"
    Expected: Success toast, dialog closes, store appears in list
    """
    # User's exact store configuration
    payload = {
        "name": "alfa",
        "marketplaces": ["CA"],  # Canada (CA)
        "default_currency": "USD",
    }
    
    # Create store
    r = admin_session.post(
        f"{base_url}/api/stores",
        json=payload,
        timeout=30,
    )
    
    # Should succeed
    assert r.status_code == 200, f"Exact user flow failed: {r.status_code} {r.text}"
    
    store = r.json()
    assert store["name"] == "alfa", "Store name should be 'alfa'"
    assert store["default_currency"] == "USD", "Currency should be USD"
    assert "CA" in store["marketplaces"], "Should have Canada marketplace"
    
    # Verify store appears in list (simulating UI refresh)
    list_r = admin_session.get(f"{base_url}/api/stores", timeout=30)
    assert list_r.status_code == 200
    stores = list_r.json()
    alfa_store = next((s for s in stores if s["name"] == "alfa"), None)
    assert alfa_store is not None, "Store 'alfa' not found in list"
    assert alfa_store["id"] == store["id"], "Store ID mismatch"
    
    # Cleanup
    delete_r = admin_session.delete(f"{base_url}/api/stores/{store['id']}", timeout=30)
    assert delete_r.status_code == 200
    
    print(f"✅ Exact user flow (alfa/USD/CA) succeeded: {store['id']}")


def test_no_cors_errors_in_api_response(admin_session, base_url):
    """
    Test 4: Verify no CORS-related errors in API responses
    """
    # Test login endpoint
    login_r = requests.post(
        f"{base_url}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        headers={"Origin": TRUSTED_ORIGIN},
        timeout=30,
    )
    assert login_r.status_code == 200, "Login should succeed"
    
    # Check CORS headers in response
    assert "access-control-allow-origin" in login_r.headers or \
           "Access-Control-Allow-Origin" in login_r.headers, \
           "CORS headers missing in response"
    
    # Test stores list endpoint
    token = login_r.json()["token"]
    list_r = requests.get(
        f"{base_url}/api/stores",
        headers={
            "Origin": TRUSTED_ORIGIN,
            "Authorization": f"Bearer {token}",
        },
        timeout=30,
    )
    assert list_r.status_code == 200, "Stores list should succeed"
    
    print("✅ No CORS errors detected in API responses")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
