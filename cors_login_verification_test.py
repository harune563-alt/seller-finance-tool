"""
CORS Login Verification Test
=============================
Focused backend login verification after CORS env fix.

Test Scope:
- Verify CORS preflight and login from new origin (https://sellerfin-tool.preview.emergentagent.com)
- Verify authentication flow (valid/invalid credentials)
- Verify security (untrusted origins denied)
- Verify regression (previously configured origin still works)

Test Credentials: admin@amzsuite.com / admin123
"""

import requests
import sys
from typing import Dict, Any

# Public preview URL from frontend/.env
BASE_URL = "https://sellerfin-tool.preview.emergentagent.com"
NEW_ORIGIN = "https://sellerfin-tool.preview.emergentagent.com"
OLD_ORIGIN = "https://5d01db41-b7e9-4610-9ea6-2c471b5d6d10.preview.emergentagent.com"
EVIL_ORIGIN = "https://evil.example.com"

# Test credentials
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"
WRONG_PASSWORD = "wrongpassword123"

class TestResult:
    def __init__(self):
        self.passed = 0
        self.failed = 0
        self.results = []
    
    def add_pass(self, test_name: str, details: str = ""):
        self.passed += 1
        self.results.append(f"✅ PASS: {test_name}")
        if details:
            self.results.append(f"   {details}")
    
    def add_fail(self, test_name: str, details: str = ""):
        self.failed += 1
        self.results.append(f"❌ FAIL: {test_name}")
        if details:
            self.results.append(f"   {details}")
    
    def print_summary(self):
        print("\n" + "="*80)
        print("CORS LOGIN VERIFICATION TEST RESULTS")
        print("="*80)
        for result in self.results:
            print(result)
        print("="*80)
        print(f"TOTAL: {self.passed + self.failed} tests | PASSED: {self.passed} | FAILED: {self.failed}")
        print("="*80)
        return self.failed == 0

def test_1_preflight_new_origin(result: TestResult):
    """Test 1: OPTIONS preflight from new origin should return 200 with CORS headers"""
    print("\n[TEST 1] CORS preflight from new origin (https://sellerfin-tool.preview.emergentagent.com)")
    
    try:
        response = requests.options(
            f"{BASE_URL}/api/auth/login",
            headers={
                "Origin": NEW_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"
            },
            timeout=10
        )
        
        status = response.status_code
        acao = response.headers.get("Access-Control-Allow-Origin", "")
        credentials = response.headers.get("Access-Control-Allow-Credentials", "")
        
        if status == 200 and acao == NEW_ORIGIN and credentials.lower() == "true":
            result.add_pass(
                "Test 1: Preflight from new origin",
                f"Status: {status}, ACAO: {acao}, Credentials: {credentials}"
            )
        else:
            result.add_fail(
                "Test 1: Preflight from new origin",
                f"Status: {status} (expected 200), ACAO: {acao} (expected {NEW_ORIGIN}), Credentials: {credentials} (expected true)"
            )
    except Exception as e:
        result.add_fail("Test 1: Preflight from new origin", f"Exception: {str(e)}")

