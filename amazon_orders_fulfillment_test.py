"""
Amazon Orders / Fulfillment Import Metadata Enrichment Test Suite

Tests the focused fix in backend/amazon_orders_import.py that enriches EXISTING
financial transactions with fulfillment metadata (fulfillment_type, 
fulfillment_last_updated_at, amazon_order_item_ids) when importing All Orders TSV.

CRITICAL RULES:
- NEVER insert/upsert into transactions collection
- NEVER touch amounts, dates, costs, or financial fields
- ONLY write metadata for matched orders (orders with existing transactions)
- NEVER write anything for unmatched orders
"""
import requests
import json
import io
from datetime import datetime

BASE_URL = "https://fba-finance-hub.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

session = requests.Session()

def login():
    """Login and get session cookie"""
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    print(f"✓ Logged in as {ADMIN_EMAIL}")
    return resp.json()

def create_test_store():
    """Create a dedicated test store"""
    resp = session.post(f"{BASE_URL}/stores", json={
        "name": "TEST_FULFILLMENT_STORE",
        "marketplaces": ["US"],
        "default_currency": "USD"
    })
    assert resp.status_code == 200, f"Store creation failed: {resp.status_code} {resp.text}"
    store = resp.json()
    print(f"✓ Created test store: {store['id']}")
    return store

def create_amazon_payments_csv(order_id, amount, date="2024-10-15"):
    """Create Amazon Payments CSV with one INCOME transaction"""
    csv_content = f"""date/time,settlement id,type,order id,sku,description,quantity,marketplace,account type,fulfillment,order city,order state,order postal,product sales,product sales tax,shipping credits,shipping credits tax,gift wrap credits,giftwrap credits tax,Regulatory Fee,Tax On Regulatory Fee,promotional rebates,promotional rebates tax,marketplace withheld tax,selling fees,fba fees,other transaction fees,other,total
{date}T10:00:00+00:00,12345678901234,Order,{order_id},TEST-SKU-001,Test Product,1,Amazon.com,Merchant,AFN,Seattle,WA,98101,{amount},0,0,0,0,0,0,0,0,0,0,-5.00,-3.00,0,0,{amount - 8.00}
"""
    return csv_content.encode('utf-8')

def create_amazon_payments_csv_with_expense(order_id, income_amount, expense_amount, date="2024-10-15"):
    """Create Amazon Payments CSV with INCOME and EXPENSE for same order"""
    csv_content = f"""date/time,settlement id,type,order id,sku,description,quantity,marketplace,account type,fulfillment,order city,order state,order postal,product sales,product sales tax,shipping credits,shipping credits tax,gift wrap credits,giftwrap credits tax,Regulatory Fee,Tax On Regulatory Fee,promotional rebates,promotional rebates tax,marketplace withheld tax,selling fees,fba fees,other transaction fees,other,total
{date}T10:00:00+00:00,12345678901234,Order,{order_id},TEST-SKU-001,Test Product,1,Amazon.com,Merchant,AFN,Seattle,WA,98101,{income_amount},0,0,0,0,0,0,0,0,0,0,-5.00,-3.00,0,0,{income_amount - 8.00}
{date}T10:05:00+00:00,12345678901234,Refund,{order_id},TEST-SKU-001,Test Product,1,Amazon.com,Merchant,AFN,Seattle,WA,98101,-{expense_amount},0,0,0,0,0,0,0,0,0,0,0,2.00,1.00,0,0,-{expense_amount - 3.00}
"""
    return csv_content.encode('utf-8')

def import_amazon_payments_csv(store_id, csv_content, commit=True):
    """Import Amazon Payments CSV to create transactions"""
    files = {'file': ('payments.csv', io.BytesIO(csv_content), 'text/csv')}
    resp = session.post(
        f"{BASE_URL}/transactions/import",
        params={"store_id": store_id, "marketplace": "US", "commit": str(commit).lower()},
        files=files
    )
    assert resp.status_code == 200, f"CSV import failed: {resp.status_code} {resp.text}"
    result = resp.json()
    print(f"✓ Imported Amazon Payments CSV: inserted={result.get('inserted', 0)}, accepted={result.get('accepted', 0)}")
    return result

def create_all_orders_tsv(rows):
    """Create All Orders TSV file
    
    rows: list of dicts with keys:
        amazon-order-id, merchant-order-id, purchase-date, last-updated-date,
        order-status, fulfillment-channel, sales-channel, product-name, sku, asin,
        item-status, quantity, currency, item-price, item-tax, shipping-price,
        shipping-tax, order-item-id
    """
    headers = [
        "amazon-order-id", "merchant-order-id", "purchase-date", "last-updated-date",
        "order-status", "fulfillment-channel", "sales-channel", "product-name", "sku", "asin",
        "item-status", "quantity", "currency", "item-price", "item-tax", "shipping-price",
        "shipping-tax", "order-item-id"
    ]
    lines = ["\t".join(headers)]
    for row in rows:
        line = "\t".join(str(row.get(h, "")) for h in headers)
        lines.append(line)
    return "\n".join(lines).encode('utf-8')

