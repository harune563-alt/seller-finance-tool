"""Cash Flow Module Testing Suite

Tests the NEW standalone Cash Flow (Nakit Akışı) module per review request.
Runs 8 focused tests + sanity checks, creates test stores with CF_TEST prefix,
and cleans up ALL test data at the end.
"""
import requests
import json
from datetime import datetime

# Backend URL from frontend/.env
BASE_URL = "https://fba-finance-hub.preview.emergentagent.com/api"

# Test credentials from /app/memory/test_credentials.md
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"

# Global session and auth token
session = requests.Session()
auth_token = None
user_id = None

# Track test data for cleanup
test_stores = []
test_lots = []
test_transactions = []
test_sellerflash_records = []
test_allocations = []

def login():
    """Login and get auth token"""
    global auth_token, user_id
    print(f"\n🔐 Logging in as {ADMIN_EMAIL}...")
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    data = resp.json()
    auth_token = data["token"]
    user_id = data["id"]
    session.headers.update({"Authorization": f"Bearer {auth_token}"})
    print(f"✅ Logged in successfully (user_id: {user_id})")

def create_test_store(name, marketplaces=["US"], currency="USD"):
    """Create a test store with CF_TEST prefix"""
    print(f"\n📦 Creating test store: {name}")
    resp = session.post(f"{BASE_URL}/stores", json={
        "name": name,
        "marketplaces": marketplaces,
        "default_currency": currency
    })
    assert resp.status_code == 200, f"Store creation failed: {resp.status_code} {resp.text}"
    store = resp.json()
    test_stores.append(store["id"])
    print(f"✅ Store created: {store['id']} ({store['name']})")
    return store

def create_fba_lot(store_id, sku, purchase_date, original_quantity, product_unit_cost_usd, inbound_shipping_total_usd):
    """Create an FBA lot"""
    print(f"\n📦 Creating FBA lot: SKU={sku}, qty={original_quantity}, cost=${product_unit_cost_usd}, inbound=${inbound_shipping_total_usd}")
    resp = session.post(f"{BASE_URL}/fba/lots", json={
        "store_id": store_id,
        "marketplace": "US",
        "sku": sku,
        "asin": f"B0TEST{sku[:6]}",
        "product_name": f"Test Product {sku}",
        "purchase_date": purchase_date,
        "original_quantity": original_quantity,
        "product_unit_cost_usd": product_unit_cost_usd,
        "inbound_shipping_total_usd": inbound_shipping_total_usd,
        "note": "Cash flow test lot"
    })
    assert resp.status_code == 200, f"Lot creation failed: {resp.status_code} {resp.text}"
    lot = resp.json()
    test_lots.append(lot["id"])
    print(f"✅ Lot created: {lot['id']} (code: {lot['lot_code']})")
    return lot

def get_cashflow_summary(store_id=None, marketplace=None, start_date=None, end_date=None):
    """Get cash flow summary"""
    params = {}
    if store_id:
        params["store_id"] = store_id
    if marketplace:
        params["marketplace"] = marketplace
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    
    resp = session.get(f"{BASE_URL}/cashflow/summary", params=params)
    assert resp.status_code == 200, f"Summary failed: {resp.status_code} {resp.text}"
    return resp.json()

def get_cashflow_entries(store_id=None, marketplace=None, start_date=None, end_date=None):
    """Get cash flow entries"""
    params = {}
    if store_id:
        params["store_id"] = store_id
    if marketplace:
        params["marketplace"] = marketplace
    if start_date:
        params["start_date"] = start_date
    if end_date:
        params["end_date"] = end_date
    
    resp = session.get(f"{BASE_URL}/cashflow/entries", params=params)
    assert resp.status_code == 200, f"Entries failed: {resp.status_code} {resp.text}"
    return resp.json()

def set_opening_balance(store_id, amount_usd, note=""):
    """Set opening balance for a store"""
    print(f"\n💰 Setting opening balance: store={store_id}, amount=${amount_usd}")
    resp = session.put(f"{BASE_URL}/cashflow/opening-balance", json={
        "store_id": store_id,
        "amount_usd": amount_usd,
        "note": note
    })
    assert resp.status_code == 200, f"Opening balance failed: {resp.status_code} {resp.text}"
    print(f"✅ Opening balance set: ${amount_usd}")
    return resp.json()

def create_manual_entry(store_id, date, direction, category, amount_usd, description="", marketplace=""):
    """Create manual cash flow entry"""
    print(f"\n✏️ Creating manual entry: {direction} ${amount_usd} - {category}")
    resp = session.post(f"{BASE_URL}/cashflow/manual", json={
        "store_id": store_id,
        "marketplace": marketplace,
        "date": date,
        "direction": direction,
        "category": category,
        "amount_usd": amount_usd,
        "description": description
    })
    assert resp.status_code == 201, f"Manual entry failed: {resp.status_code} {resp.text}"
    entry = resp.json()
    print(f"✅ Manual entry created: {entry['id']}")
    return entry

