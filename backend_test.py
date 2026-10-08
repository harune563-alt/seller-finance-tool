"""
Comprehensive backend testing for Phase A Amazon import reconciliation feature.

Tests idempotency, original date preservation, and import history.
"""
import io
import os
import uuid
import requests
from datetime import datetime

# Backend URL from environment
BASE_URL = "https://main-branch-dev.preview.emergentagent.com"
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

# Test data - using PAST dates to avoid Frankfurter future date rejection
ORDER_1 = "702-TEST-0001"
ORDER_2 = "702-TEST-0002"
DATE_1 = "2024-10-07"  # Original date for Order 1
DATE_2 = "2024-10-08"  # Refund date
DATE_3 = "2024-10-11"  # Changed date for Order 1
DATE_4 = "2024-10-12"  # Order 2 date


def create_csv_a():
    """CSV A: Order 702-TEST-0001 100.00 on 2024-10-07, Refund -20.00 on 2024-10-08"""
    return f"""date/time,type,order id,description,total
{DATE_1},Order,{ORDER_1},Test Order Payment,100.00
{DATE_2},Refund,{ORDER_1},Test Refund,-20.00
"""


def create_csv_b():
    """CSV B: Same Order event for 702-TEST-0001 (100.00) but dated 2024-10-11, plus NEW order 702-TEST-0002 50.00 dated 2024-10-12"""
    return f"""date/time,type,order id,description,total
{DATE_3},Order,{ORDER_1},Test Order Payment,100.00
{DATE_4},Order,{ORDER_2},Second Order Payment,50.00
"""


