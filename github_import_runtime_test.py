#!/usr/bin/env python3
"""
Runtime restoration verification for GitHub import task.
Tests read-only verification of backend services after repository import.
"""

import requests
import sys
from typing import Dict, Any

# Test configuration
BACKEND_URL = "https://fba-finance-hub.preview.emergentagent.com"
API_BASE = f"{BACKEND_URL}/api"
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

# Test results tracking
tests_passed = 0
tests_failed = 0
test_results = []

def log_test(name: str, passed: bool, details: str = ""):
    """Log test result"""
    global tests_passed, tests_failed
    if passed:
        tests_passed += 1
        status = "✅ PASS"
    else:
        tests_failed += 1
        status = "❌ FAIL"
    
    result = f"{status}: {name}"
    if details:
        result += f" - {details}"
    test_results.append(result)
    print(result)

def test_1_supervisor_status():
    """Verify supervisor services are running"""
    import subprocess
    try:
        result = subprocess.run(
            ["sudo", "supervisorctl", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout
        
        backend_running = "backend" in output and "RUNNING" in output
        frontend_running = "frontend" in output and "RUNNING" in output
        mongodb_running = "mongodb" in output and "RUNNING" in output
        
        all_running = backend_running and frontend_running and mongodb_running
        
        log_test(
            "Supervisor services status",
            all_running,
            f"backend={backend_running}, frontend={frontend_running}, mongodb={mongodb_running}"
        )
        return all_running
    except Exception as e:
        log_test("Supervisor services status", False, f"Error: {e}")
        return False

def test_2_backend_startup_logs():
    """Verify backend startup logs show application startup and admin seeding"""
    import subprocess
    try:
        result = subprocess.run(
            ["tail", "-n", "200", "/var/log/supervisor/backend.err.log"],
            capture_output=True,
            text=True,
            timeout=10
        )
        logs = result.stdout
        
        startup_complete = "Application startup complete" in logs
        admin_seeded = "admin@amzsuite.com" in logs and "seeded" in logs.lower()
        
        success = startup_complete and admin_seeded
        
        log_test(
            "Backend startup logs",
            success,
            f"startup_complete={startup_complete}, admin_seeded={admin_seeded}"
        )
        return success
    except Exception as e:
        log_test("Backend startup logs", False, f"Error: {e}")
        return False

def test_3_login_with_admin_credentials():
    """Test POST /api/auth/login with admin credentials returns 200 with token and HttpOnly cookie"""
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        success = (
            response.status_code == 200 and
            "access_token" in response.cookies and
            response.json().get("token") is not None
        )
        
        cookie_attrs = ""
        if "access_token" in response.cookies:
            cookie = response.cookies.get("access_token")
            cookie_attrs = f"cookie_present=True"
        
        log_test(
            "POST /api/auth/login with admin credentials",
            success,
            f"status={response.status_code}, token_in_body={response.json().get('token') is not None}, {cookie_attrs}"
        )
        
        # Return session for subsequent tests
        return response.cookies if success else None
    except Exception as e:
        log_test("POST /api/auth/login with admin credentials", False, f"Error: {e}")
        return None

def test_4_auth_me_with_cookie(session_cookies):
    """Test GET /api/auth/me with cookie returns 200"""
    if not session_cookies:
        log_test("GET /api/auth/me with cookie", False, "No session cookies from login")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE}/auth/me",
            cookies=session_cookies,
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        success = (
            response.status_code == 200 and
            response.json().get("email") == ADMIN_EMAIL
        )
        
        log_test(
            "GET /api/auth/me with cookie",
            success,
            f"status={response.status_code}, email={response.json().get('email') if response.status_code == 200 else 'N/A'}"
        )
        return success
    except Exception as e:
        log_test("GET /api/auth/me with cookie", False, f"Error: {e}")
        return False

def test_5_auth_me_with_bearer_token():
    """Test GET /api/auth/me with Bearer token returns 200"""
    try:
        # First login to get token
        login_response = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if login_response.status_code != 200:
            log_test("GET /api/auth/me with Bearer token", False, "Login failed")
            return False
        
        token = login_response.json().get("token")
        if not token:
            log_test("GET /api/auth/me with Bearer token", False, "No token in login response")
            return False
        
        # Test with Bearer token
        response = requests.get(
            f"{API_BASE}/auth/me",
            headers={
                "Authorization": f"Bearer {token}",
                "Origin": BACKEND_URL
            },
            timeout=10
        )
        
        success = (
            response.status_code == 200 and
            response.json().get("email") == ADMIN_EMAIL
        )
        
        log_test(
            "GET /api/auth/me with Bearer token",
            success,
            f"status={response.status_code}, email={response.json().get('email') if response.status_code == 200 else 'N/A'}"
        )
        return success
    except Exception as e:
        log_test("GET /api/auth/me with Bearer token", False, f"Error: {e}")
        return False

def test_6_invalid_password_rejection():
    """Test invalid password returns generic 401 with Turkish message, no info leak"""
    try:
        response = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": "wrongpassword123"},
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        is_401 = response.status_code == 401
        error_msg = response.json().get("detail", "") if response.status_code == 401 else ""
        
        # Check for generic Turkish error message (no info leak about user existence)
        is_generic = "hatalı" in error_msg.lower() or "başarısız" in error_msg.lower()
        no_info_leak = "bulunamadı" not in error_msg.lower() and "mevcut değil" not in error_msg.lower()
        
        success = is_401 and is_generic and no_info_leak
        
        log_test(
            "Invalid password rejection",
            success,
            f"status={response.status_code}, generic_message={is_generic}, no_info_leak={no_info_leak}"
        )
        return success
    except Exception as e:
        log_test("Invalid password rejection", False, f"Error: {e}")
        return False

def test_7_dashboard_summary_endpoint(session_cookies):
    """Test GET /api/dashboard/summary with auth returns 200"""
    if not session_cookies:
        log_test("GET /api/dashboard/summary", False, "No session cookies")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE}/dashboard/summary",
            cookies=session_cookies,
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        success = response.status_code == 200
        
        log_test(
            "GET /api/dashboard/summary",
            success,
            f"status={response.status_code}"
        )
        return success
    except Exception as e:
        log_test("GET /api/dashboard/summary", False, f"Error: {e}")
        return False