def import_all_orders_tsv(tsv_content, commit=True):
    """Import All Orders TSV"""
    files = {'file': ('all_orders.tsv', io.BytesIO(tsv_content), 'text/tab-separated-values')}
    resp = session.post(
        f"{BASE_URL}/amazon-orders/import",
        params={"commit": str(commit).lower()},
        files=files
    )
    assert resp.status_code == 200, f"All Orders import failed: {resp.status_code} {resp.text}"
    result = resp.json()
    print(f"✓ Imported All Orders TSV: matched={result.get('matched', 0)}, unmatched={result.get('unmatched', 0)}, committed={result.get('committed', False)}")
    return result

def get_transactions(store_id):
    """Get all transactions for a store"""
    resp = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id, "limit": 1000})
    assert resp.status_code == 200, f"Get transactions failed: {resp.status_code} {resp.text}"
    return resp.json()

def get_transaction_by_order_id(store_id, order_id):
    """Get transactions for a specific order ID"""
    all_txs = get_transactions(store_id)
    return [tx for tx in all_txs if tx.get('order_id') == order_id]

def get_dashboard_summary(store_id):
    """Get dashboard summary"""
    resp = session.get(f"{BASE_URL}/dashboard/summary", params={"store_id": store_id})
    assert resp.status_code == 200, f"Get dashboard failed: {resp.status_code} {resp.text}"
    return resp.json()

def cleanup_store(store_id):
    """Delete test store and all associated data"""
    resp = session.delete(f"{BASE_URL}/stores/{store_id}")
    if resp.status_code == 200:
        print(f"✓ Cleaned up test store: {store_id}")
    else:
        print(f"⚠ Could not delete test store (may be protected by design): {resp.status_code}")