def get_opening_balances():
    """Get all opening balances"""
    resp = session.get(f"{BASE_URL}/cashflow/opening-balances")
    assert resp.status_code == 200, f"Opening balances failed: {resp.status_code} {resp.text}"
    return resp.json()

def get_audit_log(store_id=None):
    """Get audit log"""
    params = {}
    if store_id:
        params["store_id"] = store_id
    resp = session.get(f"{BASE_URL}/cashflow/audit", params=params)
    assert resp.status_code == 200, f"Audit log failed: {resp.status_code} {resp.text}"
    return resp.json()

def seed_sellerflash_cost(store_id, seller_order_id, product_cost, shipping_cost, order_date, marketplace="US"):
    """Seed SellerFlash cost record directly in MongoDB"""
    from pymongo import MongoClient
    import uuid
    
    client = MongoClient("mongodb://localhost:27017")
    db = client["amazon_seller_suite"]
    
    now = datetime.utcnow().isoformat()
    record = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "store_id": store_id,
        "marketplace": marketplace,
        "seller_order_id": seller_order_id,
        "product_cost": product_cost,
        "initial_shipment_cost": shipping_cost,
        "product_cost_usd": product_cost,
        "shipping_cost_usd": shipping_cost,
        "order_date": order_date,
        "currency": "USD",
        "match_status": "matched",
        "source": "sellerflash",
        "first_imported_at": now,
        "last_seen_at": now
    }
    
    db.sellerflash_costs.insert_one(record)
    test_sellerflash_records.append(record["id"])
    print(f"✅ SellerFlash cost seeded: {seller_order_id} (product=${product_cost}, shipping=${shipping_cost})")
    client.close()
    return record

def seed_fba_allocation(store_id, marketplace, amazon_order_id, order_item_id, sku, order_date, quantity, lot_id, 
                       allocated_product_cost_usd, allocated_inbound_cost_usd, total_allocated_cost_usd):
    """Seed FBA allocation directly in MongoDB"""
    from pymongo import MongoClient
    import uuid
    
    client = MongoClient("mongodb://localhost:27017")
    db = client["amazon_seller_suite"]
    
    now = datetime.utcnow().isoformat()
    allocation = {
        "id": str(uuid.uuid4()),
        "user_id": user_id,
        "store_id": store_id,
        "marketplace": marketplace,
        "amazon_order_id": amazon_order_id,
        "order_item_id": order_item_id,
        "sku": sku,
        "asin": f"B0TEST{sku[:6]}",
        "order_date": order_date,
        "quantity": quantity,
        "lot_id": lot_id,
        "lot_code": "LOT-0001",
        "product_unit_cost_usd": allocated_product_cost_usd / quantity,
        "inbound_unit_cost_usd": allocated_inbound_cost_usd / quantity,
        "landed_unit_cost_usd": total_allocated_cost_usd / quantity,
        "allocated_product_cost_usd": allocated_product_cost_usd,
        "allocated_inbound_cost_usd": allocated_inbound_cost_usd,
        "total_allocated_cost_usd": total_allocated_cost_usd,
        "status": "active",
        "allocated_at": now
    }
    
    db.fba_allocations.insert_one(allocation)
    test_allocations.append(allocation["id"])
    print(f"✅ FBA allocation seeded: {amazon_order_id} (qty={quantity}, cost=${total_allocated_cost_usd})")
    
    # Also decrement lot remaining_quantity
    db.fba_lots.update_one(
        {"id": lot_id},
        {"$inc": {"remaining_quantity": -quantity}}
    )
    
    client.close()
    return allocation

def cleanup_test_data():
    """Clean up ALL test data"""
    print("\n\n🧹 CLEANING UP TEST DATA...")
    
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    db = client["amazon_seller_suite"]
    
    # Delete cash flow entries for test stores
    if test_stores:
        result = db.cash_flow_entries.delete_many({"store_id": {"$in": test_stores}})
        print(f"✅ Deleted {result.deleted_count} cash flow entries")
    
    # Delete opening balances for test stores
    if test_stores:
        result = db.cash_flow_opening_balances.delete_many({"store_id": {"$in": test_stores}})
        print(f"✅ Deleted {result.deleted_count} opening balances")
    
    # Delete audit logs for test stores
    if test_stores:
        result = db.cash_flow_audit.delete_many({"store_id": {"$in": test_stores}})
        print(f"✅ Deleted {result.deleted_count} audit logs")
    
    # Delete FBA allocations
    if test_allocations:
        result = db.fba_allocations.delete_many({"id": {"$in": test_allocations}})
        print(f"✅ Deleted {result.deleted_count} FBA allocations")
    
    # Delete SellerFlash costs
    if test_sellerflash_records:
        result = db.sellerflash_costs.delete_many({"id": {"$in": test_sellerflash_records}})
        print(f"✅ Deleted {result.deleted_count} SellerFlash costs")
    
    # Delete FBA lots via API
    for lot_id in test_lots:
        try:
            # Close lot first, then delete via MongoDB
            db.fba_lots.delete_one({"id": lot_id})
        except Exception as e:
            print(f"⚠️ Failed to delete lot {lot_id}: {e}")
    if test_lots:
        print(f"✅ Deleted {len(test_lots)} FBA lots")
    
    # Delete transactions for test stores
    if test_stores:
        result = db.transactions.delete_many({"store_id": {"$in": test_stores}})
        print(f"✅ Deleted {result.deleted_count} transactions")
    
    # Delete stores via API
    for store_id in test_stores:
        try:
            resp = session.delete(f"{BASE_URL}/stores/{store_id}")
            if resp.status_code == 200:
                print(f"✅ Deleted store: {store_id}")
        except Exception as e:
            print(f"⚠️ Failed to delete store {store_id}: {e}")
    
    client.close()
    print("✅ Cleanup complete!")

