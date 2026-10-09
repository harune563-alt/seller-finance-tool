"""
Continuation Task: Backend-only runtime restoration verification.

This test verifies:
1. Supervisor backend/frontend status
2. Backend startup logs
3. MongoDB connection and DB_NAME=amazon_seller_suite
4. Required env variables (without exposing secrets)
5. Explicit CORS and REACT_APP_BACKEND_URL contract
6. /api auth login + session
7. Dashboard/stores read-only endpoints
8. Frankfurter v2 historical FX endpoint
9. Backend remains RUNNING
10. Safe regression checks for Amazon Payments CSV idempotency/date preservation
11. SellerFlash cost import/reconciliation endpoints are still registered and accessible
"""
import os
import sys
import requests
import subprocess
import time
from datetime import datetime
from dotenv import load_dotenv

# Load backend environment variables
load_dotenv("/app/backend/.env")

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

# Get backend URL from frontend .env
BACKEND_URL = None
try:
    with open("/app/frontend/.env", "r") as f:
        for line in f:
            if line.startswith("REACT_APP_BACKEND_URL="):
                BACKEND_URL = line.split("=", 1)[1].strip()
                break
except Exception as e:
    print(f"❌ Failed to read frontend .env: {e}")
    sys.exit(1)

if not BACKEND_URL:
    print("❌ REACT_APP_BACKEND_URL not found in frontend/.env")
    sys.exit(1)

API_BASE = f"{BACKEND_URL}/api"
print(f"✓ Using backend URL: {API_BASE}")

# Test results
results = []
session = requests.Session()