def test_1_basic_metadata_enrichment():
    """
    TEST 1: After All Orders commit for an order WITH an existing income transaction:
    - Transaction doc has fulfillment_type (e.g. FBA)
    - Transaction doc has fulfillment_last_updated_at
    - Transaction doc has amazon_order_item_ids listing the order-item-ids
    - Amount, amount_usd, date, type, category, and all cost fields UNCHANGED
    - Total transactions count UNCHANGED (no second income row, no duplicate revenue)
    """
    print("\n" + "="*80)
    print("TEST 1: Basic Metadata Enrichment (Income Transaction)")
    print("="*80)
    
    store = create_test_store()
    store_id = store['id']
    
    try:
        # Step 1: Import Amazon Payments CSV to create INCOME transaction
        order_id = "111-1111111-1111111"
        amount = 50.00
        csv_content = create_amazon_payments_csv(order_id, amount, "2024-10-15")
        import_result = import_amazon_payments_csv(store_id, csv_content, commit=True)
        assert import_result['inserted'] == 1, f"Expected 1 insert, got {import_result['inserted']}"
        
        # Get transaction BEFORE All Orders import
        txs_before = get_transaction_by_order_id(store_id, order_id)
        assert len(txs_before) == 1, f"Expected 1 transaction, got {len(txs_before)}"
        tx_before = txs_before[0]
        
        print(f"✓ Transaction before All Orders import:")
        print(f"  - ID: {tx_before['id']}")
        print(f"  - Order ID: {tx_before['order_id']}")
        print(f"  - Type: {tx_before['type']}")
        print(f"  - Category: {tx_before['category']}")
        print(f"  - Amount: {tx_before['amount']}")
        print(f"  - Date: {tx_before['date']}")
        print(f"  - fulfillment_type: {tx_before.get('fulfillment_type', 'NOT SET')}")
        print(f"  - fulfillment_last_updated_at: {tx_before.get('fulfillment_last_updated_at', 'NOT SET')}")
        print(f"  - amazon_order_item_ids: {tx_before.get('amazon_order_item_ids', 'NOT SET')}")
        
        # Store original values for comparison
        original_amount = tx_before['amount']
        original_amount_usd = tx_before.get('amount_usd')
        original_date = tx_before['date']
        original_type = tx_before['type']
        original_category = tx_before['category']
        original_costs = {
            'product_cost': tx_before.get('product_cost', 0),
            'shipping_cost': tx_before.get('shipping_cost', 0),
            'extra_cost': tx_before.get('extra_cost', 0),
            'product_cost_recovery': tx_before.get('product_cost_recovery', 0),
            'shipping_cost_recovery': tx_before.get('shipping_cost_recovery', 0),
        }
        
        # Get transaction count before
        all_txs_before = get_transactions(store_id)
        count_before = len(all_txs_before)
        
        # Step 2: Import All Orders TSV with FBA fulfillment
        tsv_rows = [{
            "amazon-order-id": order_id,
            "merchant-order-id": "TEST-001",
            "purchase-date": "2024-10-15T10:00:00Z",
            "last-updated-date": "2024-10-15T12:00:00Z",
            "order-status": "Shipped",
            "fulfillment-channel": "Amazon",  # FBA
            "sales-channel": "Amazon.com",
            "product-name": "Test Product",
            "sku": "TEST-SKU-001",
            "asin": "B00TEST001",
            "item-status": "Shipped",
            "quantity": "1",
            "currency": "USD",
            "item-price": "50.00",
            "item-tax": "0.00",
            "shipping-price": "0.00",
            "shipping-tax": "0.00",
            "order-item-id": "12345678901234"
        }]
        tsv_content = create_all_orders_tsv(tsv_rows)
        orders_result = import_all_orders_tsv(tsv_content, commit=True)
        
        assert orders_result['matched'] == 1, f"Expected 1 matched order, got {orders_result['matched']}"
        assert orders_result['committed'] == True, "Expected committed=True"
        
        # Step 3: Get transaction AFTER All Orders import
        txs_after = get_transaction_by_order_id(store_id, order_id)
        assert len(txs_after) == 1, f"Expected 1 transaction after import, got {len(txs_after)}"
        tx_after = txs_after[0]
        
        # Get transaction count after
        all_txs_after = get_transactions(store_id)
        count_after = len(all_txs_after)
        
        print(f"\n✓ Transaction after All Orders import:")
        print(f"  - ID: {tx_after['id']}")
        print(f"  - fulfillment_type: {tx_after.get('fulfillment_type', 'NOT SET')}")
        print(f"  - fulfillment_last_updated_at: {tx_after.get('fulfillment_last_updated_at', 'NOT SET')}")
        print(f"  - amazon_order_item_ids: {tx_after.get('amazon_order_item_ids', 'NOT SET')}")
        
        # VERIFY: Metadata fields added
        assert tx_after.get('fulfillment_type') == 'FBA', f"Expected fulfillment_type=FBA, got {tx_after.get('fulfillment_type')}"
        assert tx_after.get('fulfillment_last_updated_at') is not None, "fulfillment_last_updated_at not set"
        assert tx_after.get('amazon_order_item_ids') == ['12345678901234'], f"Expected amazon_order_item_ids=['12345678901234'], got {tx_after.get('amazon_order_item_ids')}"
        
        # VERIFY: Financial fields UNCHANGED
        assert tx_after['amount'] == original_amount, f"Amount changed: {original_amount} -> {tx_after['amount']}"
        assert tx_after.get('amount_usd') == original_amount_usd, f"Amount USD changed: {original_amount_usd} -> {tx_after.get('amount_usd')}"
        assert tx_after['date'] == original_date, f"Date changed: {original_date} -> {tx_after['date']}"
        assert tx_after['type'] == original_type, f"Type changed: {original_type} -> {tx_after['type']}"
        assert tx_after['category'] == original_category, f"Category changed: {original_category} -> {tx_after['category']}"
        
        for cost_field, original_value in original_costs.items():
            assert tx_after.get(cost_field, 0) == original_value, f"{cost_field} changed: {original_value} -> {tx_after.get(cost_field, 0)}"
        
        # VERIFY: Transaction count UNCHANGED (no duplicate)
        assert count_after == count_before, f"Transaction count changed: {count_before} -> {count_after}"
        
        print(f"\n✓ VERIFIED: Metadata enrichment successful")
        print(f"  - fulfillment_type added: FBA")
        print(f"  - fulfillment_last_updated_at added")
        print(f"  - amazon_order_item_ids added: ['12345678901234']")
        print(f"  - All financial fields UNCHANGED")
        print(f"  - Transaction count UNCHANGED: {count_before}")
        
        print("\n✅ TEST 1 PASSED")
        return True
        
    finally:
        cleanup_store(store_id)

