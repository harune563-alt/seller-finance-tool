"""
FINAL COMPREHENSIVE TEST REPORT
Amazon Orders / Fulfillment Import Metadata Enrichment

This test suite verifies the fix in backend/amazon_orders_import.py that enriches
EXISTING financial transactions with fulfillment metadata when importing All Orders TSV.

CRITICAL FIX VERIFIED:
- The TransactionOut model in server.py was missing the fulfillment fields
- Added: fulfillment_type, fulfillment_last_updated_at, amazon_order_item_ids
- These fields are now properly written to DB and returned in API responses
"""
import requests
import io
import uuid

BASE_URL = "https://sellerfin-tool.preview.emergentagent.com/api"
session = requests.Session()

def unique_id():
    return uuid.uuid4().hex[:8].upper()

# Login
resp = session.post(f"{BASE_URL}/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})
assert resp.status_code == 200
print("✓ Logged in as admin@amzsuite.com\n")

test_results = []

# ============================================================================
# TEST 1: Basic Metadata Enrichment
# ============================================================================
print("="*80)
print("TEST 1: Basic Metadata Enrichment (Income Transaction)")
print("="*80)

store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST1_{unique_id()}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
order_id = f"TEST1-{unique_id()}"
item_id = f"ITEM1-{unique_id()}"

# Import Amazon Payments CSV to create INCOME transaction
csv = f"""date/time,settlement id,type,order id,total
2024-10-15T10:00:00+00:00,123,Order,{order_id},100.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

# Get transaction BEFORE
txs_before = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
tx_before = txs_before[0]
original_amount = tx_before['amount']
original_date = tx_before['date']
original_type = tx_before['type']
count_before = len(txs_before)

print(f"✓ Transaction BEFORE: amount={original_amount}, date={original_date}, type={original_type}")
print(f"  fulfillment_type: {tx_before.get('fulfillment_type')}")

# Import All Orders TSV with FBA fulfillment
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_id}\t{item_id}\tAmazon\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
result = session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files).json()

# Get transaction AFTER
txs_after = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
tx_after = txs_after[0]
count_after = len(txs_after)

print(f"\n✓ Transaction AFTER:")
print(f"  fulfillment_type: {tx_after.get('fulfillment_type')}")
print(f"  fulfillment_last_updated_at: {tx_after.get('fulfillment_last_updated_at')}")
print(f"  amazon_order_item_ids: {tx_after.get('amazon_order_item_ids')}")

# VERIFY
try:
    assert tx_after.get('fulfillment_type') == 'FBA', f"Expected FBA, got {tx_after.get('fulfillment_type')}"
    assert tx_after.get('fulfillment_last_updated_at') is not None, "fulfillment_last_updated_at not set"
    assert tx_after.get('amazon_order_item_ids') == [item_id], f"Expected [{item_id}], got {tx_after.get('amazon_order_item_ids')}"
    assert tx_after['amount'] == original_amount, f"Amount changed: {original_amount} -> {tx_after['amount']}"
    assert tx_after['date'] == original_date, f"Date changed: {original_date} -> {tx_after['date']}"
    assert tx_after['type'] == original_type, f"Type changed: {original_type} -> {tx_after['type']}"
    assert count_after == count_before, f"Transaction count changed: {count_before} -> {count_after}"
    print("\n✅ TEST 1 PASSED")
    test_results.append(("Test 1: Basic Metadata Enrichment", "PASSED"))
except AssertionError as e:
    print(f"\n❌ TEST 1 FAILED: {e}")
    test_results.append(("Test 1: Basic Metadata Enrichment", f"FAILED: {e}"))

session.delete(f"{BASE_URL}/stores/{store_id}")

# ============================================================================
# TEST 2: Idempotent Re-import
# ============================================================================
print("\n" + "="*80)
print("TEST 2: Idempotent Re-import")
print("="*80)

store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST2_{unique_id()}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
order_id = f"TEST2-{unique_id()}"
item_id = f"ITEM2-{unique_id()}"

# Import CSV
csv = f"""date/time,settlement id,type,order id,total
2024-10-16T10:00:00+00:00,123,Order,{order_id},75.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

# Import All Orders (first time)
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_id}\t{item_id}\tAmazon\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files)