def test_8_stores_endpoint(session_cookies):
    """Test GET /api/stores with auth returns 200"""
    if not session_cookies:
        log_test("GET /api/stores", False, "No session cookies")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE}/stores",
            cookies=session_cookies,
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        success = response.status_code == 200
        
        log_test(
            "GET /api/stores",
            success,
            f"status={response.status_code}"
        )
        return success
    except Exception as e:
        log_test("GET /api/stores", False, f"Error: {e}")
        return False

def test_9_fx_service_try_usd():
    """Test GET /api/fx/to-usd?currency=TRY&date=2024-10-07 returns 200 with frankfurter-v2 source"""
    try:
        # FX endpoint requires authentication, so login first
        login_response = requests.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if login_response.status_code != 200:
            log_test("GET /api/fx/to-usd TRY/USD 2024-10-07", False, "Login failed")
            return False
        
        session_cookies = login_response.cookies
        
        response = requests.get(
            f"{API_BASE}/fx/to-usd",
            params={"currency": "TRY", "date": "2024-10-07"},
            cookies=session_cookies,
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        is_200 = response.status_code == 200
        data = response.json() if is_200 else {}
        
        # Rate can be string or number
        has_rate = "rate" in data and data.get("rate") is not None
        has_source = data.get("source") == "frankfurter-v2"
        
        success = is_200 and has_rate and has_source
        
        log_test(
            "GET /api/fx/to-usd TRY/USD 2024-10-07",
            success,
            f"status={response.status_code}, rate={data.get('rate') if has_rate else 'N/A'}, source={data.get('source')}"
        )
        return success
    except Exception as e:
        log_test("GET /api/fx/to-usd TRY/USD 2024-10-07", False, f"Error: {e}")
        return False

def test_10_amazon_import_history(session_cookies):
    """Test GET /api/transactions/import/history with auth returns 200"""
    if not session_cookies:
        log_test("GET /api/transactions/import/history", False, "No session cookies")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE}/transactions/import/history",
            cookies=session_cookies,
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        success = response.status_code == 200
        
        log_test(
            "GET /api/transactions/import/history",
            success,
            f"status={response.status_code}"
        )
        return success
    except Exception as e:
        log_test("GET /api/transactions/import/history", False, f"Error: {e}")
        return False