def test_2_idempotent_reimport():
    """
    TEST 2: Re-import the SAME file (commit=true again):
    - Transactions count still unchanged
    - No duplicate items
    - Metadata re-written idempotently
    """
    print("\n" + "="*80)
    print("TEST 2: Idempotent Re-import")
    print("="*80)
    
    store = create_test_store()
    store_id = store['id']
    
    try:
        # Step 1: Import Amazon Payments CSV
        order_id = "222-2222222-2222222"
        amount = 75.00
        csv_content = create_amazon_payments_csv(order_id, amount, "2024-10-16")
        import_amazon_payments_csv(store_id, csv_content, commit=True)
        
        # Step 2: Import All Orders TSV (first time)
        tsv_rows = [{
            "amazon-order-id": order_id,
            "merchant-order-id": "TEST-002",
            "purchase-date": "2024-10-16T10:00:00Z",
            "last-updated-date": "2024-10-16T12:00:00Z",
            "order-status": "Shipped",
            "fulfillment-channel": "Amazon",
            "sales-channel": "Amazon.com",
            "product-name": "Test Product 2",
            "sku": "TEST-SKU-002",
            "asin": "B00TEST002",
            "item-status": "Shipped",
            "quantity": "1",
            "currency": "USD",
            "item-price": "75.00",
            "item-tax": "0.00",
            "shipping-price": "0.00",
            "shipping-tax": "0.00",
            "order-item-id": "22222222222222"
        }]
        tsv_content = create_all_orders_tsv(tsv_rows)
        import_all_orders_tsv(tsv_content, commit=True)
        
        # Get state after first import
        txs_after_first = get_transaction_by_order_id(store_id, order_id)
        count_after_first = len(get_transactions(store_id))
        fulfillment_updated_first = txs_after_first[0].get('fulfillment_last_updated_at')
        
        print(f"✓ After first All Orders import:")
        print(f"  - Transaction count: {count_after_first}")
        print(f"  - fulfillment_type: {txs_after_first[0].get('fulfillment_type')}")
        print(f"  - fulfillment_last_updated_at: {fulfillment_updated_first}")
        
        # Step 3: Re-import SAME file (second time)
        import_all_orders_tsv(tsv_content, commit=True)
        
        # Get state after second import
        txs_after_second = get_transaction_by_order_id(store_id, order_id)
        count_after_second = len(get_transactions(store_id))
        fulfillment_updated_second = txs_after_second[0].get('fulfillment_last_updated_at')
        
        print(f"\n✓ After second All Orders import (same file):")
        print(f"  - Transaction count: {count_after_second}")
        print(f"  - fulfillment_type: {txs_after_second[0].get('fulfillment_type')}")
        print(f"  - fulfillment_last_updated_at: {fulfillment_updated_second}")
        
        # VERIFY: Count unchanged
        assert count_after_second == count_after_first, f"Transaction count changed: {count_after_first} -> {count_after_second}"
        
        # VERIFY: No duplicates
        assert len(txs_after_second) == 1, f"Expected 1 transaction, got {len(txs_after_second)}"
        
        # VERIFY: Metadata re-written (timestamp should be updated)
        assert txs_after_second[0].get('fulfillment_type') == 'FBA', "fulfillment_type not preserved"
        assert txs_after_second[0].get('amazon_order_item_ids') == ['22222222222222'], "amazon_order_item_ids not preserved"
        # fulfillment_last_updated_at should be updated (newer timestamp)
        assert fulfillment_updated_second >= fulfillment_updated_first, "fulfillment_last_updated_at not updated"
        
        print(f"\n✓ VERIFIED: Idempotent re-import successful")
        print(f"  - Transaction count unchanged: {count_after_first}")
        print(f"  - No duplicate transactions")
        print(f"  - Metadata re-written idempotently")
        
        print("\n✅ TEST 2 PASSED")
        return True
        
    finally:
        cleanup_store(store_id)

