#!/usr/bin/env python3
"""
CORS Auth Bug Fix Verification Test
Verifies user-reported bug fix: Login failed with 'Giriş başarısız' on friendly alias URL
Root cause: alias origin missing from CORS_ORIGINS
Fix: Added alias origin to backend/.env CORS_ORIGINS

Test credentials: admin@amzsuite.com / admin123
"""

import requests
import sys
from pymongo import MongoClient
import os
from dotenv import load_dotenv

# Load environment variables
load_dotenv('/app/backend/.env')

# Test configuration
FRIENDLY_ALIAS = "https://amazon-payments-dev.preview.emergentagent.com"
CANONICAL_URL = "https://d475802d-d8ad-42a5-8683-782b6f0e8c23.preview.emergentagent.com"
UNTRUSTED_ORIGIN = "https://evil.example.com"

VALID_EMAIL = "admin@amzsuite.com"
VALID_PASSWORD = "admin123"
INVALID_PASSWORD = "wrongpassword123"

# MongoDB connection
MONGO_URL = os.getenv('MONGO_URL')
DB_NAME = os.getenv('DB_NAME')

def print_test(test_num, description):
    print(f"\n{'='*80}")
    print(f"TEST {test_num}: {description}")
    print('='*80)

def print_result(passed, message):
    status = "✅ PASS" if passed else "❌ FAIL"
    print(f"{status}: {message}")
    return passed