class TestReconciliation:
    def __init__(self):
        self.session = requests.Session()
        self.store_id = None
        self.store_name = None
        self.results = []
        
    def log(self, test_name, passed, message="", details=None):
        """Log test result"""
        status = "✅ PASS" if passed else "❌ FAIL"
        self.results.append({
            "test": test_name,
            "passed": passed,
            "message": message,
            "details": details
        })
        print(f"{status}: {test_name}")
        if message:
            print(f"  {message}")
        if details:
            print(f"  Details: {details}")
    
    def setup(self):
        """Setup: Login and create test store"""
        print("\n=== SETUP ===")
        
        # Login
        r = self.session.post(
            f"{BASE_URL}/api/auth/login",
            json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD}
        )
        if r.status_code != 200:
            self.log("Setup - Login", False, f"Login failed with status {r.status_code}", r.text)
            return False
        
        token = r.json().get("token")
        self.session.headers.update({"Authorization": f"Bearer {token}"})
        self.log("Setup - Login", True, f"Logged in as {ADMIN_EMAIL}")
        
        # Create test store
        self.store_name = f"TEST_RECON_{uuid.uuid4().hex[:8]}"
        r = self.session.post(
            f"{BASE_URL}/api/stores",
            json={
                "name": self.store_name,
                "marketplaces": ["US"],
                "default_currency": "USD"
            }
        )
        if r.status_code != 200:
            self.log("Setup - Create Store", False, f"Store creation failed with status {r.status_code}", r.text)
            return False
        
        self.store_id = r.json()["id"]
        self.log("Setup - Create Store", True, f"Created store {self.store_name} (ID: {self.store_id})")
        return True
    
    def teardown(self):
        """Teardown: Delete test store and data"""
        print("\n=== TEARDOWN ===")
        if self.store_id:
            r = self.session.delete(f"{BASE_URL}/api/stores/{self.store_id}")
            if r.status_code == 200:
                self.log("Teardown - Delete Store", True, f"Deleted store {self.store_name}")
            else:
                self.log("Teardown - Delete Store", False, f"Failed to delete store: {r.status_code}", r.text)
    
    def get_dashboard_summary(self, start_date=None, end_date=None):
        """Get dashboard summary for the test store"""
        params = {
            "store_id": self.store_id,
            "marketplace": "US",
            "currency": "USD"
        }
        if start_date:
            params["start_date"] = start_date
        if end_date:
            params["end_date"] = end_date
        
        r = self.session.get(f"{BASE_URL}/api/dashboard/summary", params=params)
        if r.status_code == 200:
            return r.json()
        return None
    
    def import_csv(self, csv_content, commit=True):
        """Import CSV file"""
        files = {"file": ("payments.csv", io.BytesIO(csv_content.encode("utf-8")), "text/csv")}
        params = {
            "store_id": self.store_id,
            "marketplace": "US",
            "commit": str(commit).lower()
        }
        r = self.session.post(f"{BASE_URL}/api/transactions/import", files=files, params=params)
        return r
    
    def get_transactions(self):
        """Get all transactions for the test store"""
        r = self.session.get(
            f"{BASE_URL}/api/transactions",
            params={"store_id": self.store_id, "marketplace": "US", "limit": 1000}
        )
        if r.status_code == 200:
            return r.json()
        return []
    
    def get_import_history(self):
        """Get import history"""
        r = self.session.get(
            f"{BASE_URL}/api/transactions/import/history",
            params={"store_id": self.store_id, "limit": 50}
        )
        if r.status_code == 200:
            return r.json()
        return []
    
    def get_date_history(self, order_id):
        """Get date change history for an order"""
        r = self.session.get(
            f"{BASE_URL}/api/transactions/date-history",
            params={"order_id": order_id, "store_id": self.store_id}
        )
        if r.status_code == 200:
            return r.json()
        return []
    
    def test_1_same_file_twice(self):
        """TEST 1: Import same CSV twice - verify idempotency"""
        print("\n=== TEST 1: SAME FILE TWICE ===")
        
        csv_a = create_csv_a()
        
        # First import with commit=true
        r1 = self.import_csv(csv_a, commit=True)
        if r1.status_code != 200:
            self.log("Test 1.1 - First Import", False, f"Import failed: {r1.status_code}", r1.text)
            return
        
        data1 = r1.json()
        if data1.get("inserted") != 2:
            self.log("Test 1.1 - First Import", False, f"Expected inserted=2, got {data1.get('inserted')}", data1)
            return
        
        if not data1.get("reconciliation") or data1["reconciliation"].get("new") != 2:
            self.log("Test 1.1 - First Import", False, f"Expected reconciliation.new=2, got {data1.get('reconciliation', {}).get('new')}", data1)
            return
        
        self.log("Test 1.1 - First Import", True, f"Inserted 2 new records, reconciliation.new=2")
        
        # Record dashboard totals
        summary1 = self.get_dashboard_summary()
        if not summary1:
            self.log("Test 1.2 - Dashboard After First Import", False, "Failed to get dashboard summary")
            return
        
        revenue1 = summary1.get("revenue", 0)
        expenses1 = summary1.get("expenses", 0)
        count1 = summary1.get("transaction_count", 0)
        self.log("Test 1.2 - Dashboard After First Import", True, 
                f"Revenue: {revenue1}, Expenses: {expenses1}, Count: {count1}")
        
        # Second import - same file
        r2 = self.import_csv(csv_a, commit=True)
        if r2.status_code != 200:
            self.log("Test 1.3 - Second Import (Same File)", False, f"Import failed: {r2.status_code}", r2.text)
            return
        
        data2 = r2.json()
        if data2.get("inserted") != 0:
            self.log("Test 1.3 - Second Import (Same File)", False, 
                    f"Expected inserted=0 (idempotent), got {data2.get('inserted')}", data2)
            return
        
        if not data2.get("reconciliation") or data2["reconciliation"].get("existing_unchanged") != 2:
            self.log("Test 1.3 - Second Import (Same File)", False, 
                    f"Expected reconciliation.existing_unchanged=2, got {data2.get('reconciliation', {}).get('existing_unchanged')}", data2)
            return
        
        self.log("Test 1.3 - Second Import (Same File)", True, 
                f"Inserted 0, reconciliation.existing_unchanged=2 (idempotent)")
        
        # Verify dashboard totals are IDENTICAL
        summary2 = self.get_dashboard_summary()
        if not summary2:
            self.log("Test 1.4 - Dashboard After Second Import", False, "Failed to get dashboard summary")
            return
        
        revenue2 = summary2.get("revenue", 0)
        expenses2 = summary2.get("expenses", 0)
        count2 = summary2.get("transaction_count", 0)
        
        if revenue1 != revenue2 or expenses1 != expenses2 or count1 != count2:
            self.log("Test 1.4 - Dashboard After Second Import", False, 
                    f"Dashboard totals changed! Before: R={revenue1}, E={expenses1}, C={count1}. After: R={revenue2}, E={expenses2}, C={count2}")
            return
        
        self.log("Test 1.4 - Dashboard After Second Import", True, 
                f"Dashboard totals IDENTICAL (critical financial rule verified)")
        
        # Third import - verify still identical
        r3 = self.import_csv(csv_a, commit=True)
        if r3.status_code != 200:
            self.log("Test 1.5 - Third Import (Same File)", False, f"Import failed: {r3.status_code}", r3.text)
            return
        
        data3 = r3.json()
        summary3 = self.get_dashboard_summary()
        
        if data3.get("inserted") != 0 or not summary3:
            self.log("Test 1.5 - Third Import (Same File)", False, 
                    f"Expected inserted=0, got {data3.get('inserted')}")
            return
        
        revenue3 = summary3.get("revenue", 0)
        expenses3 = summary3.get("expenses", 0)
        count3 = summary3.get("transaction_count", 0)
        
        if revenue1 != revenue3 or expenses1 != expenses3 or count1 != count3:
            self.log("Test 1.5 - Third Import (Same File)", False, 
                    f"Dashboard totals changed on third import!")
            return
        
        self.log("Test 1.5 - Third Import (Same File)", True, 
                f"Third import still identical (idempotency verified)")
    
    def test_2_overlapping_with_date_change(self):
        """TEST 2: Import overlapping report with date change"""
        print("\n=== TEST 2: OVERLAPPING REPORT WITH DATE CHANGE ===")
        
        csv_b = create_csv_b()
        
        # Import CSV B
        r = self.import_csv(csv_b, commit=True)
        if r.status_code != 200:
            self.log("Test 2.1 - Import CSV B", False, f"Import failed: {r.status_code}", r.text)
            return
        
        data = r.json()
        
        # Verify inserted=1 (only the new order 702-TEST-0002)
        if data.get("inserted") != 1:
            self.log("Test 2.1 - Import CSV B", False, 
                    f"Expected inserted=1 (new order), got {data.get('inserted')}", data)
            return
        
        # Verify reconciliation.date_changed=1
        recon = data.get("reconciliation", {})
        if recon.get("date_changed") != 1:
            self.log("Test 2.1 - Import CSV B", False, 
                    f"Expected reconciliation.date_changed=1, got {recon.get('date_changed')}", data)
            return
        
        self.log("Test 2.1 - Import CSV B", True, 
                f"Inserted 1 new order, date_changed=1")
        
        # Verify date_changes shows the change
        date_changes = data.get("date_changes", [])
        if len(date_changes) != 1:
            self.log("Test 2.2 - Date Changes Array", False, 
                    f"Expected 1 date change, got {len(date_changes)}", date_changes)
            return
        
        change = date_changes[0]
        if change.get("order_id") != ORDER_1:
            self.log("Test 2.2 - Date Changes Array", False, 
                    f"Expected order_id={ORDER_1}, got {change.get('order_id')}", change)
            return
        
        if change.get("previous_reported_date") != DATE_1 or change.get("new_reported_date") != DATE_3:
            self.log("Test 2.2 - Date Changes Array", False, 
                    f"Expected date change {DATE_1} → {DATE_3}, got {change.get('previous_reported_date')} → {change.get('new_reported_date')}", change)
            return
        
        self.log("Test 2.2 - Date Changes Array", True, 
                f"Date change recorded: {ORDER_1}: {DATE_1} → {DATE_3}")
        
        # Verify transaction record via API
        transactions = self.get_transactions()
        order_1_income = [t for t in transactions if t.get("order_id") == ORDER_1 and t.get("type") == "income"]
        
        if len(order_1_income) != 1:
            self.log("Test 2.3 - Transaction Record Verification", False, 
                    f"Expected 1 income record for {ORDER_1}, got {len(order_1_income)}", 
                    [t.get("id") for t in order_1_income])
            return
        
        tx = order_1_income[0]
        
        # Verify date still = original date (2024-10-07)
        if tx.get("date") != DATE_1:
            self.log("Test 2.3 - Transaction Record Verification", False, 
                    f"Expected date={DATE_1} (original), got {tx.get('date')}", tx)
            return
        
        # Verify original_transaction_date = 2024-10-07
        if tx.get("original_transaction_date") != DATE_1:
            self.log("Test 2.3 - Transaction Record Verification", False, 
                    f"Expected original_transaction_date={DATE_1}, got {tx.get('original_transaction_date')}", tx)
            return
        
        # Verify latest_amazon_reported_date = 2024-10-11
        if tx.get("latest_amazon_reported_date") != DATE_3:
            self.log("Test 2.3 - Transaction Record Verification", False, 
                    f"Expected latest_amazon_reported_date={DATE_3}, got {tx.get('latest_amazon_reported_date')}", tx)
            return
        
        # Verify date_changed = true
        if tx.get("date_changed") != True:
            self.log("Test 2.3 - Transaction Record Verification", False, 
                    f"Expected date_changed=true, got {tx.get('date_changed')}", tx)
            return
        
        self.log("Test 2.3 - Transaction Record Verification", True, 
                f"Transaction {ORDER_1}: date={DATE_1} (original), latest_amazon_reported_date={DATE_3}, date_changed=true")
        
        # Verify NO second revenue transaction created
        summary = self.get_dashboard_summary()
        if not summary:
            self.log("Test 2.4 - Dashboard Totals", False, "Failed to get dashboard summary")
            return
        
        revenue = summary.get("revenue", 0)
        count = summary.get("transaction_count", 0)
        
        # Expected: 100 (Order 1) + 50 (Order 2) = 150 revenue, 3 transactions total (Order 1, Refund, Order 2)
        if revenue != 150:
            self.log("Test 2.4 - Dashboard Totals", False, 
                    f"Expected revenue=150 (100+50), got {revenue}. NO duplicate revenue should be created!", summary)
            return
        
        if count != 3:
            self.log("Test 2.4 - Dashboard Totals", False, 
                    f"Expected transaction_count=3 (Order 1, Refund, Order 2), got {count}", summary)
            return
        
        self.log("Test 2.4 - Dashboard Totals", True, 
                f"Revenue=150, Count=3 (NO duplicate revenue created)")
        
        # Verify date history API
        date_history = self.get_date_history(ORDER_1)
        if len(date_history) != 1:
            self.log("Test 2.5 - Date History API", False, 
                    f"Expected 1 date history entry, got {len(date_history)}", date_history)
            return
        
        history = date_history[0]
        if history.get("previous_reported_date") != DATE_1 or history.get("new_reported_date") != DATE_3:
            self.log("Test 2.5 - Date History API", False, 
                    f"Expected history {DATE_1} → {DATE_3}, got {history.get('previous_reported_date')} → {history.get('new_reported_date')}", history)
            return
        
        self.log("Test 2.5 - Date History API", True, 
                f"Date history API: 1 entry with {DATE_1} → {DATE_3}")
    
    def test_3_reimport_b_again(self):
        """TEST 3: Re-import CSV B again - verify no duplicate history"""
        print("\n=== TEST 3: RE-IMPORT B AGAIN ===")
        
        csv_b = create_csv_b()
        
        # Re-import CSV B
        r = self.import_csv(csv_b, commit=True)
        if r.status_code != 200:
            self.log("Test 3.1 - Re-import CSV B", False, f"Import failed: {r.status_code}", r.text)
            return
        
        data = r.json()
        
        # Verify inserted=0 (all unchanged)
        if data.get("inserted") != 0:
            self.log("Test 3.1 - Re-import CSV B", False, 
                    f"Expected inserted=0, got {data.get('inserted')}", data)
            return
        
        # Verify all unchanged
        recon = data.get("reconciliation", {})
        if recon.get("existing_unchanged") != 2:
            self.log("Test 3.1 - Re-import CSV B", False, 
                    f"Expected reconciliation.existing_unchanged=2, got {recon.get('existing_unchanged')}", data)
            return
        
        self.log("Test 3.1 - Re-import CSV B", True, 
                f"Inserted 0, all unchanged (idempotent)")
        
        # Verify date history still exactly 1 entry (no duplicate)
        date_history = self.get_date_history(ORDER_1)
        if len(date_history) != 1:
            self.log("Test 3.2 - Date History (No Duplicate)", False, 
                    f"Expected exactly 1 date history entry, got {len(date_history)} (duplicate history created!)", date_history)
            return
        
        self.log("Test 3.2 - Date History (No Duplicate)", True, 
                f"Date history still exactly 1 entry (no duplicate)")
    
    def test_4_reimport_original_a(self):
        """TEST 4: Re-import original CSV A after B - verify no date flip-flop"""
        print("\n=== TEST 4: RE-IMPORT ORIGINAL A AFTER B ===")
        
        csv_a = create_csv_a()
        
        # Re-import CSV A (with original dates)
        r = self.import_csv(csv_a, commit=True)
        if r.status_code != 200:
            self.log("Test 4.1 - Re-import CSV A", False, f"Import failed: {r.status_code}", r.text)
            return
        
        data = r.json()
        
        # Verify inserted=0
        if data.get("inserted") != 0:
            self.log("Test 4.1 - Re-import CSV A", False, 
                    f"Expected inserted=0, got {data.get('inserted')}", data)
            return
        
        self.log("Test 4.1 - Re-import CSV A", True, 
                f"Inserted 0 (idempotent)")
        
        # Verify original_transaction_date stays 2024-10-07 (no flip-flop corruption)
        transactions = self.get_transactions()
        order_1_income = [t for t in transactions if t.get("order_id") == ORDER_1 and t.get("type") == "income"]
        
        if len(order_1_income) != 1:
            self.log("Test 4.2 - No Date Flip-Flop", False, 
                    f"Expected 1 income record for {ORDER_1}, got {len(order_1_income)}")
            return
        
        tx = order_1_income[0]
        
        # Verify original_transaction_date still = 2024-10-07
        if tx.get("original_transaction_date") != DATE_1:
            self.log("Test 4.2 - No Date Flip-Flop", False, 
                    f"DATE FLIP-FLOP CORRUPTION! Expected original_transaction_date={DATE_1}, got {tx.get('original_transaction_date')}", tx)
            return
        
        # Verify date still = 2024-10-07
        if tx.get("date") != DATE_1:
            self.log("Test 4.2 - No Date Flip-Flop", False, 
                    f"DATE FLIP-FLOP CORRUPTION! Expected date={DATE_1}, got {tx.get('date')}", tx)
            return
        
        self.log("Test 4.2 - No Date Flip-Flop", True, 
                f"original_transaction_date stays {DATE_1} (no flip-flop corruption)")
    
    def test_5_import_history(self):
        """TEST 5: Verify import history endpoint"""
        print("\n=== TEST 5: IMPORT HISTORY ===")
        
        history = self.get_import_history()
        
        if len(history) < 5:  # We did 5 imports (3x CSV A, 2x CSV B)
            self.log("Test 5.1 - Import History Count", False, 
                    f"Expected at least 5 batch records, got {len(history)}", history)
            return
        
        self.log("Test 5.1 - Import History Count", True, 
                f"Found {len(history)} batch records")
        
        # Verify batch records have correct structure
        for i, batch in enumerate(history[:3]):  # Check first 3
            if not batch.get("id"):
                self.log(f"Test 5.2.{i+1} - Batch Structure", False, 
                        f"Batch missing 'id' field", batch)
                return
            
            if not batch.get("file_name"):
                self.log(f"Test 5.2.{i+1} - Batch Structure", False, 
                        f"Batch missing 'file_name' field", batch)
                return
            
            if batch.get("status") != "completed":
                self.log(f"Test 5.2.{i+1} - Batch Structure", False, 
                        f"Expected status='completed', got {batch.get('status')}", batch)
                return
            
            # Check counts exist
            required_fields = ["new", "existing_unchanged", "existing_updated", "date_changed", "inserted"]
            for field in required_fields:
                if field not in batch:
                    self.log(f"Test 5.2.{i+1} - Batch Structure", False, 
                            f"Batch missing '{field}' field", batch)
                    return
        
        self.log("Test 5.2 - Batch Structure", True, 
                f"All batch records have correct structure (id, file_name, status, counts)")
        
        # Verify report_date_min/max
        for i, batch in enumerate(history[:3]):
            if not batch.get("report_date_min") or not batch.get("report_date_max"):
                self.log(f"Test 5.3.{i+1} - Report Date Range", False, 
                        f"Batch missing report_date_min/max", batch)
                return
        
        self.log("Test 5.3 - Report Date Range", True, 
                f"All batches have report_date_min/max")
    
    def test_6_dashboard_date_filtering(self):
        """TEST 6: Verify dashboard date filtering uses original date"""
        print("\n=== TEST 6: DASHBOARD DATE FILTERING ===")
        
        # Filter: 2024-10-07 to 2024-10-09 (should include Order 1 with original date 2024-10-07)
        summary = self.get_dashboard_summary(start_date=DATE_1, end_date=DATE_2)
        
        if not summary:
            self.log("Test 6.1 - Date Filtering", False, "Failed to get dashboard summary")
            return
        
        revenue = summary.get("revenue", 0)
        count = summary.get("transaction_count", 0)
        
        # Expected: Order 1 (100) + Refund (-20) in this range
        # Order 1 should be included because its ORIGINAL date is 2024-10-07, even though latest_amazon_reported_date is 2024-10-11
        if revenue != 100:
            self.log("Test 6.1 - Date Filtering", False, 
                    f"Expected revenue=100 (Order 1 in date range using original date), got {revenue}. Original date NOT used for filtering!", summary)
            return
        
        if count != 2:
            self.log("Test 6.1 - Date Filtering", False, 
                    f"Expected count=2 (Order 1 + Refund), got {count}", summary)
            return
        
        self.log("Test 6.1 - Date Filtering", True, 
                f"Date filtering uses original date (revenue=100, count=2 in range {DATE_1} to {DATE_2})")
    
    def test_7_regression(self):
        """TEST 7: Run existing finance regression suite"""
        print("\n=== TEST 7: FINANCE REGRESSION SUITE ===")
        
        # Run the existing regression tests
        import subprocess
        result = subprocess.run(
            ["python", "-m", "pytest", "/app/backend/tests/test_finance_regression.py", "-v"],
            capture_output=True,
            text=True,
            env={**os.environ, "REACT_APP_BACKEND_URL": BASE_URL}
        )
        
        if result.returncode != 0:
            self.log("Test 7 - Finance Regression", False, 
                    f"Regression tests failed with exit code {result.returncode}", 
                    result.stdout + "\n" + result.stderr)
            return
        
        # Parse output for pass/fail count
        output = result.stdout + result.stderr
        if "passed" in output:
            self.log("Test 7 - Finance Regression", True, 
                    f"All regression tests passed")
        else:
            self.log("Test 7 - Finance Regression", False, 
                    f"Regression tests output unclear", output)
    
    def test_8_preview_mode(self):
        """TEST 8: Verify preview mode (commit=false) doesn't write"""
        print("\n=== TEST 8: PREVIEW MODE ===")
        
        # Create a new CSV with unique order ID
        order_preview = f"702-TEST-PREVIEW-{uuid.uuid4().hex[:6]}"
        csv_preview = f"""date/time,type,order id,description,total
{DATE_1},Order,{order_preview},Preview Order,999.00
"""
        
        # Import with commit=false
        r = self.import_csv(csv_preview, commit=False)
        if r.status_code != 200:
            self.log("Test 8.1 - Preview Import", False, f"Import failed: {r.status_code}", r.text)
            return
        
        data = r.json()
        
        # Verify committed=false
        if data.get("committed") != False:
            self.log("Test 8.1 - Preview Import", False, 
                    f"Expected committed=false, got {data.get('committed')}", data)
            return
        
        # Verify inserted=0 (nothing written)
        if data.get("inserted") != 0:
            self.log("Test 8.1 - Preview Import", False, 
                    f"Expected inserted=0 in preview mode, got {data.get('inserted')}", data)
            return
        
        # Verify accepted=1 (parsed successfully)
        if data.get("accepted") != 1:
            self.log("Test 8.1 - Preview Import", False, 
                    f"Expected accepted=1, got {data.get('accepted')}", data)
            return
        
        self.log("Test 8.1 - Preview Import", True, 
                f"Preview mode: committed=false, inserted=0, accepted=1")
        
        # Verify no transaction was created
        transactions = self.get_transactions()
        preview_txs = [t for t in transactions if t.get("order_id") == order_preview]
        
        if len(preview_txs) > 0:
            self.log("Test 8.2 - No Data Written", False, 
                    f"Preview mode wrote data! Found {len(preview_txs)} transactions with order_id={order_preview}", preview_txs)
            return
        
        self.log("Test 8.2 - No Data Written", True, 
                f"No transactions written in preview mode")
        
        # Verify no batch record was created
        history = self.get_import_history()
        preview_batches = [b for b in history if order_preview in str(b)]
        
        if len(preview_batches) > 0:
            self.log("Test 8.3 - No Batch Record", False, 
                    f"Preview mode created batch record!", preview_batches)
            return
        
        self.log("Test 8.3 - No Batch Record", True, 
                f"No batch record created in preview mode")
    
    def run_all_tests(self):
        """Run all tests"""
        print("\n" + "="*80)
        print("PHASE A AMAZON IMPORT RECONCILIATION - COMPREHENSIVE BACKEND TESTING")
        print("="*80)
        
        if not self.setup():
            print("\n❌ Setup failed, cannot continue")
            return
        
        try:
            self.test_1_same_file_twice()
            self.test_2_overlapping_with_date_change()
            self.test_3_reimport_b_again()
            self.test_4_reimport_original_a()
            self.test_5_import_history()
            self.test_6_dashboard_date_filtering()
            self.test_7_regression()
            self.test_8_preview_mode()
        finally:
            self.teardown()
        
        # Print summary
        print("\n" + "="*80)
        print("TEST SUMMARY")
        print("="*80)
        
        passed = sum(1 for r in self.results if r["passed"])
        total = len(self.results)
        
        print(f"\nTotal: {passed}/{total} tests passed ({passed*100//total if total > 0 else 0}%)\n")
        
        for result in self.results:
            status = "✅" if result["passed"] else "❌"
            print(f"{status} {result['test']}")
            if result["message"]:
                print(f"   {result['message']}")
        
        print("\n" + "="*80)
        
        return passed, total


if __name__ == "__main__":
    tester = TestReconciliation()
    passed, total = tester.run_all_tests()
    
    # Exit with appropriate code
    exit(0 if passed == total else 1)