def test_3_unmatched_order_no_writes():
    """
    TEST 3: All Orders row for an order id with NO existing transaction/canonical order:
    - Unmatched
    - Verify ZERO writes to transactions for that id (count unchanged)
    """
    print("\n" + "="*80)
    print("TEST 3: Unmatched Order - No Writes to Transactions")
    print("="*80)
    
    store = create_test_store()
    store_id = store['id']
    
    try:
        # Step 1: Import Amazon Payments CSV for order A (to create canonical order)
        order_a = "333-3333333-3333333"
        csv_content = create_amazon_payments_csv(order_a, 100.00, "2024-10-17")
        import_amazon_payments_csv(store_id, csv_content, commit=True)
        
        count_before = len(get_transactions(store_id))
        print(f"✓ Transaction count before All Orders import: {count_before}")
        
        # Step 2: Import All Orders TSV with TWO orders:
        #   - Order A: matched (has transaction)
        #   - Order B: unmatched (NO transaction)
        order_b = "444-4444444-4444444"  # This order has NO transaction
        tsv_rows = [
            {
                "amazon-order-id": order_a,
                "merchant-order-id": "TEST-003A",
                "purchase-date": "2024-10-17T10:00:00Z",
                "last-updated-date": "2024-10-17T12:00:00Z",
                "order-status": "Shipped",
                "fulfillment-channel": "Amazon",
                "sales-channel": "Amazon.com",
                "product-name": "Test Product A",
                "sku": "TEST-SKU-003A",
                "asin": "B00TEST003A",
                "item-status": "Shipped",
                "quantity": "1",
                "currency": "USD",
                "item-price": "100.00",
                "item-tax": "0.00",
                "shipping-price": "0.00",
                "shipping-tax": "0.00",
                "order-item-id": "33333333333333"
            },
            {
                "amazon-order-id": order_b,  # UNMATCHED
                "merchant-order-id": "TEST-003B",
                "purchase-date": "2024-10-17T11:00:00Z",
                "last-updated-date": "2024-10-17T13:00:00Z",
                "order-status": "Shipped",
                "fulfillment-channel": "Merchant",
                "sales-channel": "Amazon.com",
                "product-name": "Test Product B",
                "sku": "TEST-SKU-003B",
                "asin": "B00TEST003B",
                "item-status": "Shipped",
                "quantity": "1",
                "currency": "USD",
                "item-price": "50.00",
                "item-tax": "0.00",
                "shipping-price": "0.00",
                "shipping-tax": "0.00",
                "order-item-id": "44444444444444"
            }
        ]
        tsv_content = create_all_orders_tsv(tsv_rows)
        orders_result = import_all_orders_tsv(tsv_content, commit=True)
        
        print(f"\n✓ All Orders import result:")
        print(f"  - Matched: {orders_result['matched']}")
        print(f"  - Unmatched: {orders_result['unmatched']}")
        
        # VERIFY: 1 matched, 1 unmatched
        assert orders_result['matched'] == 1, f"Expected 1 matched, got {orders_result['matched']}"
        assert orders_result['unmatched'] == 1, f"Expected 1 unmatched, got {orders_result['unmatched']}"
        
        # Step 3: Verify transaction count unchanged
        count_after = len(get_transactions(store_id))
        print(f"\n✓ Transaction count after All Orders import: {count_after}")
        
        assert count_after == count_before, f"Transaction count changed: {count_before} -> {count_after}"
        
        # Step 4: Verify order B has NO transactions
        txs_order_b = get_transaction_by_order_id(store_id, order_b)
        assert len(txs_order_b) == 0, f"Expected 0 transactions for unmatched order B, got {len(txs_order_b)}"
        
        # Step 5: Verify order A has transaction with metadata
        txs_order_a = get_transaction_by_order_id(store_id, order_a)
        assert len(txs_order_a) == 1, f"Expected 1 transaction for matched order A, got {len(txs_order_a)}"
        assert txs_order_a[0].get('fulfillment_type') == 'FBA', "Order A should have fulfillment_type"
        
        print(f"\n✓ VERIFIED: Unmatched order handling correct")
        print(f"  - Transaction count unchanged: {count_before}")
        print(f"  - Order B (unmatched): 0 transactions")
        print(f"  - Order A (matched): 1 transaction with metadata")
        
        print("\n✅ TEST 3 PASSED")
        return True
        
    finally:
        cleanup_store(store_id)