def verify_ngtrade_intact():
    """Verify NGTRADE store is intact"""
    print("\n🔍 Verifying NGTRADE store is intact...")
    resp = session.get(f"{BASE_URL}/stores")
    assert resp.status_code == 200
    stores = resp.json()
    ngtrade = [s for s in stores if s["name"] == "NGTRADE"]
    if ngtrade:
        print(f"✅ NGTRADE store intact: {ngtrade[0]['id']}")
    else:
        print("ℹ️ NGTRADE store not found (may not exist in this environment)")

# ============================================================================
# TEST 1: FBA lot cash out
# ============================================================================
def test_1_fba_lot_cash_out():
    print("\n" + "="*80)
    print("TEST 1: FBA lot cash out")
    print("="*80)
    
    # Create CF_TEST store A
    store_a = create_test_store("CF_TEST_STORE_A", ["US"], "USD")
    
    # Create FBA lot: 100 units, $8.00 each, $150 inbound
    lot = create_fba_lot(
        store_id=store_a["id"],
        sku="CF-TEST-SKU-001",
        purchase_date="2026-09-01",
        original_quantity=100,
        product_unit_cost_usd=8.00,
        inbound_shipping_total_usd=150.00
    )
    
    # Get summary
    summary = get_cashflow_summary(store_id=store_a["id"])
    
    print(f"\n📊 Summary:")
    print(f"  cash_out: ${summary['cash_out']}")
    print(f"  inventory_purchases: ${summary['inventory_purchases']}")
    print(f"  current_inventory_value: ${summary['current_inventory_value']}")
    
    # Get entries
    entries_data = get_cashflow_entries(store_id=store_a["id"])
    entries = entries_data["rows"]
    
    print(f"\n📋 Entries ({len(entries)}):")
    for e in entries:
        print(f"  - {e['source_type']}: ${e.get('cash_out', 0)} on {e['date']} (lot_id: {e.get('lot_id', 'N/A')})")
    
    # Verify expectations
    assert summary["cash_out"] == 950.00, f"Expected cash_out=950.00, got {summary['cash_out']}"
    assert summary["inventory_purchases"] == 950.00, f"Expected inventory_purchases=950.00, got {summary['inventory_purchases']}"
    assert summary["current_inventory_value"] == 950.00, f"Expected current_inventory_value=950.00, got {summary['current_inventory_value']}"
    
    # Verify two entries
    purchase_entries = [e for e in entries if e["source_type"] == "FBA_INVENTORY_PURCHASE"]
    shipping_entries = [e for e in entries if e["source_type"] == "FBA_INBOUND_SHIPPING"]
    
    assert len(purchase_entries) == 1, f"Expected 1 FBA_INVENTORY_PURCHASE entry, got {len(purchase_entries)}"
    assert len(shipping_entries) == 1, f"Expected 1 FBA_INBOUND_SHIPPING entry, got {len(shipping_entries)}"
    
    assert purchase_entries[0]["cash_out"] == 800.00, f"Expected purchase=800.00, got {purchase_entries[0]['cash_out']}"
    assert shipping_entries[0]["cash_out"] == 150.00, f"Expected shipping=150.00, got {shipping_entries[0]['cash_out']}"
    assert purchase_entries[0]["date"] == "2026-09-01", f"Expected date=2026-09-01, got {purchase_entries[0]['date']}"
    assert purchase_entries[0]["lot_id"] == lot["id"], f"Expected lot_id={lot['id']}, got {purchase_entries[0]['lot_id']}"
    
    print("\n✅ TEST 1 PASSED")
    return store_a, lot