txs_first = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
count_first = len(txs_first)
print(f"✓ After first import: count={count_first}, fulfillment_type={txs_first[0].get('fulfillment_type')}")

# Re-import SAME file (second time)
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files)

txs_second = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
count_second = len(txs_second)
print(f"✓ After second import: count={count_second}, fulfillment_type={txs_second[0].get('fulfillment_type')}")

# VERIFY
try:
    assert count_second == count_first, f"Count changed: {count_first} -> {count_second}"
    assert len(txs_second) == 1, f"Expected 1 transaction, got {len(txs_second)}"
    assert txs_second[0].get('fulfillment_type') == 'FBA', f"Expected FBA, got {txs_second[0].get('fulfillment_type')}"
    assert txs_second[0].get('amazon_order_item_ids') == [item_id], "Item IDs not preserved"
    print("\n✅ TEST 2 PASSED")
    test_results.append(("Test 2: Idempotent Re-import", "PASSED"))
except AssertionError as e:
    print(f"\n❌ TEST 2 FAILED: {e}")
    test_results.append(("Test 2: Idempotent Re-import", f"FAILED: {e}"))

session.delete(f"{BASE_URL}/stores/{store_id}")

# ============================================================================
# TEST 3: Unmatched Order - No Writes
# ============================================================================
print("\n" + "="*80)
print("TEST 3: Unmatched Order - No Writes to Transactions")
print("="*80)

store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST3_{unique_id()}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
order_a = f"TEST3A-{unique_id()}"
order_b = f"TEST3B-{unique_id()}"  # This order will have NO transaction

# Import CSV for order A only
csv = f"""date/time,settlement id,type,order id,total
2024-10-17T10:00:00+00:00,123,Order,{order_a},100.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

count_before = len(session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json())
print(f"✓ Transaction count before All Orders: {count_before}")

# Import All Orders for BOTH orders (A has transaction, B does not)
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_a}\tITEM-A\tAmazon\t1\tShipped
{order_b}\tITEM-B\tMerchant\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
result = session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files).json()

count_after = len(session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json())
print(f"✓ Transaction count after All Orders: {count_after}")
print(f"✓ All Orders result: matched={result.get('matched')}, unmatched={result.get('unmatched')}")

# VERIFY
try:
    assert count_after == count_before, f"Count changed: {count_before} -> {count_after}"
    # Order B should be unmatched (no canonical order exists because no transaction was imported)
    assert result.get('unmatched') == 1, f"Expected 1 unmatched, got {result.get('unmatched')}"
    assert result.get('matched') == 1, f"Expected 1 matched, got {result.get('matched')}"
    print("\n✅ TEST 3 PASSED")
    test_results.append(("Test 3: Unmatched Order - No Writes", "PASSED"))
except AssertionError as e:
    print(f"\n❌ TEST 3 FAILED: {e}")
    test_results.append(("Test 3: Unmatched Order - No Writes", f"FAILED: {e}"))

session.delete(f"{BASE_URL}/stores/{store_id}")

# ============================================================================
# TEST 4: Both Income and Expense Receive Metadata
# ============================================================================
print("\n" + "="*80)
print("TEST 4: Both Income and Expense Receive Metadata")
print("="*80)

store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST4_{unique_id()}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
order_id = f"TEST4-{unique_id()}"
item_id = f"ITEM4-{unique_id()}"

# Import CSV with BOTH income and expense (refund)
csv = f"""date/time,settlement id,type,order id,sku,description,quantity,marketplace,account type,fulfillment,order city,order state,order postal,product sales,product sales tax,shipping credits,shipping credits tax,gift wrap credits,giftwrap credits tax,Regulatory Fee,Tax On Regulatory Fee,promotional rebates,promotional rebates tax,marketplace withheld tax,selling fees,fba fees,other transaction fees,other,total
2024-10-18T10:00:00+00:00,123,Order,{order_id},SKU1,Product,1,Amazon.com,Merchant,AFN,Seattle,WA,98101,120.00,0,0,0,0,0,0,0,0,0,0,-5.00,-3.00,0,0,112.00
2024-10-18T10:05:00+00:00,123,Refund,{order_id},SKU1,Product,1,Amazon.com,Merchant,AFN,Seattle,WA,98101,-30.00,0,0,0,0,0,0,0,0,0,0,0,2.00,1.00,0,0,-27.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
result = session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files).json()
print(f"✓ Imported CSV: inserted={result.get('inserted')}")