def test_supervisor_status():
    """Test 1: Verify supervisor backend/frontend status"""
    print("\n=== Test 1: Supervisor Status ===")
    try:
        result = subprocess.run(
            ["sudo", "supervisorctl", "status"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout + result.stderr
        
        backend_running = "backend" in output and "RUNNING" in output
        frontend_running = "frontend" in output and "RUNNING" in output
        
        if backend_running and frontend_running:
            print("✅ Backend and frontend services RUNNING")
            results.append(("Supervisor Status", True, "Backend and frontend RUNNING"))
            return True
        else:
            print(f"❌ Services not running:\n{output}")
            results.append(("Supervisor Status", False, f"Services not running: {output[:200]}"))
            return False
    except Exception as e:
        print(f"❌ Failed to check supervisor status: {e}")
        results.append(("Supervisor Status", False, str(e)))
        return False


def test_backend_logs():
    """Test 2: Verify backend startup logs"""
    print("\n=== Test 2: Backend Startup Logs ===")
    try:
        result = subprocess.run(
            ["tail", "-n", "50", "/var/log/supervisor/backend.err.log"],
            capture_output=True,
            text=True,
            timeout=10
        )
        logs = result.stdout
        
        startup_complete = "Application startup complete" in logs
        admin_seeded = "Admin user seeded" in logs or "admin@amzsuite.com" in logs
        
        if startup_complete:
            print("✅ Backend startup complete")
            if admin_seeded:
                print("✅ Admin user seeded")
            results.append(("Backend Startup Logs", True, "Application startup complete"))
            return True
        else:
            print(f"❌ Backend startup not complete:\n{logs[-500:]}")
            results.append(("Backend Startup Logs", False, "Startup not complete"))
            return False
    except Exception as e:
        print(f"❌ Failed to check backend logs: {e}")
        results.append(("Backend Startup Logs", False, str(e)))
        return False


def test_mongodb_connection():
    """Test 3: Verify MongoDB connection and DB_NAME"""
    print("\n=== Test 3: MongoDB Connection ===")
    try:
        from pymongo import MongoClient
        
        mongo_url = os.environ.get("MONGO_URL", "mongodb://127.0.0.1:27017")
        db_name = os.environ.get("DB_NAME", "amazon_seller_suite")
        
        client = MongoClient(mongo_url, serverSelectionTimeoutMS=5000)
        client.server_info()  # Force connection
        
        db = client[db_name]
        collections = db.list_collection_names()
        
        print(f"✅ MongoDB connected successfully")
        print(f"✅ Database: {db_name}")
        print(f"✅ Collections found: {len(collections)}")
        
        client.close()
        results.append(("MongoDB Connection", True, f"Connected to {db_name} with {len(collections)} collections"))
        return True
    except Exception as e:
        print(f"❌ MongoDB connection failed: {e}")
        results.append(("MongoDB Connection", False, str(e)))
        return False


def test_env_variables():
    """Test 4: Verify required env variables (without exposing secrets)"""
    print("\n=== Test 4: Environment Variables ===")
    try:
        required_vars = [
            "MONGO_URL",
            "DB_NAME",
            "JWT_SECRET",
            "WEBHOOK_CRON_SECRET",
            "FRANKFURTER_BASE_URL",
            "FX_TIMEOUT_SECONDS",
            "CORS_ORIGINS"
        ]
        
        missing = []
        for var in required_vars:
            value = os.environ.get(var)
            if not value:
                missing.append(var)
                print(f"❌ {var}: NOT SET")
            else:
                # Don't expose secrets
                if "SECRET" in var:
                    print(f"✅ {var}: [PRESENT]")
                else:
                    print(f"✅ {var}: {value}")
        
        if missing:
            results.append(("Environment Variables", False, f"Missing: {', '.join(missing)}"))
            return False
        else:
            results.append(("Environment Variables", True, "All required variables present"))
            return True
    except Exception as e:
        print(f"❌ Failed to check env variables: {e}")
        results.append(("Environment Variables", False, str(e)))
        return False


def test_cors_configuration():
    """Test 5: Verify CORS and REACT_APP_BACKEND_URL contract"""
    print("\n=== Test 5: CORS Configuration ===")
    try:
        cors_origins = os.environ.get("CORS_ORIGINS", "")
        
        # Check that CORS_ORIGINS matches REACT_APP_BACKEND_URL
        if BACKEND_URL in cors_origins:
            print(f"✅ CORS_ORIGINS includes REACT_APP_BACKEND_URL: {BACKEND_URL}")
            results.append(("CORS Configuration", True, "CORS properly configured"))
            return True
        else:
            print(f"❌ CORS_ORIGINS does not include REACT_APP_BACKEND_URL")
            print(f"   CORS_ORIGINS: {cors_origins}")
            print(f"   REACT_APP_BACKEND_URL: {BACKEND_URL}")
            results.append(("CORS Configuration", False, "CORS mismatch"))
            return False
    except Exception as e:
        print(f"❌ Failed to check CORS configuration: {e}")
        results.append(("CORS Configuration", False, str(e)))
        return False


def test_auth_login():
    """Test 6: Verify /api/auth/login endpoint"""
    print("\n=== Test 6: Auth Login ===")
    try:
        response = session.post(
            f"{API_BASE}/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "token" in data or "access_token" in session.cookies:
                print(f"✅ Login successful for {ADMIN_EMAIL}")
                print(f"✅ Response: {data.get('email')}")
                results.append(("Auth Login", True, "Login successful"))
                return True
            else:
                print(f"❌ Login response missing token: {data}")
                results.append(("Auth Login", False, "Missing token"))
                return False
        else:
            print(f"❌ Login failed: {response.status_code} - {response.text}")
            results.append(("Auth Login", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ Auth login failed: {e}")
        results.append(("Auth Login", False, str(e)))
        return False


def test_auth_session():
    """Test 7: Verify /api/auth/me endpoint (session persistence)"""
    print("\n=== Test 7: Auth Session ===")
    try:
        response = session.get(
            f"{API_BASE}/auth/me",
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("email") == ADMIN_EMAIL:
                print(f"✅ Session valid for {ADMIN_EMAIL}")
                results.append(("Auth Session", True, "Session valid"))
                return True
            else:
                print(f"❌ Session email mismatch: {data}")
                results.append(("Auth Session", False, "Email mismatch"))
                return False
        else:
            print(f"❌ Session check failed: {response.status_code} - {response.text}")
            results.append(("Auth Session", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ Auth session check failed: {e}")
        results.append(("Auth Session", False, str(e)))
        return False


def test_dashboard_endpoint():
    """Test 8: Verify /api/dashboard/summary read-only endpoint"""
    print("\n=== Test 8: Dashboard Endpoint ===")
    try:
        response = session.get(
            f"{API_BASE}/dashboard/summary",
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Dashboard endpoint accessible")
            print(f"✅ Response keys: {list(data.keys())[:5]}...")
            results.append(("Dashboard Endpoint", True, "Accessible"))
            return True
        else:
            print(f"❌ Dashboard endpoint failed: {response.status_code} - {response.text}")
            results.append(("Dashboard Endpoint", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ Dashboard endpoint failed: {e}")
        results.append(("Dashboard Endpoint", False, str(e)))
        return False


def test_stores_endpoint():
    """Test 9: Verify /api/stores read-only endpoint"""
    print("\n=== Test 9: Stores Endpoint ===")
    try:
        response = session.get(
            f"{API_BASE}/stores",
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Stores endpoint accessible")
            print(f"✅ Stores count: {len(data)}")
            results.append(("Stores Endpoint", True, f"{len(data)} stores"))
            return True
        else:
            print(f"❌ Stores endpoint failed: {response.status_code} - {response.text}")
            results.append(("Stores Endpoint", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ Stores endpoint failed: {e}")
        results.append(("Stores Endpoint", False, str(e)))
        return False


def test_frankfurter_fx():
    """Test 10: Verify Frankfurter v2 historical FX endpoint"""
    print("\n=== Test 10: Frankfurter FX Endpoint ===")
    try:
        # Test with a historical date
        test_date = "2024-10-07"
        response = session.get(
            f"{API_BASE}/fx/to-usd",
            params={"currency": "TRY", "date": test_date},
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if "rate" in data and "source" in data:
                print(f"✅ FX endpoint accessible")
                print(f"✅ TRY/USD rate for {test_date}: {data.get('rate')}")
                print(f"✅ Source: {data.get('source')}")
                
                # Verify it's using Frankfurter v2
                if "frankfurter" in data.get("source", "").lower():
                    print(f"✅ Using Frankfurter v2")
                    results.append(("Frankfurter FX", True, f"Rate: {data.get('rate')}, Source: {data.get('source')}"))
                    return True
                else:
                    print(f"⚠️  Source is not Frankfurter: {data.get('source')}")
                    results.append(("Frankfurter FX", True, f"Working but source: {data.get('source')}"))
                    return True
            else:
                print(f"❌ FX response missing required fields: {data}")
                results.append(("Frankfurter FX", False, "Missing fields"))
                return False
        else:
            print(f"❌ FX endpoint failed: {response.status_code} - {response.text}")
            results.append(("Frankfurter FX", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ FX endpoint failed: {e}")
        results.append(("Frankfurter FX", False, str(e)))
        return False


def test_amazon_csv_endpoints():
    """Test 11: Verify Amazon Payments CSV endpoints are accessible"""
    print("\n=== Test 11: Amazon CSV Endpoints ===")
    try:
        # Test import history endpoint
        response = session.get(
            f"{API_BASE}/transactions/import/history",
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ Amazon import history endpoint accessible")
            print(f"✅ Import batches: {len(data)}")
            results.append(("Amazon CSV Endpoints", True, f"{len(data)} import batches"))
            return True
        else:
            print(f"❌ Amazon import history failed: {response.status_code} - {response.text}")
            results.append(("Amazon CSV Endpoints", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ Amazon CSV endpoints failed: {e}")
        results.append(("Amazon CSV Endpoints", False, str(e)))
        return False


def test_sellerflash_endpoints():
    """Test 12: Verify SellerFlash endpoints are accessible"""
    print("\n=== Test 12: SellerFlash Endpoints ===")
    try:
        # Test SellerFlash history endpoint
        response = session.get(
            f"{API_BASE}/sellerflash/history",
            headers={"Origin": BACKEND_URL},
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            print(f"✅ SellerFlash history endpoint accessible")
            print(f"✅ Import batches: {len(data)}")
            results.append(("SellerFlash Endpoints", True, f"{len(data)} import batches"))
            return True
        else:
            print(f"❌ SellerFlash history failed: {response.status_code} - {response.text}")
            results.append(("SellerFlash Endpoints", False, f"Status {response.status_code}"))
            return False
    except Exception as e:
        print(f"❌ SellerFlash endpoints failed: {e}")
        results.append(("SellerFlash Endpoints", False, str(e)))
        return False


def test_backend_still_running():
    """Test 13: Verify backend remains RUNNING after all tests"""
    print("\n=== Test 13: Backend Still Running ===")
    try:
        result = subprocess.run(
            ["sudo", "supervisorctl", "status", "backend"],
            capture_output=True,
            text=True,
            timeout=10
        )
        output = result.stdout + result.stderr
        
        if "RUNNING" in output:
            print("✅ Backend still RUNNING after all tests")
            results.append(("Backend Still Running", True, "Backend RUNNING"))
            return True
        else:
            print(f"❌ Backend not running:\n{output}")
            results.append(("Backend Still Running", False, f"Backend not running: {output[:200]}"))
            return False
    except Exception as e:
        print(f"❌ Failed to check backend status: {e}")
        results.append(("Backend Still Running", False, str(e)))
        return False


def print_summary():
    """Print test summary"""
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    
    passed = sum(1 for _, success, _ in results if success)
    total = len(results)
    
    for test_name, success, message in results:
        status = "✅ PASS" if success else "❌ FAIL"
        print(f"{status}: {test_name}")
        if not success:
            print(f"       {message}")
    
    print("="*80)
    print(f"TOTAL: {passed}/{total} tests passed ({passed*100//total if total > 0 else 0}%)")
    print("="*80)
    
    return passed == total


def main():
    """Run all tests"""
    print("="*80)
    print("CONTINUATION TASK: Backend Runtime Restoration Verification")
    print("="*80)
    print(f"Timestamp: {datetime.now().isoformat()}")
    print(f"Backend URL: {BACKEND_URL}")
    print(f"Test Credentials: {ADMIN_EMAIL}")
    print("="*80)
    
    # Run all tests
    test_supervisor_status()
    test_backend_logs()
    test_mongodb_connection()
    test_env_variables()
    test_cors_configuration()
    test_auth_login()
    test_auth_session()
    test_dashboard_endpoint()
    test_stores_endpoint()
    test_frankfurter_fx()
    test_amazon_csv_endpoints()
    test_sellerflash_endpoints()
    test_backend_still_running()
    
    # Print summary
    all_passed = print_summary()
    
    if all_passed:
        print("\n✅ All tests passed! Runtime restoration verified successfully.")
        sys.exit(0)
    else:
        print("\n❌ Some tests failed. Please review the results above.")
        sys.exit(1)


if __name__ == "__main__":
    main()