# ============================================================================
# TEST 2: FIFO sale does NOT touch cash
# ============================================================================
def test_2_fifo_sale_no_cash(store_a, lot):
    print("\n" + "="*80)
    print("TEST 2: FIFO sale does NOT touch cash")
    print("="*80)
    
    # Simulate a sale of 2 units with FIFO cost 19.00
    # Seed FBA allocation
    allocation = seed_fba_allocation(
        store_id=store_a["id"],
        marketplace="US",
        amazon_order_id="CF-TEST-ORDER-1",
        order_item_id="it1",
        sku="CF-TEST-SKU-001",
        order_date="2026-09-10",
        quantity=2,
        lot_id=lot["id"],
        allocated_product_cost_usd=16.00,  # 2 * 8.00
        allocated_inbound_cost_usd=3.00,   # 2 * 1.50
        total_allocated_cost_usd=19.00
    )
    
    # Get summary again
    summary = get_cashflow_summary(store_id=store_a["id"])
    
    print(f"\n📊 Summary after FIFO sale:")
    print(f"  cash_out: ${summary['cash_out']}")
    print(f"  realized_inventory_cost: ${summary['realized_inventory_cost']}")
    print(f"  current_inventory_value: ${summary['current_inventory_value']}")
    
    # Get entries
    entries_data = get_cashflow_entries(store_id=store_a["id"])
    entries = entries_data["rows"]
    
    print(f"\n📋 Entries ({len(entries)}):")
    for e in entries:
        print(f"  - {e['source_type']}: ${e.get('cash_out', 0)} (order_id: {e.get('order_id', 'N/A')})")
    
    # Verify expectations
    assert summary["cash_out"] == 950.00, f"Expected cash_out=950.00 (unchanged), got {summary['cash_out']}"
    assert summary["realized_inventory_cost"] == 19.00, f"Expected realized_inventory_cost=19.00, got {summary['realized_inventory_cost']}"
    assert summary["current_inventory_value"] == 931.00, f"Expected current_inventory_value=931.00 (950-19), got {summary['current_inventory_value']}"
    
    # Verify NO new cash flow entry for the FIFO allocation
    order_entries = [e for e in entries if e.get("order_id") == "CF-TEST-ORDER-1"]
    assert len(order_entries) == 0, f"Expected NO cash flow entry for CF-TEST-ORDER-1, got {len(order_entries)}"
    
    # Verify still only 2 entries (purchase + shipping)
    assert len(entries) == 2, f"Expected 2 entries (no new entry for FIFO), got {len(entries)}"
    
    print("\n✅ TEST 2 PASSED")

# ============================================================================
# TEST 3: FBM SellerFlash costs once
# ============================================================================
def test_3_fbm_sellerflash_once(store_a):
    print("\n" + "="*80)
    print("TEST 3: FBM SellerFlash costs once")
    print("="*80)
    
    # Seed SellerFlash cost
    seed_sellerflash_cost(
        store_id=store_a["id"],
        seller_order_id="CF-TEST-FBM-1",
        product_cost=25.0,
        shipping_cost=8.0,
        order_date="2026-09-05",
        marketplace="US"
    )
    
    # Get summary
    summary = get_cashflow_summary(store_id=store_a["id"])
    
    print(f"\n📊 Summary after SellerFlash:")
    print(f"  cash_out: ${summary['cash_out']}")
    
    # Get entries
    entries_data = get_cashflow_entries(store_id=store_a["id"])
    entries = entries_data["rows"]
    
    fbm_product = [e for e in entries if e["source_type"] == "FBM_PRODUCT_COST" and e.get("order_id") == "CF-TEST-FBM-1"]
    fbm_shipping = [e for e in entries if e["source_type"] == "FBM_SHIPPING_COST" and e.get("order_id") == "CF-TEST-FBM-1"]
    
    print(f"\n📋 FBM Entries:")
    print(f"  FBM_PRODUCT_COST: {len(fbm_product)} entries")
    print(f"  FBM_SHIPPING_COST: {len(fbm_shipping)} entries")
    
    # Verify cash_out increased by 33.00
    expected_cash_out = 950.00 + 33.00  # Previous 950 + new 33
    assert summary["cash_out"] == expected_cash_out, f"Expected cash_out={expected_cash_out}, got {summary['cash_out']}"
    
    # Verify entries
    assert len(fbm_product) == 1, f"Expected 1 FBM_PRODUCT_COST entry, got {len(fbm_product)}"
    assert len(fbm_shipping) == 1, f"Expected 1 FBM_SHIPPING_COST entry, got {len(fbm_shipping)}"
    assert fbm_product[0]["cash_out"] == 25.00, f"Expected product=25.00, got {fbm_product[0]['cash_out']}"
    assert fbm_shipping[0]["cash_out"] == 8.00, f"Expected shipping=8.00, got {fbm_shipping[0]['cash_out']}"
    
    # Call GET /summary 3 more times - amounts must not change
    print("\n🔄 Testing idempotency (3 more calls)...")
    for i in range(3):
        summary_again = get_cashflow_summary(store_id=store_a["id"])
        assert summary_again["cash_out"] == expected_cash_out, f"Call {i+1}: cash_out changed to {summary_again['cash_out']}"
        print(f"  Call {i+1}: cash_out=${summary_again['cash_out']} ✓")
    
    print("\n✅ TEST 3 PASSED")

