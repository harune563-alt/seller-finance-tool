"""
Amazon Orders / Fulfillment Import Module Testing
Tests the NEW standalone module per user specification.

Required Tests:
1. fulfillment-channel=Amazon → fulfillment_type=FBA
2. fulfillment-channel=Merchant → fulfillment_type=FBM
3. Same report twice → no duplicates
4. One order with two order-item-ids → both preserved
5. Shipped qty=1 Amazon + Cancelled qty=0 Merchant → FBA (active wins)
6. No canonical order → unmatched, no financial order created
7. Different marketplace text → match still succeeds by order id

Financial Safety:
- No changes to transactions collection
- No changes to Amazon Payments totals
- No changes to SellerFlash data
"""
import requests
import io
import time
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://5d01db41-b7e9-4610-9ea6-2c471b5d6d10.preview.emergentagent.com/api"

# Test credentials
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

# Test store name prefix for cleanup
TEST_STORE_PREFIX = "TEST_ORDERS_IMPORT_"

class TestSession:
    def __init__(self):
        self.session = requests.Session()
        self.token = None
        self.user_id = None
        self.store_id = None
        self.test_store_name = f"{TEST_STORE_PREFIX}{int(time.time())}"
        
    def login(self):
        """Login and get auth token"""
        resp = self.session.post(f"{BASE_URL}/auth/login", json={
            "email": ADMIN_EMAIL,
            "password": ADMIN_PASSWORD
        })
        assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
        data = resp.json()
        self.token = data["token"]
        self.user_id = data["id"]
        print(f"✓ Logged in as {ADMIN_EMAIL}")
        return data
    
    def create_store(self):
        """Create a test store"""
        resp = self.session.post(f"{BASE_URL}/stores", json={
            "name": self.test_store_name,
            "marketplaces": ["US"],
            "default_currency": "USD"
        })
        assert resp.status_code == 200, f"Store creation failed: {resp.status_code} {resp.text}"
        data = resp.json()
        self.store_id = data["id"]
        print(f"✓ Created test store: {self.test_store_name} (ID: {self.store_id})")
        return data
    
    def import_amazon_payments_csv(self, csv_content, marketplace="US"):
        """Import Amazon Payments CSV to create canonical orders"""
        files = {
            'file': ('payments.csv', io.BytesIO(csv_content.encode('utf-8')), 'text/csv')
        }
        params = {
            'store_id': self.store_id,
            'marketplace': marketplace,
            'commit': 'true'
        }
        resp = self.session.post(f"{BASE_URL}/transactions/import", files=files, params=params)
        assert resp.status_code == 200, f"Amazon Payments import failed: {resp.status_code} {resp.text}"
        data = resp.json()
        print(f"✓ Imported Amazon Payments CSV: {data['inserted']} inserted, {data['accepted']} accepted")
        return data
    
    def import_all_orders(self, tsv_content, commit=False):
        """Import All Orders report"""
        files = {
            'file': ('all_orders.txt', io.BytesIO(tsv_content.encode('utf-8')), 'text/plain')
        }
        params = {
            'commit': 'true' if commit else 'false'
        }
        resp = self.session.post(f"{BASE_URL}/amazon-orders/import", files=files, params=params)
        assert resp.status_code == 200, f"All Orders import failed: {resp.status_code} {resp.text}"
        data = resp.json()
        return data
    
    def get_order_items(self, order_id):
        """Get items for a specific order"""
        resp = self.session.get(f"{BASE_URL}/amazon-orders/items", params={"order_id": order_id})
        assert resp.status_code == 200, f"Get order items failed: {resp.status_code} {resp.text}"
        return resp.json()
    
    def get_unmatched_orders(self):
        """Get unmatched orders"""
        resp = self.session.get(f"{BASE_URL}/amazon-orders/unmatched")
        assert resp.status_code == 200, f"Get unmatched failed: {resp.status_code} {resp.text}"
        return resp.json()
    
    def get_import_history(self):
        """Get import history"""
        resp = self.session.get(f"{BASE_URL}/amazon-orders/history")
        assert resp.status_code == 200, f"Get history failed: {resp.status_code} {resp.text}"
        return resp.json()
    
    def get_transactions_count(self):
        """Get count of transactions"""
        resp = self.session.get(f"{BASE_URL}/transactions", params={"store_id": self.store_id, "limit": 10000})
        assert resp.status_code == 200, f"Get transactions failed: {resp.status_code} {resp.text}"
        return len(resp.json())
    
    def cleanup(self):
        """Delete test store and all associated data"""
        if self.store_id:
            resp = self.session.delete(f"{BASE_URL}/stores/{self.store_id}")
            if resp.status_code == 200:
                print(f"✓ Cleaned up test store: {self.test_store_name}")
            else:
                print(f"⚠ Failed to cleanup store: {resp.status_code} {resp.text}")


