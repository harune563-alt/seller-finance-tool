"""
Clean test suite with unique order IDs to avoid pollution
"""
import requests
import io
import uuid

BASE_URL = "https://fba-finance-hub.preview.emergentagent.com/api"
session = requests.Session()

def unique_order_id():
    """Generate unique order ID"""
    return f"TEST-{uuid.uuid4().hex[:8].upper()}"

# Login
session.post(f"{BASE_URL}/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})

print("\n" + "="*80)
print("CLEAN TEST: Basic Metadata Enrichment")
print("="*80)

# Create store
store = session.post(f"{BASE_URL}/stores", json={"name": f"TEST_{uuid.uuid4().hex[:8]}", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']
print(f"✓ Store: {store_id}")

# Import CSV
order_id = unique_order_id()
print(f"✓ Order ID: {order_id}")
csv = f"""date/time,settlement id,type,order id,total
2024-10-15T10:00:00+00:00,123,Order,{order_id},100.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

# Get transaction BEFORE
txs_before = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
print(f"\n✓ Transaction BEFORE All Orders import:")
print(f"  - fulfillment_type: {txs_before[0].get('fulfillment_type')}")
print(f"  - amazon_order_item_ids: {txs_before[0].get('amazon_order_item_ids')}")

# Import All Orders
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_id}\tITEM-{uuid.uuid4().hex[:8]}\tAmazon\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
result = session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files).json()
print(f"\n✓ All Orders import: matched={result.get('matched')}, unmatched={result.get('unmatched')}")

# Get transaction AFTER
txs_after = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
print(f"\n✓ Transaction AFTER All Orders import:")
print(f"  - fulfillment_type: {txs_after[0].get('fulfillment_type')}")
print(f"  - amazon_order_item_ids: {txs_after[0].get('amazon_order_item_ids')}")
print(f"  - fulfillment_last_updated_at: {txs_after[0].get('fulfillment_last_updated_at')}")

# Verify
assert txs_after[0].get('fulfillment_type') == 'FBA', f"Expected FBA, got {txs_after[0].get('fulfillment_type')}"
assert len(txs_after[0].get('amazon_order_item_ids', [])) == 1, f"Expected 1 item ID, got {len(txs_after[0].get('amazon_order_item_ids', []))}"
assert txs_after[0].get('fulfillment_last_updated_at') is not None, "fulfillment_last_updated_at not set"

print("\n✅ TEST PASSED: Metadata enrichment working correctly")

# Cleanup
session.delete(f"{BASE_URL}/stores/{store_id}")
print(f"✓ Cleaned up store")