# ============================================================================
# TEST 4: Split SellerFlash completion
# ============================================================================
def test_4_split_sellerflash(store_a):
    print("\n" + "="*80)
    print("TEST 4: Split SellerFlash completion")
    print("="*80)
    
    from pymongo import MongoClient
    import uuid
    
    client = MongoClient("mongodb://localhost:27017")
    db = client["amazon_seller_suite"]
    
    # Seed SellerFlash with ONLY product_cost
    now = datetime.utcnow().isoformat()
    record_id = str(uuid.uuid4())
    record = {
        "id": record_id,
        "user_id": user_id,
        "store_id": store_a["id"],
        "marketplace": "US",
        "seller_order_id": "CF-TEST-FBM-2",
        "product_cost": 10.0,
        "initial_shipment_cost": None,
        "product_cost_usd": 10.0,
        "shipping_cost_usd": None,
        "order_date": "2026-09-06",
        "currency": "USD",
        "match_status": "matched",
        "source": "sellerflash",
        "first_imported_at": now,
        "last_seen_at": now
    }
    db.sellerflash_costs.insert_one(record)
    test_sellerflash_records.append(record_id)
    print(f"✅ SellerFlash seeded with ONLY product_cost=10.0")
    
    # Get summary - should show only product cost
    summary = get_cashflow_summary(store_id=store_a["id"])
    entries_data = get_cashflow_entries(store_id=store_a["id"])
    entries = entries_data["rows"]
    
    fbm2_product = [e for e in entries if e["source_type"] == "FBM_PRODUCT_COST" and e.get("order_id") == "CF-TEST-FBM-2"]
    fbm2_shipping = [e for e in entries if e["source_type"] == "FBM_SHIPPING_COST" and e.get("order_id") == "CF-TEST-FBM-2"]
    
    print(f"\n📋 After first sync (product only):")
    print(f"  FBM_PRODUCT_COST entries: {len(fbm2_product)}")
    print(f"  FBM_SHIPPING_COST entries: {len(fbm2_shipping)}")
    
    assert len(fbm2_product) == 1, f"Expected 1 FBM_PRODUCT_COST entry, got {len(fbm2_product)}"
    assert len(fbm2_shipping) == 0, f"Expected 0 FBM_SHIPPING_COST entries, got {len(fbm2_shipping)}"
    assert fbm2_product[0]["cash_out"] == 10.00, f"Expected product=10.00, got {fbm2_product[0]['cash_out']}"
    
    # Now update the SAME record adding shipping_cost
    db.sellerflash_costs.update_one(
        {"id": record_id},
        {"$set": {
            "initial_shipment_cost": 5.0,
            "shipping_cost_usd": 5.0,
            "last_seen_at": datetime.utcnow().isoformat()
        }}
    )
    print(f"✅ Updated SellerFlash record with shipping_cost=5.0")
    
    # Get summary again
    summary = get_cashflow_summary(store_id=store_a["id"])
    entries_data = get_cashflow_entries(store_id=store_a["id"])
    entries = entries_data["rows"]
    
    fbm2_product = [e for e in entries if e["source_type"] == "FBM_PRODUCT_COST" and e.get("order_id") == "CF-TEST-FBM-2"]
    fbm2_shipping = [e for e in entries if e["source_type"] == "FBM_SHIPPING_COST" and e.get("order_id") == "CF-TEST-FBM-2"]
    
    print(f"\n📋 After second sync (product + shipping):")
    print(f"  FBM_PRODUCT_COST entries: {len(fbm2_product)}")
    print(f"  FBM_SHIPPING_COST entries: {len(fbm2_shipping)}")
    
    assert len(fbm2_product) == 1, f"Expected 1 FBM_PRODUCT_COST entry (no duplicate), got {len(fbm2_product)}"
    assert len(fbm2_shipping) == 1, f"Expected 1 FBM_SHIPPING_COST entry, got {len(fbm2_shipping)}"
    assert fbm2_product[0]["cash_out"] == 10.00, f"Expected product=10.00, got {fbm2_product[0]['cash_out']}"
    assert fbm2_shipping[0]["cash_out"] == 5.00, f"Expected shipping=5.00, got {fbm2_shipping[0]['cash_out']}"
    
    # Verify exactly 2 entries for this order
    fbm2_all = [e for e in entries if e.get("order_id") == "CF-TEST-FBM-2"]
    assert len(fbm2_all) == 2, f"Expected exactly 2 entries for CF-TEST-FBM-2, got {len(fbm2_all)}"
    
    # Verify total = 15.00
    fbm2_total = sum(e.get("cash_out", 0) for e in fbm2_all)
    assert fbm2_total == 15.00, f"Expected total=15.00, got {fbm2_total}"
    
    client.close()
    print("\n✅ TEST 4 PASSED")

