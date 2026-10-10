"""
Test to verify the exact MongoDB query being used
"""
import requests
import io

BASE_URL = "https://sellerfin-tool.preview.emergentagent.com/api"
session = requests.Session()

# Login
session.post(f"{BASE_URL}/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})

# Create store
store = session.post(f"{BASE_URL}/stores", json={"name": "QUERY_TEST", "marketplaces": ["US"], "default_currency": "USD"}).json()
store_id = store['id']

# Import CSV with specific order ID
order_id = "TEST-999-9999999"
csv = f"""date/time,settlement id,type,order id,total
2024-10-15T10:00:00+00:00,123,Order,{order_id},100.00
"""
files = {'file': ('test.csv', io.BytesIO(csv.encode('utf-8')), 'text/csv')}
session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)

# Get transaction
txs = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
print(f"Transaction order_id: '{txs[0].get('order_id')}'")
print(f"Transaction order_id type: {type(txs[0].get('order_id'))}")
print(f"Transaction order_id repr: {repr(txs[0].get('order_id'))}")

# Import All Orders with same order ID
tsv = f"""amazon-order-id\torder-item-id\tfulfillment-channel\tquantity\torder-status
{order_id}\t111111\tAmazon\t1\tShipped
"""
files = {'file': ('test.tsv', io.BytesIO(tsv.encode('utf-8')), 'text/tab-separated-values')}
result = session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files).json()
print(f"\nAll Orders matched: {result.get('matched')}")

# Check transaction again
txs = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id}).json()
print(f"\nAfter All Orders import:")
print(f"  fulfillment_type: {txs[0].get('fulfillment_type')}")
print(f"  amazon_order_item_ids: {txs[0].get('amazon_order_item_ids')}")

# Check canonical order
items = session.get(f"{BASE_URL}/amazon-orders/items", params={"order_id": order_id}).json()
print(f"\nCanonical orders: {len(items.get('canonical_orders', []))}")
if items.get('canonical_orders'):
    print(f"  fulfillment_type: {items['canonical_orders'][0].get('fulfillment_type')}")

# Cleanup
session.delete(f"{BASE_URL}/stores/{store_id}")