def test_2_valid_login_new_origin(result: TestResult) -> Dict[str, Any]:
    """Test 2: POST login with valid credentials from new origin"""
    print("\n[TEST 2] Valid login from new origin")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": NEW_ORIGIN},
            timeout=10
        )
        
        status = response.status_code
        acao = response.headers.get("Access-Control-Allow-Origin", "")
        set_cookie = response.headers.get("Set-Cookie", "")
        
        # Check response body for token
        token_in_body = False
        bearer_token = None
        try:
            data = response.json()
            # Token can be in "token" or "access_token" field
            if "token" in data:
                token_in_body = True
                bearer_token = data["token"]
            elif "access_token" in data:
                token_in_body = True
                bearer_token = data["access_token"]
        except:
            pass
        
        # Check cookie attributes
        has_httponly = "HttpOnly" in set_cookie
        has_secure = "Secure" in set_cookie
        has_samesite_none = "SameSite=None" in set_cookie or "SameSite=none" in set_cookie
        has_access_token = "access_token=" in set_cookie
        
        if (status == 200 and acao == NEW_ORIGIN and token_in_body and 
            has_access_token and has_httponly and has_secure and has_samesite_none):
            result.add_pass(
                "Test 2: Valid login from new origin",
                f"Status: {status}, ACAO: {acao}, Token in body: {token_in_body}, Cookie: HttpOnly={has_httponly}, Secure={has_secure}, SameSite=None={has_samesite_none}"
            )
            return {"success": True, "token": bearer_token, "cookies": response.cookies}
        else:
            result.add_fail(
                "Test 2: Valid login from new origin",
                f"Status: {status} (expected 200), ACAO: {acao}, Token in body: {token_in_body}, Cookie attrs: HttpOnly={has_httponly}, Secure={has_secure}, SameSite=None={has_samesite_none}"
            )
            return {"success": False}
    except Exception as e:
        result.add_fail("Test 2: Valid login from new origin", f"Exception: {str(e)}")
        return {"success": False}

def test_3_auth_me_with_token(result: TestResult, auth_data: Dict[str, Any]):
    """Test 3: GET /api/auth/me with Bearer token"""
    print("\n[TEST 3] GET /api/auth/me with Bearer token")
    
    if not auth_data.get("success") or not auth_data.get("token"):
        result.add_fail("Test 3: Auth me with token", "Skipped - no valid token from Test 2")
        return
    
    try:
        response = requests.get(
            f"{BASE_URL}/api/auth/me",
            headers={
                "Authorization": f"Bearer {auth_data['token']}",
                "Origin": NEW_ORIGIN
            },
            timeout=10
        )
        
        status = response.status_code
        email = None
        try:
            data = response.json()
            email = data.get("email")
        except:
            pass
        
        if status == 200 and email == ADMIN_EMAIL:
            result.add_pass(
                "Test 3: Auth me with token",
                f"Status: {status}, Email: {email}"
            )
        else:
            result.add_fail(
                "Test 3: Auth me with token",
                f"Status: {status} (expected 200), Email: {email} (expected {ADMIN_EMAIL})"
            )
    except Exception as e:
        result.add_fail("Test 3: Auth me with token", f"Exception: {str(e)}")

def test_4_invalid_password(result: TestResult):
    """Test 4: POST login with wrong password should return 401 with Turkish message"""
    print("\n[TEST 4] Login with wrong password from new origin")
    
    try:
        response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": WRONG_PASSWORD},
            headers={"Origin": NEW_ORIGIN},
            timeout=10
        )
        
        status = response.status_code
        message = ""
        try:
            data = response.json()
            message = data.get("detail", "")
        except:
            pass
        
        # Check for Turkish error message
        has_turkish_message = "hatalı" in message.lower() or "E-posta veya şifre hatalı" in message
        
        if status == 401 and has_turkish_message:
            result.add_pass(
                "Test 4: Invalid password rejection",
                f"Status: {status}, Message: '{message}'"
            )
        else:
            result.add_fail(
                "Test 4: Invalid password rejection",
                f"Status: {status} (expected 401), Message: '{message}' (expected Turkish 'hatalı' message)"
            )
    except Exception as e:
        result.add_fail("Test 4: Invalid password rejection", f"Exception: {str(e)}")