# ============================================================================
# TEST 5: Opening + manual math
# ============================================================================
def test_5_opening_manual_math():
    print("\n" + "="*80)
    print("TEST 5: Opening + manual math")
    print("="*80)
    
    # Create CF_TEST store B (empty, US)
    store_b = create_test_store("CF_TEST_STORE_B", ["US"], "USD")
    
    # Set opening balance: $5000
    set_opening_balance(store_b["id"], 5000.0, "Test opening balance")
    
    # Create manual IN: $1000
    create_manual_entry(
        store_id=store_b["id"],
        date="2026-09-03",
        direction="IN",
        category="Sermaye",
        amount_usd=1000.0,
        description="test in"
    )
    
    # Create manual OUT: $600
    create_manual_entry(
        store_id=store_b["id"],
        date="2026-09-04",
        direction="OUT",
        category="Gider",
        amount_usd=600.0,
        description="test out"
    )
    
    # Get summary
    summary = get_cashflow_summary(store_id=store_b["id"])
    
    print(f"\n📊 Summary:")
    print(f"  opening_cash: ${summary['opening_cash']}")
    print(f"  cash_in: ${summary['cash_in']}")
    print(f"  cash_out: ${summary['cash_out']}")
    print(f"  net_cash_flow: ${summary['net_cash_flow']}")
    print(f"  closing_cash: ${summary['closing_cash']}")
    
    # Verify expectations
    assert summary["opening_cash"] == 5000.0, f"Expected opening_cash=5000.0, got {summary['opening_cash']}"
    assert summary["cash_in"] == 1000.0, f"Expected cash_in=1000.0, got {summary['cash_in']}"
    assert summary["cash_out"] == 600.0, f"Expected cash_out=600.0, got {summary['cash_out']}"
    assert summary["net_cash_flow"] == 400.0, f"Expected net_cash_flow=400.0, got {summary['net_cash_flow']}"
    assert summary["closing_cash"] == 5400.0, f"Expected closing_cash=5400.0, got {summary['closing_cash']}"
    
    # Get opening balances
    balances = get_opening_balances()
    store_b_balance = [b for b in balances["balances"] if b["store_id"] == store_b["id"]]
    
    print(f"\n💰 Opening balances:")
    print(f"  Store B balance: ${store_b_balance[0]['amount_usd']}")
    print(f"  History length: {len(store_b_balance[0]['history'])}")
    
    assert len(store_b_balance) == 1, f"Expected 1 balance for store B, got {len(store_b_balance)}"
    assert store_b_balance[0]["amount_usd"] == 5000.0, f"Expected balance=5000.0, got {store_b_balance[0]['amount_usd']}"
    assert len(store_b_balance[0]["history"]) >= 1, f"Expected history length >= 1, got {len(store_b_balance[0]['history'])}"
    
    # Get audit log
    audit = get_audit_log(store_id=store_b["id"])
    
    print(f"\n📜 Audit log:")
    print(f"  Total entries: {len(audit['rows'])}")
    
    # Verify audit log has opening_balance_update + manual_create records
    opening_updates = [r for r in audit["rows"] if r["action"] == "opening_balance_update"]
    manual_creates = [r for r in audit["rows"] if r["action"] == "manual_create"]
    
    print(f"  opening_balance_update: {len(opening_updates)}")
    print(f"  manual_create: {len(manual_creates)}")
    
    assert len(opening_updates) >= 1, f"Expected >= 1 opening_balance_update, got {len(opening_updates)}"
    assert len(manual_creates) == 2, f"Expected 2 manual_create, got {len(manual_creates)}"
    
    print("\n✅ TEST 5 PASSED")
    return store_b

# ============================================================================
# TEST 6: Idempotency
# ============================================================================
def test_6_idempotency(store_a):
    print("\n" + "="*80)
    print("TEST 6: Idempotency")
    print("="*80)
    
    # Get summary and entries 5 times
    print("\n🔄 Calling GET /summary and /entries 5 times...")
    
    summaries = []
    entries_list = []
    
    for i in range(5):
        summary = get_cashflow_summary(store_id=store_a["id"])
        entries_data = get_cashflow_entries(store_id=store_a["id"])
        
        summaries.append(summary)
        entries_list.append(entries_data)
        
        print(f"  Call {i+1}: cash_out=${summary['cash_out']}, entries={len(entries_data['rows'])}")
    
    # Verify all summaries are identical
    for i in range(1, 5):
        assert summaries[i]["cash_out"] == summaries[0]["cash_out"], f"Call {i+1}: cash_out changed"
        assert summaries[i]["cash_in"] == summaries[0]["cash_in"], f"Call {i+1}: cash_in changed"
        assert summaries[i]["closing_cash"] == summaries[0]["closing_cash"], f"Call {i+1}: closing_cash changed"
        assert len(entries_list[i]["rows"]) == len(entries_list[0]["rows"]), f"Call {i+1}: entry count changed"
    
    print(f"\n✅ All 5 calls returned identical results")
    
    # Check for duplicate idem_key in MongoDB
    from pymongo import MongoClient
    client = MongoClient("mongodb://localhost:27017")
    db = client["amazon_seller_suite"]
    
    pipeline = [
        {"$match": {"store_id": store_a["id"]}},
        {"$group": {"_id": "$idem_key", "count": {"$sum": 1}}},
        {"$match": {"count": {"$gt": 1}}}
    ]
    
    duplicates = list(db.cash_flow_entries.aggregate(pipeline))
    
    print(f"\n🔍 Checking for duplicate idem_key in MongoDB...")
    print(f"  Duplicates found: {len(duplicates)}")
    
    assert len(duplicates) == 0, f"Found {len(duplicates)} duplicate idem_key entries: {duplicates}"
    
    client.close()
    print("\n✅ TEST 6 PASSED")