def test_4_both_income_and_expense():
    """
    TEST 4: If the order has an EXPENSE row too (add one via the payments CSV):
    - Both income AND expense rows receive the metadata
    """
    print("\n" + "="*80)
    print("TEST 4: Both Income and Expense Receive Metadata")
    print("="*80)
    
    store = create_test_store()
    store_id = store['id']
    
    try:
        # Step 1: Import Amazon Payments CSV with BOTH income and expense (refund)
        order_id = "555-5555555-5555555"
        income_amount = 120.00
        expense_amount = 30.00
        csv_content = create_amazon_payments_csv_with_expense(order_id, income_amount, expense_amount, "2024-10-18")
        import_result = import_amazon_payments_csv(store_id, csv_content, commit=True)
        
        # Should have 2 transactions: 1 income, 1 expense
        assert import_result['inserted'] == 2, f"Expected 2 inserts, got {import_result['inserted']}"
        
        txs_before = get_transaction_by_order_id(store_id, order_id)
        assert len(txs_before) == 2, f"Expected 2 transactions, got {len(txs_before)}"
        
        income_tx = [tx for tx in txs_before if tx['type'] == 'income'][0]
        expense_tx = [tx for tx in txs_before if tx['type'] == 'expense'][0]
        
        print(f"✓ Transactions before All Orders import:")
        print(f"  - Income: ID={income_tx['id']}, amount={income_tx['amount']}, fulfillment_type={income_tx.get('fulfillment_type', 'NOT SET')}")
        print(f"  - Expense: ID={expense_tx['id']}, amount={expense_tx['amount']}, fulfillment_type={expense_tx.get('fulfillment_type', 'NOT SET')}")
        
        # Step 2: Import All Orders TSV
        tsv_rows = [{
            "amazon-order-id": order_id,
            "merchant-order-id": "TEST-004",
            "purchase-date": "2024-10-18T10:00:00Z",
            "last-updated-date": "2024-10-18T12:00:00Z",
            "order-status": "Shipped",
            "fulfillment-channel": "Merchant",  # FBM
            "sales-channel": "Amazon.com",
            "product-name": "Test Product 4",
            "sku": "TEST-SKU-004",
            "asin": "B00TEST004",
            "item-status": "Shipped",
            "quantity": "1",
            "currency": "USD",
            "item-price": "120.00",
            "item-tax": "0.00",
            "shipping-price": "0.00",
            "shipping-tax": "0.00",
            "order-item-id": "55555555555555"
        }]
        tsv_content = create_all_orders_tsv(tsv_rows)
        import_all_orders_tsv(tsv_content, commit=True)
        
        # Step 3: Verify BOTH transactions have metadata
        txs_after = get_transaction_by_order_id(store_id, order_id)
        assert len(txs_after) == 2, f"Expected 2 transactions after import, got {len(txs_after)}"
        
        income_tx_after = [tx for tx in txs_after if tx['type'] == 'income'][0]
        expense_tx_after = [tx for tx in txs_after if tx['type'] == 'expense'][0]
        
        print(f"\n✓ Transactions after All Orders import:")
        print(f"  - Income: fulfillment_type={income_tx_after.get('fulfillment_type')}, amazon_order_item_ids={income_tx_after.get('amazon_order_item_ids')}")
        print(f"  - Expense: fulfillment_type={expense_tx_after.get('fulfillment_type')}, amazon_order_item_ids={expense_tx_after.get('amazon_order_item_ids')}")
        
        # VERIFY: Both have metadata
        assert income_tx_after.get('fulfillment_type') == 'FBM', f"Income should have fulfillment_type=FBM, got {income_tx_after.get('fulfillment_type')}"
        assert expense_tx_after.get('fulfillment_type') == 'FBM', f"Expense should have fulfillment_type=FBM, got {expense_tx_after.get('fulfillment_type')}"
        
        assert income_tx_after.get('amazon_order_item_ids') == ['55555555555555'], "Income should have amazon_order_item_ids"
        assert expense_tx_after.get('amazon_order_item_ids') == ['55555555555555'], "Expense should have amazon_order_item_ids"
        
        assert income_tx_after.get('fulfillment_last_updated_at') is not None, "Income should have fulfillment_last_updated_at"
        assert expense_tx_after.get('fulfillment_last_updated_at') is not None, "Expense should have fulfillment_last_updated_at"
        
        # VERIFY: Financial fields unchanged
        assert income_tx_after['amount'] == income_tx['amount'], "Income amount changed"
        assert expense_tx_after['amount'] == expense_tx['amount'], "Expense amount changed"
        
        print(f"\n✓ VERIFIED: Both income and expense enriched")
        print(f"  - Both have fulfillment_type=FBM")
        print(f"  - Both have amazon_order_item_ids=['55555555555555']")
        print(f"  - Both have fulfillment_last_updated_at")
        print(f"  - Financial fields unchanged")
        
        print("\n✅ TEST 4 PASSED")
        return True
        
    finally:
        cleanup_store(store_id)