def test_11_sellerflash_history(session_cookies):
    """Test GET /api/sellerflash/history with auth returns 200"""
    if not session_cookies:
        log_test("GET /api/sellerflash/history", False, "No session cookies")
        return False
    
    try:
        response = requests.get(
            f"{API_BASE}/sellerflash/history",
            cookies=session_cookies,
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        success = response.status_code == 200
        
        log_test(
            "GET /api/sellerflash/history",
            success,
            f"status={response.status_code}"
        )
        return success
    except Exception as e:
        log_test("GET /api/sellerflash/history", False, f"Error: {e}")
        return False

def test_12_cors_preflight_trusted_origin():
    """Test CORS preflight from trusted origin returns 200 with ACAO and credentials"""
    try:
        response = requests.options(
            f"{API_BASE}/auth/login",
            headers={
                "Origin": BACKEND_URL,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"
            },
            timeout=10
        )
        
        is_200 = response.status_code == 200
        has_acao = response.headers.get("Access-Control-Allow-Origin") == BACKEND_URL
        has_credentials = response.headers.get("Access-Control-Allow-Credentials") == "true"
        
        success = is_200 and has_acao and has_credentials
        
        log_test(
            "CORS preflight from trusted origin",
            success,
            f"status={response.status_code}, ACAO={has_acao}, credentials={has_credentials}"
        )
        return success
    except Exception as e:
        log_test("CORS preflight from trusted origin", False, f"Error: {e}")
        return False

def test_13_cors_preflight_untrusted_origin():
    """Test CORS preflight from untrusted origin is denied"""
    try:
        response = requests.options(
            f"{API_BASE}/auth/login",
            headers={
                "Origin": "https://evil.example.com",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"
            },
            timeout=10
        )
        
        # Should return 400 or not have ACAO header for untrusted origin
        is_denied = (
            response.status_code == 400 or
            response.headers.get("Access-Control-Allow-Origin") != "https://evil.example.com"
        )
        
        log_test(
            "CORS preflight from untrusted origin denied",
            is_denied,
            f"status={response.status_code}, ACAO={response.headers.get('Access-Control-Allow-Origin', 'None')}"
        )
        return is_denied
    except Exception as e:
        log_test("CORS preflight from untrusted origin denied", False, f"Error: {e}")
        return False

def test_14_backend_remains_running():
    """Verify backend service remains RUNNING after all tests"""
    import subprocess
    try:
        result = subprocess.run(
            ["sudo", "supervisorctl", "status", "backend"],
            capture_output=True,
            text=True,
            timeout=10
        )
        
        is_running = "RUNNING" in result.stdout
        
        log_test(
            "Backend remains RUNNING after tests",
            is_running,
            f"status={result.stdout.strip()}"
        )
        return is_running
    except Exception as e:
        log_test("Backend remains RUNNING after tests", False, f"Error: {e}")
        return False

def main():
    """Run all tests"""
    print("=" * 80)
    print("GITHUB IMPORT RUNTIME RESTORATION VERIFICATION")
    print("=" * 80)
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("=" * 80)
    print()
    
    # Test 1-2: Infrastructure
    test_1_supervisor_status()
    test_2_backend_startup_logs()
    
    # Test 3-6: Authentication
    session_cookies = test_3_login_with_admin_credentials()
    test_4_auth_me_with_cookie(session_cookies)
    test_5_auth_me_with_bearer_token()
    test_6_invalid_password_rejection()
    
    # Test 7-8: Protected endpoints
    test_7_dashboard_summary_endpoint(session_cookies)
    test_8_stores_endpoint(session_cookies)
    
    # Test 9: FX service
    test_9_fx_service_try_usd()
    
    # Test 10-11: Import history endpoints
    test_10_amazon_import_history(session_cookies)
    test_11_sellerflash_history(session_cookies)
    
    # Test 12-13: CORS
    test_12_cors_preflight_trusted_origin()
    test_13_cors_preflight_untrusted_origin()
    
    # Test 14: Backend stability
    test_14_backend_remains_running()
    
    # Summary
    print()
    print("=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)
    total_tests = tests_passed + tests_failed
    pass_rate = (tests_passed / total_tests * 100) if total_tests > 0 else 0
    print(f"Total: {total_tests} tests")
    print(f"Passed: {tests_passed} ({pass_rate:.1f}%)")
    print(f"Failed: {tests_failed}")
    print("=" * 80)
    
    if tests_failed > 0:
        print("\nFailed tests:")
        for result in test_results:
            if "❌ FAIL" in result:
                print(f"  {result}")
    
    return 0 if tests_failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