# ============================================================================
# TEST 7: Store filter isolation
# ============================================================================
def test_7_store_filter_isolation(store_a, store_b):
    print("\n" + "="*80)
    print("TEST 7: Store filter isolation")
    print("="*80)
    
    # Get summary for store A
    summary_a = get_cashflow_summary(store_id=store_a["id"])
    
    # Get summary for store B
    summary_b = get_cashflow_summary(store_id=store_b["id"])
    
    # Get unfiltered summary
    summary_all = get_cashflow_summary()
    
    print(f"\n📊 Store A summary:")
    print(f"  opening_cash: ${summary_a['opening_cash']}")
    print(f"  cash_in: ${summary_a['cash_in']}")
    print(f"  cash_out: ${summary_a['cash_out']}")
    print(f"  closing_cash: ${summary_a['closing_cash']}")
    
    print(f"\n📊 Store B summary:")
    print(f"  opening_cash: ${summary_b['opening_cash']}")
    print(f"  cash_in: ${summary_b['cash_in']}")
    print(f"  cash_out: ${summary_b['cash_out']}")
    print(f"  closing_cash: ${summary_b['closing_cash']}")
    
    print(f"\n📊 Unfiltered summary:")
    print(f"  opening_cash: ${summary_all['opening_cash']}")
    print(f"  cash_in: ${summary_all['cash_in']}")
    print(f"  cash_out: ${summary_all['cash_out']}")
    print(f"  closing_cash: ${summary_all['closing_cash']}")
    
    # Verify A's figures exclude B's manual entries and opening balance
    assert summary_a["opening_cash"] == 0.0, f"Store A should have opening_cash=0, got {summary_a['opening_cash']}"
    assert summary_a["cash_in"] == 0.0, f"Store A should have cash_in=0 (no manual IN), got {summary_a['cash_in']}"
    
    # Verify B's figures exclude A's lot
    # Store B should have opening=5000, in=1000, out=600
    assert summary_b["opening_cash"] == 5000.0, f"Store B should have opening_cash=5000, got {summary_b['opening_cash']}"
    assert summary_b["cash_in"] == 1000.0, f"Store B should have cash_in=1000, got {summary_b['cash_in']}"
    assert summary_b["cash_out"] == 600.0, f"Store B should have cash_out=600, got {summary_b['cash_out']}"
    
    # Verify unfiltered includes both stores (but may include other stores like NGTRADE)
    # So we verify unfiltered >= sum of our test stores
    expected_opening = summary_a["opening_cash"] + summary_b["opening_cash"]
    expected_in = summary_a["cash_in"] + summary_b["cash_in"]
    expected_out = summary_a["cash_out"] + summary_b["cash_out"]
    
    print(f"\n🔍 Unfiltered vs combined test stores:")
    print(f"  Test stores opening: ${expected_opening}, Unfiltered: ${summary_all['opening_cash']}")
    print(f"  Test stores cash_in: ${expected_in}, Unfiltered: ${summary_all['cash_in']}")
    print(f"  Test stores cash_out: ${expected_out}, Unfiltered: ${summary_all['cash_out']}")
    
    assert summary_all["opening_cash"] >= expected_opening, f"Unfiltered opening should be >= {expected_opening}, got {summary_all['opening_cash']}"
    assert summary_all["cash_in"] >= expected_in, f"Unfiltered cash_in should be >= {expected_in}, got {summary_all['cash_in']}"
    assert summary_all["cash_out"] >= expected_out, f"Unfiltered cash_out should be >= {expected_out}, got {summary_all['cash_out']}"
    
    print(f"  ✓ Unfiltered includes both test stores (may include NGTRADE and others)")
    
    # Get entries for store B - should show running balance starting from B's opening
    entries_b = get_cashflow_entries(store_id=store_b["id"])
    
    print(f"\n📋 Store B entries ({len(entries_b['rows'])}):")
    for e in entries_b["rows"]:
        print(f"  - {e['category']}: ${e.get('cash_in', 0) or e.get('cash_out', 0)} → balance ${e['running_balance']}")
    
    # Verify running balance starts from 5000
    assert entries_b["opening_cash"] == 5000.0, f"Store B entries should start with opening=5000, got {entries_b['opening_cash']}"
    
    # Verify only B rows
    for e in entries_b["rows"]:
        assert e["store_id"] == store_b["id"], f"Found entry from wrong store: {e['store_id']}"
    
    print("\n✅ TEST 7 PASSED")