# Import All Orders
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_id}\t{item_id}\tMerchant\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files)

txs = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
income_tx = [tx for tx in txs if tx['type'] == 'income'][0]
expense_tx = [tx for tx in txs if tx['type'] == 'expense'][0]

print(f"✓ Income: fulfillment_type={income_tx.get('fulfillment_type')}, item_ids={income_tx.get('amazon_order_item_ids')}")
print(f"✓ Expense: fulfillment_type={expense_tx.get('fulfillment_type')}, item_ids={expense_tx.get('amazon_order_item_ids')}")

# VERIFY
try:
    assert income_tx.get('fulfillment_type') == 'FBM', f"Income expected FBM, got {income_tx.get('fulfillment_type')}"
    assert expense_tx.get('fulfillment_type') == 'FBM', f"Expense expected FBM, got {expense_tx.get('fulfillment_type')}"
    assert income_tx.get('amazon_order_item_ids') == [item_id], "Income item IDs incorrect"
    assert expense_tx.get('amazon_order_item_ids') == [item_id], "Expense item IDs incorrect"
    assert income_tx.get('fulfillment_last_updated_at') is not None, "Income timestamp not set"
    assert expense_tx.get('fulfillment_last_updated_at') is not None, "Expense timestamp not set"
    print("\n✅ TEST 4 PASSED")
    test_results.append(("Test 4: Both Income and Expense", "PASSED"))
except AssertionError as e:
    print(f"\n❌ TEST 4 FAILED: {e}")
    test_results.append(("Test 4: Both Income and Expense", f"FAILED: {e}"))

session.delete(f"{BASE_URL}/stores/{store_id}")

# ============================================================================
# TEST 5: Classification Integrity (Cancelled Zero-Qty Ignored)
# ============================================================================
print("\n" + "="*80)
print("TEST 5: Classification Integrity (Cancelled Zero-Qty Ignored)")
print("="*80)

store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST5_{unique_id()}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
order_id = f"TEST5-{unique_id()}"

# Import CSV
csv = f"""date/time,settlement id,type,order id,total
2024-10-19T10:00:00+00:00,123,Order,{order_id},80.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

# Import All Orders with TWO items: Shipped FBA (qty=1) + Cancelled FBM (qty=0)
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status\titem-status
{order_id}\tITEM-A\tAmazon\t1\tShipped\tShipped
{order_id}\tITEM-B\tMerchant\t0\tCancelled\tCancelled
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files)

tx = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()[0]
print(f"✓ Transaction: fulfillment_type={tx.get('fulfillment_type')}, item_ids={tx.get('amazon_order_item_ids')}")

# VERIFY: Should be FBA (cancelled zero-qty Merchant item ignored in classification)
try:
    assert tx.get('fulfillment_type') == 'FBA', f"Expected FBA, got {tx.get('fulfillment_type')}"
    assert 'ITEM-A' in tx.get('amazon_order_item_ids', []), "Active item ID missing"
    assert 'ITEM-B' in tx.get('amazon_order_item_ids', []), "Cancelled item ID missing"
    print("\n✅ TEST 5 PASSED")
    test_results.append(("Test 5: Classification Integrity", "PASSED"))
except AssertionError as e:
    print(f"\n❌ TEST 5 FAILED: {e}")
    test_results.append(("Test 5: Classification Integrity", f"FAILED: {e}"))

session.delete(f"{BASE_URL}/stores/{store_id}")

# ============================================================================
# TEST 6: Dashboard Summary Unchanged (Financial Safety)
# ============================================================================
print("\n" + "="*80)
print("TEST 6: Dashboard Summary Unchanged (Financial Safety)")
print("="*80)

store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST6_{unique_id()}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
order_1 = f"TEST6A-{unique_id()}"
order_2 = f"TEST6B-{unique_id()}"

# Import CSV with multiple transactions
csv = f"""date/time,settlement id,type,order id,total
2024-10-20T10:00:00+00:00,123,Order,{order_1},150.00
2024-10-21T10:00:00+00:00,124,Order,{order_2},200.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