def create_amazon_payments_csv(orders):
    """Create Amazon Payments CSV with given orders"""
    lines = [
        "date/time,settlement id,type,order id,sku,description,quantity,marketplace,account type,fulfillment,order city,order state,order postal,product sales,product sales tax,shipping credits,shipping credits tax,gift wrap credits,giftwrap credits tax,promotional rebates,promotional rebates tax,marketplace withheld tax,selling fees,fba fees,other transaction fees,other,total"
    ]
    for order in orders:
        lines.append(
            f"{order['date']},,Order,{order['order_id']},{order.get('sku', 'TEST-SKU')},{order.get('description', 'Test Product')},{order.get('quantity', '1')},Amazon.com,Merchant,{order.get('fulfillment', 'AFN')},,,,{order['amount']},0,0,0,0,0,0,0,0,0,0,0,0,{order['amount']}"
        )
    return "\n".join(lines)


def create_all_orders_tsv(items):
    """Create All Orders TSV with given items"""
    lines = [
        "amazon-order-id\tmerchant-order-id\tpurchase-date\tlast-updated-date\torder-status\tfulfillment-channel\tsales-channel\tproduct-name\tsku\tasin\titem-status\tquantity\tcurrency\titem-price\titem-tax\tshipping-price\tshipping-tax\torder-item-id"
    ]
    for item in items:
        lines.append(
            f"{item['amazon_order_id']}\t{item.get('merchant_order_id', '')}\t{item.get('purchase_date', '2024-10-01T10:00:00Z')}\t{item.get('last_updated_date', '2024-10-01T10:00:00Z')}\t{item.get('order_status', 'Shipped')}\t{item['fulfillment_channel']}\t{item.get('sales_channel', 'Amazon.com')}\t{item.get('product_name', 'Test Product')}\t{item.get('sku', 'TEST-SKU')}\t{item.get('asin', 'B00TEST123')}\t{item.get('item_status', 'Shipped')}\t{item['quantity']}\t{item.get('currency', 'USD')}\t{item.get('item_price', '10.00')}\t{item.get('item_tax', '0.00')}\t{item.get('shipping_price', '0.00')}\t{item.get('shipping_tax', '0.00')}\t{item['order_item_id']}"
        )
    return "\n".join(lines)


