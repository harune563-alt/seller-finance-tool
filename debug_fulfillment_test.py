"""
Debug test to understand why fulfillment metadata is not being written
"""
import requests
import json
import io

BASE_URL = "https://sellerfin-tool.preview.emergentagent.com/api"
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

session = requests.Session()

# Login
resp = session.post(f"{BASE_URL}/auth/login", json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD})
print(f"Login: {resp.status_code}")

# Create store
resp = session.post(f"{BASE_URL}/stores", json={"name": "DEBUG_STORE", "marketplaces": ["US"], "default_currency": "USD"})
store = resp.json()
store_id = store['id']
print(f"Store created: {store_id}")

# Import Amazon Payments CSV
order_id = "DEBUG-ORDER-001"
csv_content = f"""date/time,settlement id,type,order id,sku,description,quantity,marketplace,account type,fulfillment,order city,order state,order postal,product sales,product sales tax,shipping credits,shipping credits tax,gift wrap credits,giftwrap credits tax,Regulatory Fee,Tax On Regulatory Fee,promotional rebates,promotional rebates tax,marketplace withheld tax,selling fees,fba fees,other transaction fees,other,total
2024-10-15T10:00:00+00:00,12345678901234,Order,{order_id},TEST-SKU,Test Product,1,Amazon.com,Merchant,AFN,Seattle,WA,98101,100.00,0,0,0,0,0,0,0,0,0,0,-5.00,-3.00,0,0,92.00
"""
files = {'file': ('payments.csv', io.BytesIO(csv_content.encode('utf-8')), 'text/csv')}
resp = session.post(f"{BASE_URL}/transactions/import", params={"store_id": store_id, "marketplace": "US", "commit": "true"}, files=files)
print(f"CSV import: {resp.status_code}, inserted={resp.json().get('inserted')}")

# Check canonical orders collection
# We can't directly query MongoDB, but we can check if the transaction was created
resp = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id, "limit": 1000})
txs = resp.json()
print(f"\nTransactions after CSV import: {len(txs)}")
for tx in txs:
    print(f"  - ID: {tx['id']}, Order ID: {tx.get('order_id')}, Type: {tx['type']}, Amount: {tx['amount']}")

# Import All Orders TSV
tsv_content = f"""amazon-order-id\tmerchant-order-id\tpurchase-date\tlast-updated-date\torder-status\tfulfillment-channel\tsales-channel\tproduct-name\tsku\tasin\titem-status\tquantity\tcurrency\titem-price\titem-tax\tshipping-price\tshipping-tax\torder-item-id
{order_id}\tMERCH-001\t2024-10-15T10:00:00Z\t2024-10-15T12:00:00Z\tShipped\tAmazon\tAmazon.com\tTest Product\tTEST-SKU\tB00TEST001\tShipped\t1\tUSD\t100.00\t0.00\t0.00\t0.00\t12345678901234
"""
files = {'file': ('all_orders.tsv', io.BytesIO(tsv_content.encode('utf-8')), 'text/tab-separated-values')}
resp = session.post(f"{BASE_URL}/amazon-orders/import", params={"commit": "true"}, files=files)
result = resp.json()
print(f"\nAll Orders import: {resp.status_code}")
print(f"  - matched: {result.get('matched')}")
print(f"  - unmatched: {result.get('unmatched')}")
print(f"  - committed: {result.get('committed')}")

# Check transactions again
resp = session.get(f"{BASE_URL}/transactions", params={"store_id": store_id, "limit": 1000})
txs = resp.json()
print(f"\nTransactions after All Orders import: {len(txs)}")
for tx in txs:
    print(f"  - ID: {tx['id']}")
    print(f"    Order ID: {tx.get('order_id')}")
    print(f"    Type: {tx['type']}")
    print(f"    Amount: {tx['amount']}")
    print(f"    fulfillment_type: {tx.get('fulfillment_type', 'NOT SET')}")
    print(f"    fulfillment_last_updated_at: {tx.get('fulfillment_last_updated_at', 'NOT SET')}")
    print(f"    amazon_order_item_ids: {tx.get('amazon_order_item_ids', 'NOT SET')}")

# Check amazon_orders collection via the items endpoint
resp = session.get(f"{BASE_URL}/amazon-orders/items", params={"order_id": order_id})
items_result = resp.json()
print(f"\nAmazon Order Items for {order_id}:")
print(f"  - Total items: {items_result.get('total')}")
print(f"  - Canonical orders: {len(items_result.get('canonical_orders', []))}")
for canonical in items_result.get('canonical_orders', []):
    print(f"    - Order ID: {canonical.get('order_id')}")
    print(f"      Store ID: {canonical.get('store_id')}")
    print(f"      Marketplace: {canonical.get('marketplace')}")
    print(f"      fulfillment_type: {canonical.get('fulfillment_type', 'NOT SET')}")

# Cleanup
resp = session.delete(f"{BASE_URL}/stores/{store_id}")
print(f"\nCleanup: {resp.status_code}")