# ============================================================================
# TEST 8: Inventory value not double counted
# ============================================================================
def test_8_inventory_not_double_counted(store_a):
    print("\n" + "="*80)
    print("TEST 8: Inventory value not double counted")
    print("="*80)
    
    summary = get_cashflow_summary(store_id=store_a["id"])
    
    print(f"\n📊 Store A summary:")
    print(f"  opening_cash: ${summary['opening_cash']}")
    print(f"  cash_in: ${summary['cash_in']}")
    print(f"  cash_out: ${summary['cash_out']}")
    print(f"  net_cash_flow: ${summary['net_cash_flow']}")
    print(f"  closing_cash: ${summary['closing_cash']}")
    print(f"  current_inventory_value: ${summary['current_inventory_value']}")
    
    # Verify closing_cash = opening_cash + (cash_in - cash_out)
    expected_closing = summary["opening_cash"] + summary["cash_in"] - summary["cash_out"]
    
    print(f"\n🧮 Math check:")
    print(f"  opening_cash: ${summary['opening_cash']}")
    print(f"  + cash_in: ${summary['cash_in']}")
    print(f"  - cash_out: ${summary['cash_out']}")
    print(f"  = expected_closing: ${expected_closing}")
    print(f"  actual closing_cash: ${summary['closing_cash']}")
    
    assert summary["closing_cash"] == expected_closing, f"Closing cash should be {expected_closing}, got {summary['closing_cash']}"
    
    # Verify current_inventory_value appears in payload but is NOT subtracted from closing_cash
    assert "current_inventory_value" in summary, "current_inventory_value should be in payload"
    assert summary["current_inventory_value"] == 931.0, f"Expected current_inventory_value=931.0, got {summary['current_inventory_value']}"
    
    # Verify closing_cash ≠ opening - 950 - 931 (double counting would give -1881)
    wrong_closing = summary["opening_cash"] - 950.0 - 931.0
    assert summary["closing_cash"] != wrong_closing, f"Closing cash should NOT be {wrong_closing} (double counting)"
    
    # Verify cash_out counts the 950 purchase ONCE
    # Store A has: 950 (lot) + 33 (FBM-1) + 15 (FBM-2) = 998
    expected_cash_out = 950.0 + 33.0 + 15.0
    assert summary["cash_out"] == expected_cash_out, f"Expected cash_out={expected_cash_out}, got {summary['cash_out']}"
    
    print("\n✅ TEST 8 PASSED")

# ============================================================================
# SANITY CHECKS
# ============================================================================
def sanity_check_dashboard():
    print("\n" + "="*80)
    print("SANITY CHECK: Dashboard summary")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/dashboard/summary")
    assert resp.status_code == 200, f"Dashboard summary failed: {resp.status_code} {resp.text}"
    
    print("✅ GET /api/dashboard/summary returns 200")

def sanity_check_login():
    print("\n" + "="*80)
    print("SANITY CHECK: Login")
    print("="*80)
    
    resp = session.post(f"{BASE_URL}/auth/login", json={
        "email": ADMIN_EMAIL,
        "password": ADMIN_PASSWORD
    })
    assert resp.status_code == 200, f"Login failed: {resp.status_code} {resp.text}"
    
    print("✅ POST /api/auth/login works")

# ============================================================================
# MAIN
# ============================================================================
def main():
    print("\n" + "="*80)
    print("CASH FLOW MODULE TESTING SUITE")
    print("="*80)
    
    try:
        # Login
        login()
        
        # Run tests
        store_a, lot = test_1_fba_lot_cash_out()
        test_2_fifo_sale_no_cash(store_a, lot)
        test_3_fbm_sellerflash_once(store_a)
        test_4_split_sellerflash(store_a)
        store_b = test_5_opening_manual_math()
        test_6_idempotency(store_a)
        test_7_store_filter_isolation(store_a, store_b)
        test_8_inventory_not_double_counted(store_a)
        
        # Sanity checks
        sanity_check_dashboard()
        sanity_check_login()
        
        print("\n" + "="*80)
        print("✅ ALL TESTS PASSED!")
        print("="*80)
        
    except AssertionError as e:
        print(f"\n❌ TEST FAILED: {e}")
        raise
    except Exception as e:
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        # Cleanup
        cleanup_test_data()
        verify_ngtrade_intact()

if __name__ == "__main__":
    main()