def test_cors_preflight(origin, test_num, should_pass=True):
    """Test CORS preflight OPTIONS request"""
    print_test(test_num, f"CORS preflight OPTIONS /api/auth/login from {origin}")
    
    url = f"{origin}/api/auth/login"
    headers = {
        'Origin': origin,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    }
    
    try:
        response = requests.options(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        
        if should_pass:
            passed = (
                response.status_code == 200 and
                response.headers.get('Access-Control-Allow-Origin') == origin and
                response.headers.get('Access-Control-Allow-Credentials') == 'true'
            )
            return print_result(passed, 
                f"Preflight from {origin}: status={response.status_code}, "
                f"ACAO={response.headers.get('Access-Control-Allow-Origin')}, "
                f"credentials={response.headers.get('Access-Control-Allow-Credentials')}")
        else:
            passed = response.headers.get('Access-Control-Allow-Origin') != origin
            return print_result(passed, 
                f"Untrusted origin correctly rejected (no ACAO header for {origin})")
    except Exception as e:
        return print_result(False, f"Exception: {str(e)}")

def test_valid_login(origin, test_num):
    """Test valid login POST request"""
    print_test(test_num, f"Valid login POST /api/auth/login from {origin}")
    
    url = f"{origin}/api/auth/login"
    headers = {
        'Origin': origin,
        'Content-Type': 'application/json'
    }
    payload = {
        'email': VALID_EMAIL,
        'password': VALID_PASSWORD
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Headers: {dict(response.headers)}")
        print(f"Response body: {response.text[:200]}")
        
        # Check response
        passed = True
        results = []
        
        # Status code
        if response.status_code == 200:
            results.append("Status 200 ✅")
        else:
            results.append(f"Status {response.status_code} ❌")
            passed = False
        
        # ACAO header
        acao = response.headers.get('Access-Control-Allow-Origin')
        if acao == origin:
            results.append(f"ACAO header matches origin ✅")
        else:
            results.append(f"ACAO header mismatch (got: {acao}) ❌")
            passed = False
        
        # Access token cookie
        cookies = response.cookies
        if 'access_token' in cookies:
            cookie = cookies['access_token']
            results.append(f"access_token cookie present ✅")
            # Note: requests library doesn't expose HttpOnly, SameSite, Secure flags
            # These are browser-only attributes
        else:
            results.append("access_token cookie missing ❌")
            passed = False
        
        # Token in body (field is "token" not "access_token")
        try:
            body = response.json()
            if 'token' in body:
                results.append("token in response body ✅")
                return print_result(passed, " | ".join(results)), cookies.get('access_token'), body.get('token')
            else:
                results.append("token missing from body ❌")
                passed = False
        except:
            results.append("Invalid JSON response ❌")
            passed = False
        
        return print_result(passed, " | ".join(results)), None, None
    except Exception as e:
        return print_result(False, f"Exception: {str(e)}"), None

def test_invalid_password(origin, test_num):
    """Test invalid password login"""
    print_test(test_num, f"Invalid password POST /api/auth/login from {origin}")
    
    url = f"{origin}/api/auth/login"
    headers = {
        'Origin': origin,
        'Content-Type': 'application/json'
    }
    payload = {
        'email': VALID_EMAIL,
        'password': INVALID_PASSWORD
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text}")
        
        passed = True
        results = []
        
        # Should return 401
        if response.status_code == 401:
            results.append("Status 401 ✅")
        else:
            results.append(f"Status {response.status_code} (expected 401) ❌")
            passed = False
        
        # Check error message
        try:
            body = response.json()
            error_msg = body.get('detail', '')
            if 'E-posta veya şifre hatalı' in error_msg or 'hatalı' in error_msg.lower():
                results.append(f"Generic error message present ✅")
            else:
                results.append(f"Error message: '{error_msg}' ⚠️")
        except:
            pass
        
        return print_result(passed, " | ".join(results))
    except Exception as e:
        return print_result(False, f"Exception: {str(e)}")

def test_session_persistence(origin, cookie, test_num):
    """Test session persistence with cookie"""
    print_test(test_num, f"Session persistence GET /api/auth/me from {origin} with cookie")
    
    url = f"{origin}/api/auth/me"
    headers = {
        'Origin': origin
    }
    cookies = {'access_token': cookie} if cookie else {}
    
    try:
        response = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        print(f"Status: {response.status_code}")
        print(f"Response: {response.text[:200]}")
        
        passed = True
        results = []
        
        if response.status_code == 200:
            results.append("Status 200 ✅")
            try:
                body = response.json()
                if body.get('email') == VALID_EMAIL:
                    results.append(f"User data correct (email: {VALID_EMAIL}) ✅")
                else:
                    results.append(f"User data mismatch ❌")
                    passed = False
            except:
                results.append("Invalid JSON response ❌")
                passed = False
        else:
            results.append(f"Status {response.status_code} (expected 200) ❌")
            passed = False
        
        return print_result(passed, " | ".join(results))
    except Exception as e:
        return print_result(False, f"Exception: {str(e)}")

def test_bearer_token(origin, token, test_num):
    """Test Bearer token authentication"""
    print_test(test_num, f"Bearer token auth GET /api/auth/me from {origin}")
    
    url = f"{origin}/api/auth/me"
    headers = {
        'Origin': origin,
        'Authorization': f'Bearer {token}'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        print(f"Status: {response.status_code}")
        
        passed = response.status_code == 200
        return print_result(passed, 
            f"Bearer token auth: status={response.status_code}")
    except Exception as e:
        return print_result(False, f"Exception: {str(e)}")

def test_untrusted_origin_security(test_num):
    """Test that untrusted origins are rejected"""
    print_test(test_num, f"Security check: untrusted origin {UNTRUSTED_ORIGIN}")
    
    # Test preflight with untrusted origin header to real backend
    print(f"\n--- Testing OPTIONS preflight with untrusted origin ---")
    url = f"{CANONICAL_URL}/api/auth/login"
    headers = {
        'Origin': UNTRUSTED_ORIGIN,
        'Access-Control-Request-Method': 'POST',
        'Access-Control-Request-Headers': 'content-type'
    }
    
    try:
        response = requests.options(url, headers=headers, timeout=10)
        print(f"Preflight status: {response.status_code}")
        acao_preflight = response.headers.get('Access-Control-Allow-Origin')
        print(f"Preflight ACAO: {acao_preflight}")
        
        # Should not have ACAO header matching untrusted origin
        preflight_passed = acao_preflight != UNTRUSTED_ORIGIN
        print_result(preflight_passed, 
            f"Preflight with untrusted origin: ACAO={acao_preflight} (should not match {UNTRUSTED_ORIGIN})")
    except Exception as e:
        print_result(False, f"Preflight exception: {str(e)}")
        preflight_passed = False
    
    # Then test actual POST with untrusted origin header
    print(f"\n--- Testing POST with untrusted origin ---")
    headers = {
        'Origin': UNTRUSTED_ORIGIN,
        'Content-Type': 'application/json'
    }
    payload = {
        'email': VALID_EMAIL,
        'password': VALID_PASSWORD
    }
    
    try:
        response = requests.post(url, json=payload, headers=headers, timeout=10)
        print(f"POST status: {response.status_code}")
        
        # Should not have ACAO header for untrusted origin
        acao = response.headers.get('Access-Control-Allow-Origin')
        print(f"POST ACAO: {acao}")
        post_passed = acao != UNTRUSTED_ORIGIN
        
        print_result(post_passed, 
            f"POST with untrusted origin: ACAO={acao} (should not match {UNTRUSTED_ORIGIN})")
        
        return preflight_passed and post_passed
    except Exception as e:
        return print_result(False, f"POST exception: {str(e)}")

def test_mongodb_state(test_num):
    """Test MongoDB state - admin user exists, no extra users, no lockout"""
    print_test(test_num, "MongoDB state verification")
    
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        
        # Check users collection
        users = list(db.users.find({}))
        print(f"Total users in database: {len(users)}")
        
        passed = True
        results = []
        
        # Check admin user exists
        admin_user = db.users.find_one({'email': VALID_EMAIL})
        if admin_user:
            results.append(f"Admin user {VALID_EMAIL} exists ✅")
        else:
            results.append(f"Admin user {VALID_EMAIL} NOT FOUND ❌")
            passed = False
        
        # Check only one admin
        admin_count = db.users.count_documents({'email': VALID_EMAIL})
        if admin_count == 1:
            results.append(f"Single admin user (count: {admin_count}) ✅")
        else:
            results.append(f"Multiple admin users (count: {admin_count}) ❌")
            passed = False
        
        # Check login_attempts for admin
        login_attempts = db.login_attempts.find_one({'email': VALID_EMAIL})
        if login_attempts:
            attempts = login_attempts.get('attempts', 0)
            locked_until = login_attempts.get('locked_until')
            print(f"Login attempts for admin: {attempts}, locked_until: {locked_until}")
            
            if locked_until:
                results.append(f"Admin account has lockout (locked_until: {locked_until}) ⚠️")
            else:
                results.append(f"No active lockout for admin ✅")
        else:
            results.append("No login_attempts record for admin ✅")
        
        client.close()
        return print_result(passed, " | ".join(results))
    except Exception as e:
        return print_result(False, f"Exception: {str(e)}")

def cleanup_login_attempts():
    """Clean up login_attempts entries created during testing"""
    print("\n" + "="*80)
    print("CLEANUP: Removing test login_attempts entries")
    print("="*80)
    
    try:
        client = MongoClient(MONGO_URL)
        db = client[DB_NAME]
        
        # Remove login_attempts for admin created during invalid password tests
        result = db.login_attempts.delete_many({'email': VALID_EMAIL})
        print(f"Deleted {result.deleted_count} login_attempts entries for {VALID_EMAIL}")
        
        client.close()
        return True
    except Exception as e:
        print(f"❌ Cleanup failed: {str(e)}")
        return False

def test_regression_endpoints(origin, cookie, test_num):
    """Test regression: Amazon CSV import history and SellerFlash history endpoints"""
    print_test(test_num, f"Regression check: import history endpoints from {origin}")
    
    headers = {
        'Origin': origin
    }
    cookies = {'access_token': cookie} if cookie else {}
    
    results = []
    passed = True
    
    # Test Amazon CSV import history
    try:
        url = f"{origin}/api/transactions/import/history"
        response = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        print(f"GET /api/transactions/import/history: {response.status_code}")
        
        if response.status_code == 200:
            results.append("Amazon CSV import history endpoint ✅")
        else:
            results.append(f"Amazon CSV import history endpoint {response.status_code} ❌")
            passed = False
    except Exception as e:
        results.append(f"Amazon CSV import history exception: {str(e)} ❌")
        passed = False
    
    # Test SellerFlash history
    try:
        url = f"{origin}/api/sellerflash/history"
        response = requests.get(url, headers=headers, cookies=cookies, timeout=10)
        print(f"GET /api/sellerflash/history: {response.status_code}")
        
        if response.status_code == 200:
            results.append("SellerFlash history endpoint ✅")
        else:
            results.append(f"SellerFlash history endpoint {response.status_code} ❌")
            passed = False
    except Exception as e:
        results.append(f"SellerFlash history exception: {str(e)} ❌")
        passed = False
    
    return print_result(passed, " | ".join(results))

def check_backend_status():
    """Check if backend is still running"""
    print("\n" + "="*80)
    print("FINAL CHECK: Backend service status")
    print("="*80)
    
    import subprocess
    try:
        result = subprocess.run(
            ['sudo', 'supervisorctl', 'status', 'backend'],
            capture_output=True,
            text=True,
            timeout=5
        )
        print(result.stdout)
        
        if 'RUNNING' in result.stdout:
            print("✅ Backend service is RUNNING")
            return True
        else:
            print("❌ Backend service is NOT running")
            return False
    except Exception as e:
        print(f"❌ Failed to check backend status: {str(e)}")
        return False

def main():
    print("\n" + "="*80)
    print("CORS AUTH BUG FIX VERIFICATION TEST")
    print("User-reported bug: Login failed on friendly alias URL")
    print("Fix: Added alias origin to CORS_ORIGINS")
    print("="*80)
    
    test_results = []
    
    # Test 1: CORS preflight from friendly alias
    test_results.append(test_cors_preflight(FRIENDLY_ALIAS, 1))
    
    # Test 2: CORS preflight from canonical URL
    test_results.append(test_cors_preflight(CANONICAL_URL, 2))
    
    # Test 3: Valid login from friendly alias
    result, alias_cookie, alias_token = test_valid_login(FRIENDLY_ALIAS, 3)
    test_results.append(result)
    
    # Test 4: Valid login from canonical URL
    result, canonical_cookie, canonical_token = test_valid_login(CANONICAL_URL, 4)
    test_results.append(result)
    
    # Test 5: Invalid password from friendly alias
    test_results.append(test_invalid_password(FRIENDLY_ALIAS, 5))
    
    # Test 6: Invalid password from canonical URL
    test_results.append(test_invalid_password(CANONICAL_URL, 6))
    
    # Test 7: Session persistence from friendly alias
    if alias_cookie:
        test_results.append(test_session_persistence(FRIENDLY_ALIAS, alias_cookie, 7))
    else:
        print_test(7, "Session persistence from friendly alias - SKIPPED (no cookie)")
        test_results.append(False)
    
    # Test 8: Session persistence from canonical URL
    if canonical_cookie:
        test_results.append(test_session_persistence(CANONICAL_URL, canonical_cookie, 8))
    else:
        print_test(8, "Session persistence from canonical URL - SKIPPED (no cookie)")
        test_results.append(False)
    
    # Test 9: Bearer token auth (use token from login response)
    if alias_token:
        test_results.append(test_bearer_token(FRIENDLY_ALIAS, alias_token, 9))
    else:
        print_test(9, "Bearer token auth - SKIPPED (no token in response)")
        test_results.append(False)
    
    # Test 10: Security - untrusted origin rejected
    test_results.append(test_untrusted_origin_security(10))
    
    # Test 11: MongoDB state
    test_results.append(test_mongodb_state(11))
    
    # Test 12: Regression endpoints from friendly alias
    if alias_cookie:
        test_results.append(test_regression_endpoints(FRIENDLY_ALIAS, alias_cookie, 12))
    else:
        print_test(12, "Regression endpoints - SKIPPED (no cookie)")
        test_results.append(False)
    
    # Test 13: Regression endpoints from canonical URL
    if canonical_cookie:
        test_results.append(test_regression_endpoints(CANONICAL_URL, canonical_cookie, 13))
    else:
        print_test(13, "Regression endpoints - SKIPPED (no cookie)")
        test_results.append(False)
    
    # Cleanup
    cleanup_login_attempts()
    
    # Final backend status check
    backend_running = check_backend_status()
    test_results.append(backend_running)
    
    # Summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    passed = sum(test_results)
    total = len(test_results)
    print(f"PASSED: {passed}/{total} tests")
    print(f"PASS RATE: {passed/total*100:.1f}%")
    
    if passed == total:
        print("\n✅ ALL TESTS PASSED - CORS AUTH BUG FIX VERIFIED")
        return 0
    else:
        print(f"\n❌ {total - passed} TEST(S) FAILED")
        return 1

if __name__ == '__main__':
    sys.exit(main())