def test_5_classification_integrity():
    """
    TEST 5: Classification integrity:
    - Order with Shipped qty=1 fulfillment-channel=Amazon row
    - PLUS Cancelled qty=0 fulfillment-channel=Merchant row
    - Result: fulfillment_type=FBA on the transaction (cancelled zero-qty ignored)
    """
    print("\n" + "="*80)
    print("TEST 5: Classification Integrity (Cancelled Zero-Qty Ignored)")
    print("="*80)
    
    store = create_test_store()
    store_id = store['id']
    
    try:
        # Step 1: Import Amazon Payments CSV
        order_id = "666-6666666-6666666"
        csv_content = create_amazon_payments_csv(order_id, 80.00, "2024-10-19")
        import_amazon_payments_csv(store_id, csv_content, commit=True)
        
        # Step 2: Import All Orders TSV with TWO items:
        #   - Item 1: Shipped, qty=1, Amazon (FBA) - ACTIVE
        #   - Item 2: Cancelled, qty=0, Merchant (FBM) - SHOULD BE IGNORED
        tsv_rows = [
            {
                "amazon-order-id": order_id,
                "merchant-order-id": "TEST-005",
                "purchase-date": "2024-10-19T10:00:00Z",
                "last-updated-date": "2024-10-19T12:00:00Z",
                "order-status": "Shipped",
                "fulfillment-channel": "Amazon",  # FBA
                "sales-channel": "Amazon.com",
                "product-name": "Test Product 5A",
                "sku": "TEST-SKU-005A",
                "asin": "B00TEST005A",
                "item-status": "Shipped",
                "quantity": "1",  # Active
                "currency": "USD",
                "item-price": "80.00",
                "item-tax": "0.00",
                "shipping-price": "0.00",
                "shipping-tax": "0.00",
                "order-item-id": "66666666666661"
            },
            {
                "amazon-order-id": order_id,
                "merchant-order-id": "TEST-005",
                "purchase-date": "2024-10-19T10:00:00Z",
                "last-updated-date": "2024-10-19T13:00:00Z",
                "order-status": "Cancelled",
                "fulfillment-channel": "Merchant",  # FBM
                "sales-channel": "Amazon.com",
                "product-name": "Test Product 5B",
                "sku": "TEST-SKU-005B",
                "asin": "B00TEST005B",
                "item-status": "Cancelled",
                "quantity": "0",  # Cancelled, should be ignored
                "currency": "USD",
                "item-price": "0.00",
                "item-tax": "0.00",
                "shipping-price": "0.00",
                "shipping-tax": "0.00",
                "order-item-id": "66666666666662"
            }
        ]
        tsv_content = create_all_orders_tsv(tsv_rows)
        orders_result = import_all_orders_tsv(tsv_content, commit=True)
        
        print(f"\n✓ All Orders import result:")
        print(f"  - Matched: {orders_result['matched']}")
        print(f"  - FBA items: {orders_result['fba_items']}")
        print(f"  - FBM items: {orders_result['fbm_items']}")
        
        # Step 3: Verify transaction has fulfillment_type=FBA (not MIXED)
        txs = get_transaction_by_order_id(store_id, order_id)
        assert len(txs) == 1, f"Expected 1 transaction, got {len(txs)}"
        tx = txs[0]
        
        print(f"\n✓ Transaction after All Orders import:")
        print(f"  - fulfillment_type: {tx.get('fulfillment_type')}")
        print(f"  - amazon_order_item_ids: {tx.get('amazon_order_item_ids')}")
        
        # VERIFY: fulfillment_type is FBA (cancelled zero-qty Merchant item ignored)
        assert tx.get('fulfillment_type') == 'FBA', f"Expected fulfillment_type=FBA, got {tx.get('fulfillment_type')}"
        
        # VERIFY: Both item IDs are recorded (even though one is cancelled)
        item_ids = tx.get('amazon_order_item_ids', [])
        assert '66666666666661' in item_ids, "Active item ID should be in amazon_order_item_ids"
        assert '66666666666662' in item_ids, "Cancelled item ID should be in amazon_order_item_ids"
        
        print(f"\n✓ VERIFIED: Classification integrity maintained")
        print(f"  - fulfillment_type=FBA (cancelled zero-qty Merchant item ignored)")
        print(f"  - Both item IDs recorded: {item_ids}")
        
        print("\n✅ TEST 5 PASSED")
        return True
        
    finally:
        cleanup_store(store_id)