def run_tests():
    """Run all tests"""
    session = TestSession()
    test_results = []
    
    try:
        # Setup
        print("\n=== SETUP ===")
        session.login()
        session.create_store()
        
        # Create canonical orders by importing Amazon Payments CSV
        print("\n=== Creating Canonical Orders ===")
        payments_csv = create_amazon_payments_csv([
            {"order_id": "111-1111111-1111111", "date": "2024-10-01T10:00:00Z", "amount": "25.00", "sku": "SKU-FBA-001", "quantity": "1"},
            {"order_id": "222-2222222-2222222", "date": "2024-10-02T10:00:00Z", "amount": "30.00", "sku": "SKU-FBM-001", "quantity": "1"},
            {"order_id": "333-3333333-3333333", "date": "2024-10-03T10:00:00Z", "amount": "40.00", "sku": "SKU-MULTI-001", "quantity": "2"},
            {"order_id": "444-4444444-4444444", "date": "2024-10-04T10:00:00Z", "amount": "50.00", "sku": "SKU-MIXED-001", "quantity": "1"},
            {"order_id": "555-5555555-5555555", "date": "2024-10-05T10:00:00Z", "amount": "60.00", "sku": "SKU-MARKET-001", "quantity": "1"},
        ])
        payments_result = session.import_amazon_payments_csv(payments_csv)
        
        # Record initial transactions count for financial safety check
        initial_tx_count = session.get_transactions_count()
        print(f"✓ Initial transactions count: {initial_tx_count}")
        
        # TEST 1: fulfillment-channel=Amazon → fulfillment_type=FBA
        print("\n=== TEST 1: Amazon fulfillment → FBA ===")
        all_orders_1 = create_all_orders_tsv([
            {
                "amazon_order_id": "111-1111111-1111111",
                "order_item_id": "11111111111111",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "sku": "SKU-FBA-001"
            }
        ])
        result_1 = session.import_all_orders(all_orders_1, commit=True)
        assert result_1["matched"] == 1, f"Expected 1 matched, got {result_1['matched']}"
        assert result_1["new"] == 1, f"Expected 1 new, got {result_1['new']}"
        assert result_1["fba_items"] == 1, f"Expected 1 FBA item, got {result_1['fba_items']}"
        
        # Verify fulfillment_type on canonical order
        order_items_1 = session.get_order_items("111-1111111-1111111")
        assert len(order_items_1["canonical_orders"]) == 1, "Expected 1 canonical order"
        assert order_items_1["canonical_orders"][0]["fulfillment_type"] == "FBA", f"Expected FBA, got {order_items_1['canonical_orders'][0].get('fulfillment_type')}"
        print(f"✓ TEST 1 PASSED: fulfillment_type=FBA for Amazon fulfillment")
        test_results.append(("TEST 1: Amazon → FBA", "PASS"))
        
        # TEST 2: fulfillment-channel=Merchant → fulfillment_type=FBM
        print("\n=== TEST 2: Merchant fulfillment → FBM ===")
        all_orders_2 = create_all_orders_tsv([
            {
                "amazon_order_id": "222-2222222-2222222",
                "order_item_id": "22222222222222",
                "fulfillment_channel": "Merchant",
                "quantity": "1",
                "sku": "SKU-FBM-001"
            }
        ])
        result_2 = session.import_all_orders(all_orders_2, commit=True)
        assert result_2["matched"] == 1, f"Expected 1 matched, got {result_2['matched']}"
        assert result_2["fbm_items"] == 1, f"Expected 1 FBM item, got {result_2['fbm_items']}"
        
        order_items_2 = session.get_order_items("222-2222222-2222222")
        assert order_items_2["canonical_orders"][0]["fulfillment_type"] == "FBM", f"Expected FBM, got {order_items_2['canonical_orders'][0].get('fulfillment_type')}"
        print(f"✓ TEST 2 PASSED: fulfillment_type=FBM for Merchant fulfillment")
        test_results.append(("TEST 2: Merchant → FBM", "PASS"))
        
        # TEST 3: Same report twice → no duplicates
        print("\n=== TEST 3: Idempotency - same report twice ===")
        all_orders_3 = create_all_orders_tsv([
            {
                "amazon_order_id": "111-1111111-1111111",
                "order_item_id": "11111111111111",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "sku": "SKU-FBA-001"
            }
        ])
        result_3_first = session.import_all_orders(all_orders_3, commit=True)
        result_3_second = session.import_all_orders(all_orders_3, commit=True)
        
        assert result_3_second["new"] == 0, f"Expected 0 new on second import, got {result_3_second['new']}"
        assert result_3_second["unchanged"] == 1, f"Expected 1 unchanged on second import, got {result_3_second['unchanged']}"
        
        # Verify no duplicate items in DB
        order_items_3 = session.get_order_items("111-1111111-1111111")
        assert order_items_3["total"] == 1, f"Expected 1 item total, got {order_items_3['total']} (duplicates detected!)"
        print(f"✓ TEST 3 PASSED: No duplicates on re-import")
        test_results.append(("TEST 3: Idempotency", "PASS"))
        
        # TEST 4: One order with two different order-item-ids → both preserved
        print("\n=== TEST 4: Multiple items per order ===")
        all_orders_4 = create_all_orders_tsv([
            {
                "amazon_order_id": "333-3333333-3333333",
                "order_item_id": "33333333333331",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "sku": "SKU-MULTI-001"
            },
            {
                "amazon_order_id": "333-3333333-3333333",
                "order_item_id": "33333333333332",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "sku": "SKU-MULTI-002"
            }
        ])
        result_4 = session.import_all_orders(all_orders_4, commit=True)
        assert result_4["new"] == 2, f"Expected 2 new items, got {result_4['new']}"
        
        order_items_4 = session.get_order_items("333-3333333-3333333")
        assert order_items_4["total"] == 2, f"Expected 2 items for order, got {order_items_4['total']}"
        item_ids = [item["order_item_id"] for item in order_items_4["items"]]
        assert "33333333333331" in item_ids, "First order-item-id not found"
        assert "33333333333332" in item_ids, "Second order-item-id not found"
        print(f"✓ TEST 4 PASSED: Both order-item-ids preserved")
        test_results.append(("TEST 4: Multiple items", "PASS"))
        
        # TEST 5: Shipped qty=1 Amazon + Cancelled qty=0 Merchant → FBA (active wins)
        print("\n=== TEST 5: Active shipped row wins over cancelled ===")
        all_orders_5 = create_all_orders_tsv([
            {
                "amazon_order_id": "444-4444444-4444444",
                "order_item_id": "44444444444441",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "order_status": "Shipped",
                "item_status": "Shipped",
                "sku": "SKU-MIXED-001"
            },
            {
                "amazon_order_id": "444-4444444-4444444",
                "order_item_id": "44444444444442",
                "fulfillment_channel": "Merchant",
                "quantity": "0",
                "order_status": "Cancelled",
                "item_status": "Cancelled",
                "sku": "SKU-MIXED-002"
            }
        ])
        result_5 = session.import_all_orders(all_orders_5, commit=True)
        assert result_5["new"] == 2, f"Expected 2 new items, got {result_5['new']}"
        
        order_items_5 = session.get_order_items("444-4444444-4444444")
        # Classification should be FBA because active shipped Amazon row wins
        assert order_items_5["canonical_orders"][0]["fulfillment_type"] == "FBA", f"Expected FBA (active wins), got {order_items_5['canonical_orders'][0].get('fulfillment_type')}"
        # Verify both items are stored
        assert order_items_5["total"] == 2, f"Expected 2 items stored (including cancelled), got {order_items_5['total']}"
        print(f"✓ TEST 5 PASSED: FBA classification (active shipped wins), cancelled row still stored")
        test_results.append(("TEST 5: Active wins classification", "PASS"))
        
        # TEST 6: No canonical order → unmatched, no financial order created
        print("\n=== TEST 6: Unmatched order (no canonical) ===")
        all_orders_6 = create_all_orders_tsv([
            {
                "amazon_order_id": "999-9999999-9999999",
                "order_item_id": "99999999999999",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "sku": "SKU-UNMATCHED-001"
            }
        ])
        result_6 = session.import_all_orders(all_orders_6, commit=True)
        assert result_6["unmatched"] == 1, f"Expected 1 unmatched, got {result_6['unmatched']}"
        assert result_6["matched"] == 0, f"Expected 0 matched, got {result_6['matched']}"
        
        # Verify appears in unmatched endpoint
        unmatched = session.get_unmatched_orders()
        unmatched_order_ids = [item["amazon_order_id"] for item in unmatched["items"]]
        assert "999-9999999-9999999" in unmatched_order_ids, "Unmatched order not in unmatched list"
        
        # Verify no new transactions created
        current_tx_count = session.get_transactions_count()
        assert current_tx_count == initial_tx_count, f"Transactions count changed! Expected {initial_tx_count}, got {current_tx_count}"
        print(f"✓ TEST 6 PASSED: Unmatched order, no financial transaction created")
        test_results.append(("TEST 6: Unmatched order", "PASS"))
        
        # TEST 7: Different marketplace text → match still succeeds
        print("\n=== TEST 7: Marketplace text differs but match succeeds ===")
        all_orders_7 = create_all_orders_tsv([
            {
                "amazon_order_id": "555-5555555-5555555",
                "order_item_id": "55555555555555",
                "fulfillment_channel": "Amazon",
                "quantity": "1",
                "sku": "SKU-MARKET-001",
                "sales_channel": "Amazon.de"  # Different marketplace text
            }
        ])
        result_7 = session.import_all_orders(all_orders_7, commit=True)
        assert result_7["matched"] == 1, f"Expected 1 matched (by order id only), got {result_7['matched']}"
        assert result_7["new"] == 1, f"Expected 1 new, got {result_7['new']}"
        
        order_items_7 = session.get_order_items("555-5555555-5555555")
        assert len(order_items_7["canonical_orders"]) == 1, "Expected canonical order to exist"
        assert order_items_7["canonical_orders"][0]["marketplace"] == "US", "Canonical order should be US marketplace"
        assert order_items_7["items"][0]["sales_channel"] == "Amazon.de", "Item should preserve Amazon.de sales channel"
        print(f"✓ TEST 7 PASSED: Match by order id only, marketplace text difference ignored")
        test_results.append(("TEST 7: Marketplace text differs", "PASS"))
        
        # FINANCIAL SAFETY CHECKS
        print("\n=== FINANCIAL SAFETY CHECKS ===")
        
        # Check transactions count hasn't changed (except for initial canonical orders)
        final_tx_count = session.get_transactions_count()
        assert final_tx_count == initial_tx_count, f"Transactions count changed! Expected {initial_tx_count}, got {final_tx_count}"
        print(f"✓ Transactions count unchanged: {final_tx_count}")
        test_results.append(("Financial Safety: Transactions unchanged", "PASS"))
        
        # Verify import history
        print("\n=== IMPORT HISTORY ===")
        history = session.get_import_history()
        assert len(history) > 0, "Expected import history records"
        print(f"✓ Import history has {len(history)} records")
        
        # Print summary
        print("\n" + "="*60)
        print("TEST SUMMARY")
        print("="*60)
        for test_name, result in test_results:
            status = "✅" if result == "PASS" else "❌"
            print(f"{status} {test_name}: {result}")
        
        passed = sum(1 for _, r in test_results if r == "PASS")
        total = len(test_results)
        print(f"\nTotal: {passed}/{total} tests passed ({100*passed//total}%)")
        
        if passed == total:
            print("\n🎉 ALL TESTS PASSED!")
        else:
            print(f"\n⚠️  {total - passed} test(s) failed")
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        test_results.append(("Current test", "FAIL"))
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        raise
    finally:
        # Cleanup
        print("\n=== CLEANUP ===")
        session.cleanup()


if __name__ == "__main__":
    run_tests()