def test_5_untrusted_origin_preflight(result: TestResult):
    """Test 5: Preflight from untrusted origin should be denied"""
    print("\n[TEST 5] CORS preflight from untrusted origin (https://evil.example.com)")
    
    try:
        response = requests.options(
            f"{BASE_URL}/api/auth/login",
            headers={
                "Origin": EVIL_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"
            },
            timeout=10
        )
        
        status = response.status_code
        acao = response.headers.get("Access-Control-Allow-Origin", "")
        
        # Should be 400 or denied, and ACAO should NOT match evil origin
        if status == 400 and acao != EVIL_ORIGIN:
            result.add_pass(
                "Test 5: Untrusted origin denied",
                f"Status: {status}, ACAO: '{acao}' (correctly not matching evil origin)"
            )
        else:
            result.add_fail(
                "Test 5: Untrusted origin denied",
                f"Status: {status} (expected 400), ACAO: '{acao}' (should not match {EVIL_ORIGIN})"
            )
    except Exception as e:
        result.add_fail("Test 5: Untrusted origin denied", f"Exception: {str(e)}")

def test_6_regression_old_origin(result: TestResult):
    """Test 6: Regression - previously configured origin should still work"""
    print("\n[TEST 6] Regression: Login from previously configured origin")
    
    # Test 6a: Preflight from old origin
    try:
        preflight_response = requests.options(
            f"{BASE_URL}/api/auth/login",
            headers={
                "Origin": OLD_ORIGIN,
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "content-type"
            },
            timeout=10
        )
        
        preflight_status = preflight_response.status_code
        preflight_acao = preflight_response.headers.get("Access-Control-Allow-Origin", "")
        
        # Test 6b: Login from old origin
        login_response = requests.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": OLD_ORIGIN},
            timeout=10
        )
        
        login_status = login_response.status_code
        login_acao = login_response.headers.get("Access-Control-Allow-Origin", "")
        
        if (preflight_status == 200 and preflight_acao == OLD_ORIGIN and 
            login_status == 200 and login_acao == OLD_ORIGIN):
            result.add_pass(
                "Test 6: Regression - old origin still works",
                f"Preflight: {preflight_status} with ACAO={preflight_acao}, Login: {login_status} with ACAO={login_acao}"
            )
        else:
            result.add_fail(
                "Test 6: Regression - old origin still works",
                f"Preflight: {preflight_status} (expected 200) with ACAO={preflight_acao}, Login: {login_status} (expected 200) with ACAO={login_acao}"
            )
    except Exception as e:
        result.add_fail("Test 6: Regression - old origin still works", f"Exception: {str(e)}")

def cleanup_login_attempts():
    """Clean up any login_attempts entries for admin identifier"""
    print("\n[CLEANUP] Checking for login_attempts entries to clean up...")
    
    try:
        from pymongo import MongoClient
        import os
        
        mongo_url = os.environ.get("MONGO_URL", "mongodb://localhost:27017")
        db_name = os.environ.get("DB_NAME", "amazon_seller_suite")
        
        client = MongoClient(mongo_url)
        db = client[db_name]
        
        # Find login_attempts for admin email
        attempts = list(db.login_attempts.find({"identifier": ADMIN_EMAIL}))
        
        if attempts:
            result = db.login_attempts.delete_many({"identifier": ADMIN_EMAIL})
            print(f"   Deleted {result.deleted_count} login_attempts entries for {ADMIN_EMAIL}")
        else:
            print(f"   No login_attempts entries found for {ADMIN_EMAIL}")
        
        client.close()
    except Exception as e:
        print(f"   Cleanup warning: {str(e)}")

def main():
    print("="*80)
    print("CORS LOGIN VERIFICATION TEST")
    print("="*80)
    print(f"Base URL: {BASE_URL}")
    print(f"New Origin: {NEW_ORIGIN}")
    print(f"Old Origin: {OLD_ORIGIN}")
    print(f"Test Credentials: {ADMIN_EMAIL} / {ADMIN_PASSWORD}")
    print("="*80)
    
    result = TestResult()
    
    # Run tests in sequence
    test_1_preflight_new_origin(result)
    auth_data = test_2_valid_login_new_origin(result)
    test_3_auth_me_with_token(result, auth_data)
    test_4_invalid_password(result)
    test_5_untrusted_origin_preflight(result)
    test_6_regression_old_origin(result)
    
    # Cleanup
    cleanup_login_attempts()
    
    # Print summary
    success = result.print_summary()
    
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