# Get dashboard BEFORE
summary_before = session.get(f"{BASE_URL}/dashboard/summary", params={"store_id": store_id}).json()
revenue_before = summary_before.get('revenue')
expenses_before = summary_before.get('expenses')
net_before = summary_before.get('net_profit')
count_before = summary_before.get('transaction_count')
print(f"✓ BEFORE: revenue={revenue_before}, expenses={expenses_before}, net={net_before}, count={count_before}")

# Import All Orders
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_1}\tITEM-1\tAmazon\t1\tShipped
{order_2}\tITEM-2\tMerchant\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files)

# Get dashboard AFTER
summary_after = session.get(f"{BASE_URL}/dashboard/summary", params={"store_id": store_id}).json()
revenue_after = summary_after.get('revenue')
expenses_after = summary_after.get('expenses')
net_after = summary_after.get('net_profit')
count_after = summary_after.get('transaction_count')
print(f"✓ AFTER:  revenue={revenue_after}, expenses={expenses_after}, net={net_after}, count={count_after}")

# VERIFY
try:
    assert revenue_after == revenue_before, f"Revenue changed: {revenue_before} -> {revenue_after}"
    assert expenses_after == expenses_before, f"Expenses changed: {expenses_before} -> {expenses_after}"
    assert net_after == net_before, f"Net profit changed: {net_before} -> {net_after}"
    assert count_after == count_before, f"Count changed: {count_before} -> {count_after}"
    print("\n✅ TEST 6 PASSED")
    test_results.append(("Test 6: Dashboard Summary Unchanged", "PASSED"))
except AssertionError as e:
    print(f"\n❌ TEST 6 FAILED: {e}")
    test_results.append(("Test 6: Dashboard Summary Unchanged", f"FAILED: {e}"))

session.delete(f"{BASE_URL}/stores/{store_id}")

# ============================================================================
# FINAL SUMMARY
# ============================================================================
print("\n" + "="*80)
print("FINAL TEST SUMMARY")
print("="*80)
for test_name, status in test_results:
    icon = "✅" if status == "PASSED" else "❌"
    print(f"{icon} {test_name}: {status}")

passed = sum(1 for _, status in test_results if status == "PASSED")
total = len(test_results)
print(f"\nTotal: {passed}/{total} tests passed")

if passed == total:
    print("\n🎉 ALL TESTS PASSED! 🎉")
    print("\nThe Amazon Orders / Fulfillment Import metadata enrichment fix is working correctly.")
    print("All 6 minimum test requirements verified successfully.")
    print("\nFIX SUMMARY:")
    print("- Added fulfillment_type, fulfillment_last_updated_at, amazon_order_item_ids to TransactionOut model")
    print("- Metadata enrichment working correctly for existing transactions")
    print("- No financial fields modified (amounts, dates, costs unchanged)")
    print("- No duplicate transactions created")
    print("- Dashboard totals remain unchanged")
else:
    print(f"\n⚠️  {total - passed} test(s) failed.")

print("="*80)