def test_6_dashboard_summary_unchanged():
    """
    TEST 6: Dashboard summary totals identical before vs after All Orders import
    - Financial safety: no impact on revenue, expenses, net profit
    """
    print("\n" + "="*80)
    print("TEST 6: Dashboard Summary Totals Unchanged (Financial Safety)")
    print("="*80)
    
    store = create_test_store()
    store_id = store['id']
    
    try:
        # Step 1: Import Amazon Payments CSV with multiple transactions
        order_1 = "777-7777777-7777777"
        order_2 = "888-8888888-8888888"
        
        csv_content_1 = create_amazon_payments_csv(order_1, 150.00, "2024-10-20")
        import_amazon_payments_csv(store_id, csv_content_1, commit=True)
        
        csv_content_2 = create_amazon_payments_csv_with_expense(order_2, 200.00, 50.00, "2024-10-21")
        import_amazon_payments_csv(store_id, csv_content_2, commit=True)
        
        # Get dashboard summary BEFORE All Orders import
        summary_before = get_dashboard_summary(store_id)
        
        print(f"✓ Dashboard summary BEFORE All Orders import:")
        print(f"  - Revenue: {summary_before.get('revenue')}")
        print(f"  - Expenses: {summary_before.get('expenses')}")
        print(f"  - Net Profit: {summary_before.get('net_profit')}")
        print(f"  - Transaction Count: {summary_before.get('transaction_count')}")
        
        revenue_before = summary_before.get('revenue')
        expenses_before = summary_before.get('expenses')
        net_profit_before = summary_before.get('net_profit')
        tx_count_before = summary_before.get('transaction_count')
        
        # Step 2: Import All Orders TSV for both orders
        tsv_rows = [
            {
                "amazon-order-id": order_1,
                "merchant-order-id": "TEST-006A",
                "purchase-date": "2024-10-20T10:00:00Z",
                "last-updated-date": "2024-10-20T12:00:00Z",
                "order-status": "Shipped",
                "fulfillment-channel": "Amazon",
                "sales-channel": "Amazon.com",
                "product-name": "Test Product 6A",
                "sku": "TEST-SKU-006A",
                "asin": "B00TEST006A",
                "item-status": "Shipped",
                "quantity": "1",
                "currency": "USD",
                "item-price": "150.00",
                "item-tax": "0.00",
                "shipping-price": "0.00",
                "shipping-tax": "0.00",
                "order-item-id": "77777777777777"
            },
            {
                "amazon-order-id": order_2,
                "merchant-order-id": "TEST-006B",
                "purchase-date": "2024-10-21T10:00:00Z",
                "last-updated-date": "2024-10-21T12:00:00Z",
                "order-status": "Shipped",
                "fulfillment-channel": "Merchant",
                "sales-channel": "Amazon.com",
                "product-name": "Test Product 6B",
                "sku": "TEST-SKU-006B",
                "asin": "B00TEST006B",
                "item-status": "Shipped",
                "quantity": "1",
                "currency": "USD",
                "item-price": "200.00",
                "item-tax": "0.00",
                "shipping-price": "0.00",
                "shipping-tax": "0.00",
                "order-item-id": "88888888888888"
            }
        ]
        tsv_content = create_all_orders_tsv(tsv_rows)
        import_all_orders_tsv(tsv_content, commit=True)
        
        # Get dashboard summary AFTER All Orders import
        summary_after = get_dashboard_summary(store_id)
        
        print(f"\n✓ Dashboard summary AFTER All Orders import:")
        print(f"  - Revenue: {summary_after.get('revenue')}")
        print(f"  - Expenses: {summary_after.get('expenses')}")
        print(f"  - Net Profit: {summary_after.get('net_profit')}")
        print(f"  - Transaction Count: {summary_after.get('transaction_count')}")
        
        revenue_after = summary_after.get('revenue')
        expenses_after = summary_after.get('expenses')
        net_profit_after = summary_after.get('net_profit')
        tx_count_after = summary_after.get('transaction_count')
        
        # VERIFY: All financial totals UNCHANGED
        assert revenue_after == revenue_before, f"Revenue changed: {revenue_before} -> {revenue_after}"
        assert expenses_after == expenses_before, f"Expenses changed: {expenses_before} -> {expenses_after}"
        assert net_profit_after == net_profit_before, f"Net profit changed: {net_profit_before} -> {net_profit_after}"
        assert tx_count_after == tx_count_before, f"Transaction count changed: {tx_count_before} -> {tx_count_after}"
        
        print(f"\n✓ VERIFIED: Dashboard summary unchanged")
        print(f"  - Revenue: {revenue_before} (unchanged)")
        print(f"  - Expenses: {expenses_before} (unchanged)")
        print(f"  - Net Profit: {net_profit_before} (unchanged)")
        print(f"  - Transaction Count: {tx_count_before} (unchanged)")
        
        print("\n✅ TEST 6 PASSED")
        return True
        
    finally:
        cleanup_store(store_id)

def main():
    """Run all tests"""
    print("\n" + "="*80)
    print("AMAZON ORDERS / FULFILLMENT IMPORT METADATA ENRICHMENT TEST SUITE")
    print("="*80)
    print("\nTesting the focused fix in backend/amazon_orders_import.py")
    print("that enriches EXISTING transactions with fulfillment metadata.")
    print("\nCRITICAL RULES:")
    print("- NEVER insert/upsert into transactions collection")
    print("- NEVER touch amounts, dates, costs, or financial fields")
    print("- ONLY write metadata for matched orders")
    print("- NEVER write anything for unmatched orders")
    print("="*80)
    
    # Login
    login()
    
    # Run all tests
    tests = [
        ("Test 1: Basic Metadata Enrichment", test_1_basic_metadata_enrichment),
        ("Test 2: Idempotent Re-import", test_2_idempotent_reimport),
        ("Test 3: Unmatched Order - No Writes", test_3_unmatched_order_no_writes),
        ("Test 4: Both Income and Expense", test_4_both_income_and_expense),
        ("Test 5: Classification Integrity", test_5_classification_integrity),
        ("Test 6: Dashboard Summary Unchanged", test_6_dashboard_summary_unchanged),
    ]
    
    results = []
    for test_name, test_func in tests:
        try:
            result = test_func()
            results.append((test_name, "PASSED" if result else "FAILED"))
        except Exception as e:
            print(f"\n❌ {test_name} FAILED with exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((test_name, f"FAILED: {str(e)}"))
    
    # Print summary
    print("\n" + "="*80)
    print("TEST SUMMARY")
    print("="*80)
    for test_name, status in results:
        icon = "✅" if status == "PASSED" else "❌"
        print(f"{icon} {test_name}: {status}")
    
    passed = sum(1 for _, status in results if status == "PASSED")
    total = len(results)
    print(f"\nTotal: {passed}/{total} tests passed")
    
    if passed == total:
        print("\n🎉 ALL TESTS PASSED! 🎉")
        print("\nThe Amazon Orders / Fulfillment Import metadata enrichment fix is working correctly.")
        print("All 6 minimum test requirements verified successfully.")
    else:
        print(f"\n⚠️  {total - passed} test(s) failed. Please review the failures above.")
    
    print("="*80)

if __name__ == "__main__":
    main()
