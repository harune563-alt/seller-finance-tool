#!/usr/bin/env python3
"""
Scoped Matcher Bug Fix Verification for Order 701-7543735-7207422

This test verifies that the Amazon Orders / Fulfillment Import module correctly:
1. Matches orders by querying db.transactions (not just amazon_orders registry)
2. Identifies enrichment state (unchanged item + unenriched transaction = "enrich")
3. Enriches existing transactions without modifying financial fields
4. Achieves full idempotency on re-upload
"""

import os
import sys
import requests
from pymongo import MongoClient
import json

# Load environment
with open('/app/backend/.env') as f:
    for line in f:
        if '=' in line and not line.startswith('#'):
            key, val = line.strip().split('=', 1)
            os.environ[key] = val

BASE_URL = "https://sellerfin-tool.preview.emergentagent.com/api"
MONGO_URL = os.environ['MONGO_URL']
DB_NAME = os.environ['DB_NAME']

# Test credentials
EMAIL = "admin@amzsuite.com"
PASSWORD = "admin123"

# Order details
ORDER_ID = "701-7543735-7207422"
TRANSACTION_ID = "675c3d9e-eb9a-4c9d-8118-23eca261f183"
ORDER_ITEM_ID = "171879845183561"

def login():
    """Login and return session with cookies"""
    session = requests.Session()
    resp = session.post(f"{BASE_URL}/auth/login", json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        print(f"❌ Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    print(f"✅ Login successful")
    return session

def get_db():
    """Get MongoDB database connection"""
    client = MongoClient(MONGO_URL)
    return client[DB_NAME]

def get_transaction_state(db):
    """Get current state of the transaction"""
    tx = db.transactions.find_one({"id": TRANSACTION_ID})
    if not tx:
        print(f"❌ Transaction {TRANSACTION_ID} not found")
        sys.exit(1)
    return {
        "id": tx.get("id"),
        "type": tx.get("type"),
        "amount": tx.get("amount"),
        "currency": tx.get("currency"),
        "date": tx.get("date"),
        "category": tx.get("category"),
        "order_id": tx.get("order_id"),
        "fulfillment_type": tx.get("fulfillment_type"),
        "amazon_order_item_ids": tx.get("amazon_order_item_ids"),
        "fulfillment_last_updated_at": tx.get("fulfillment_last_updated_at"),
    }

def get_item_state(db):
    """Get current state of the amazon order item"""
    item = db.amazon_order_items.find_one({"amazon_order_id": ORDER_ID, "order_item_id": ORDER_ITEM_ID})
    if not item:
        print(f"❌ Amazon order item {ORDER_ID}/{ORDER_ITEM_ID} not found")
        sys.exit(1)
    return {
        "match_status": item.get("match_status"),
        "sku": item.get("sku"),
        "asin": item.get("asin"),
        "quantity": item.get("quantity"),
    }

def get_canonical_order_state(db):
    """Get current state of the canonical amazon order"""
    order = db.amazon_orders.find_one({"order_id": ORDER_ID})
    if order:
        return {
            "fulfillment_type": order.get("fulfillment_type"),
            "marketplace": order.get("marketplace"),
        }
    return None

def count_transactions(db, user_id):
    """Count total transactions for user"""
    return db.transactions.count_documents({"user_id": user_id})

def upload_tsv(session, commit=False):
    """Upload the test TSV file"""
    with open('/app/test_order_701.tsv', 'rb') as f:
        files = {'file': ('test_order_701.tsv', f, 'text/tab-separated-values')}
        data = {'commit': 'true' if commit else 'false'}
        resp = session.post(f"{BASE_URL}/amazon-orders/import", files=files, data=data)
    
    if resp.status_code != 200:
        print(f"❌ Upload failed: {resp.status_code}")
        print(f"Response: {resp.text}")
        return None
    
    return resp.json()

def verify_preview_response(result):
    """Verify STEP 1: Preview response"""
    print("\n" + "="*80)
    print("STEP 1: PREVIEW (commit=false)")
    print("="*80)
    
    # Check summary counts (at top level)
    print(f"\nSummary:")
    print(f"  enrichment_required: {result.get('enrichment_required')}")
    print(f"  unchanged: {result.get('unchanged')}")
    print(f"  new: {result.get('new')}")
    print(f"  matched: {result.get('matched')}")
    print(f"  total_rows: {result.get('total_rows')}")
    
    # Verify expected values
    errors = []
    if result.get('enrichment_required') != 1:
        errors.append(f"Expected enrichment_required=1, got {result.get('enrichment_required')}")
    if result.get('unchanged') != 0:
        errors.append(f"Expected unchanged=0, got {result.get('unchanged')}")
    if result.get('new') != 0:
        errors.append(f"Expected new=0, got {result.get('new')}")
    
    # Check row details (in 'preview' key)
    rows = result.get("preview", [])
    if len(rows) != 1:
        errors.append(f"Expected 1 row, got {len(rows)}")
    else:
        row = rows[0]
        print(f"\nRow details:")
        print(f"  matched: {row.get('matched')}")
        print(f"  resolved_fulfillment: {row.get('resolved_fulfillment')}")
        print(f"  action: {row.get('action')}")
        print(f"  amazon_order_id: {row.get('amazon_order_id')}")
        print(f"  order_item_id: {row.get('order_item_id')}")
        
        if not row.get('matched'):
            errors.append(f"Expected matched=true, got {row.get('matched')}")
        if row.get('resolved_fulfillment') != 'FBA':
            errors.append(f"Expected resolved_fulfillment=FBA, got {row.get('resolved_fulfillment')}")
        if row.get('action') != 'enrich':
            errors.append(f"Expected action=enrich, got {row.get('action')}")
    
    if errors:
        print(f"\n❌ STEP 1 FAILED:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print(f"\n✅ STEP 1 PASSED: Preview shows matched=true, resolved_fulfillment=FBA, action=enrich, enrichment_required=1")
        return True

def verify_preview_readonly(db, tx_before, item_before, tx_count_before):
    """Verify that preview is READ-ONLY"""
    print("\n" + "-"*80)
    print("VERIFYING PREVIEW IS READ-ONLY")
    print("-"*80)
    
    tx_after = get_transaction_state(db)
    item_after = get_item_state(db)
    tx_count_after = count_transactions(db, tx_before.get("user_id") or "test_user")
    
    errors = []
    
    # Transaction should be unchanged
    if tx_after.get("fulfillment_type") is not None:
        errors.append(f"Transaction fulfillment_type should be None, got {tx_after.get('fulfillment_type')}")
    if tx_after.get("amazon_order_item_ids") is not None:
        errors.append(f"Transaction amazon_order_item_ids should be None, got {tx_after.get('amazon_order_item_ids')}")
    if tx_after.get("fulfillment_last_updated_at") is not None:
        errors.append(f"Transaction fulfillment_last_updated_at should be None, got {tx_after.get('fulfillment_last_updated_at')}")
    
    # Item match_status should still be unmatched
    if item_after.get("match_status") != "unmatched":
        errors.append(f"Item match_status should be 'unmatched', got {item_after.get('match_status')}")
    
    # Transaction count should be unchanged
    if tx_count_after != tx_count_before:
        errors.append(f"Transaction count changed from {tx_count_before} to {tx_count_after}")
    
    if errors:
        print(f"\n❌ PREVIEW READ-ONLY CHECK FAILED:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print(f"\n✅ PREVIEW IS READ-ONLY: Transaction and item unchanged, no new transactions")
        return True

def verify_apply_response(result):
    """Verify STEP 2: Apply response"""
    print("\n" + "="*80)
    print("STEP 2: APPLY (commit=true)")
    print("="*80)
    
    print(f"\nSummary:")
    print(f"  enrichment_required: {result.get('enrichment_required')}")
    print(f"  unchanged: {result.get('unchanged')}")
    print(f"  new: {result.get('new')}")
    print(f"  committed: {result.get('committed')}")
    
    errors = []
    if not result.get('committed'):
        errors.append(f"Expected committed=true, got {result.get('committed')}")
    
    if errors:
        print(f"\n❌ STEP 2 RESPONSE CHECK FAILED:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print(f"\n✅ STEP 2 RESPONSE OK: committed=true")
        return True

def verify_apply_effects(db, tx_before, tx_count_before):
    """Verify STEP 2: Database effects after apply"""
    print("\n" + "-"*80)
    print("VERIFYING APPLY EFFECTS")
    print("-"*80)
    
    tx_after = get_transaction_state(db)
    item_after = get_item_state(db)
    canonical_after = get_canonical_order_state(db)
    tx_count_after = count_transactions(db, tx_before.get("user_id") or "test_user")
    
    print(f"\nTransaction after apply:")
    print(f"  fulfillment_type: {tx_after.get('fulfillment_type')}")
    print(f"  amazon_order_item_ids: {tx_after.get('amazon_order_item_ids')}")
    print(f"  fulfillment_last_updated_at: {tx_after.get('fulfillment_last_updated_at')}")
    print(f"  amount: {tx_after.get('amount')} (was {tx_before.get('amount')})")
    print(f"  date: {tx_after.get('date')} (was {tx_before.get('date')})")
    print(f"  type: {tx_after.get('type')} (was {tx_before.get('type')})")
    print(f"  category: {tx_after.get('category')} (was {tx_before.get('category')})")
    
    print(f"\nItem after apply:")
    print(f"  match_status: {item_after.get('match_status')}")
    
    print(f"\nCanonical order after apply:")
    if canonical_after:
        print(f"  fulfillment_type: {canonical_after.get('fulfillment_type')}")
        print(f"  marketplace: {canonical_after.get('marketplace')}")
    else:
        print(f"  NOT FOUND")
    
    print(f"\nTransaction count: {tx_count_before} -> {tx_count_after}")
    
    errors = []
    
    # Transaction should have fulfillment fields
    if tx_after.get("fulfillment_type") != "FBA":
        errors.append(f"Expected fulfillment_type=FBA, got {tx_after.get('fulfillment_type')}")
    if tx_after.get("amazon_order_item_ids") != [ORDER_ITEM_ID]:
        errors.append(f"Expected amazon_order_item_ids=['{ORDER_ITEM_ID}'], got {tx_after.get('amazon_order_item_ids')}")
    if tx_after.get("fulfillment_last_updated_at") is None:
        errors.append(f"Expected fulfillment_last_updated_at to be set, got None")
    
    # Financial fields should be unchanged
    if tx_after.get("amount") != tx_before.get("amount"):
        errors.append(f"Amount changed from {tx_before.get('amount')} to {tx_after.get('amount')}")
    if tx_after.get("date") != tx_before.get("date"):
        errors.append(f"Date changed from {tx_before.get('date')} to {tx_after.get('date')}")
    if tx_after.get("type") != tx_before.get("type"):
        errors.append(f"Type changed from {tx_before.get('type')} to {tx_after.get('type')}")
    if tx_after.get("category") != tx_before.get("category"):
        errors.append(f"Category changed from {tx_before.get('category')} to {tx_after.get('category')}")
    
    # Item match_status should be "matched"
    if item_after.get("match_status") != "matched":
        errors.append(f"Expected item match_status=matched, got {item_after.get('match_status')}")
    
    # Canonical order should exist with FBA
    if not canonical_after:
        errors.append(f"Canonical order not created")
    elif canonical_after.get("fulfillment_type") != "FBA":
        errors.append(f"Expected canonical order fulfillment_type=FBA, got {canonical_after.get('fulfillment_type')}")
    
    # Transaction count should be unchanged (no new transaction)
    if tx_count_after != tx_count_before:
        errors.append(f"Transaction count changed from {tx_count_before} to {tx_count_after} (expected no change)")
    
    if errors:
        print(f"\n❌ STEP 2 EFFECTS CHECK FAILED:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print(f"\n✅ STEP 2 PASSED: Transaction enriched with fulfillment fields, financial fields unchanged, item matched, no new transaction")
        return True

def verify_reupload_response(result):
    """Verify STEP 3: Re-upload response"""
    print("\n" + "="*80)
    print("STEP 3: RE-UPLOAD (commit=false)")
    print("="*80)
    
    print(f"\nSummary:")
    print(f"  enrichment_required: {result.get('enrichment_required')}")
    print(f"  unchanged: {result.get('unchanged')}")
    print(f"  new: {result.get('new')}")
    print(f"  matched: {result.get('matched')}")
    
    rows = result.get("preview", [])
    if len(rows) > 0:
        row = rows[0]
        print(f"\nRow details:")
        print(f"  action: {row.get('action')}")
        print(f"  matched: {row.get('matched')}")
    
    errors = []
    if result.get('enrichment_required') != 0:
        errors.append(f"Expected enrichment_required=0, got {result.get('enrichment_required')}")
    if result.get('unchanged') != 1:
        errors.append(f"Expected unchanged=1, got {result.get('unchanged')}")
    if len(rows) > 0 and row.get('action') != 'no_change':
        errors.append(f"Expected action=no_change, got {row.get('action')}")
    
    if errors:
        print(f"\n❌ STEP 3 FAILED:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print(f"\n✅ STEP 3 PASSED: Re-upload shows action=no_change, unchanged=1, enrichment_required=0 (full idempotency)")
        return True

def verify_history_endpoint(session):
    """Verify STEP 4: History endpoint"""
    print("\n" + "="*80)
    print("STEP 4: HISTORY ENDPOINT")
    print("="*80)
    
    resp = session.get(f"{BASE_URL}/amazon-orders/history")
    if resp.status_code != 200:
        print(f"❌ History endpoint failed: {resp.status_code}")
        return False
    
    history = resp.json()
    print(f"\nHistory response:")
    print(f"  Total batches: {len(history)}")
    
    if len(history) > 0:
        latest = history[0]
        print(f"\nLatest batch:")
        print(f"  file_name: {latest.get('file_name')}")
        print(f"  status: {latest.get('status')}")
        print(f"  enrichment_required: {latest.get('enrichment_required')}")
        print(f"  new: {latest.get('new')}")
        print(f"  unchanged: {latest.get('unchanged')}")
    
    errors = []
    if len(history) == 0:
        errors.append(f"Expected at least 1 batch in history, got 0")
    
    if errors:
        print(f"\n❌ STEP 4 FAILED:")
        for error in errors:
            print(f"   - {error}")
        return False
    else:
        print(f"\n✅ STEP 4 PASSED: History endpoint returns batches with enrichment_required field")
        return True

def main():
    print("="*80)
    print("SCOPED MATCHER BUG FIX VERIFICATION")
    print("Order: 701-7543735-7207422")
    print("="*80)
    
    # Login
    session = login()
    
    # Get database connection
    db = get_db()
    
    # Get initial state
    print("\n" + "="*80)
    print("INITIAL STATE")
    print("="*80)
    tx_before = get_transaction_state(db)
    item_before = get_item_state(db)
    canonical_before = get_canonical_order_state(db)
    tx_count_before = count_transactions(db, tx_before.get("user_id") or "test_user")
    
    print(f"\nTransaction {TRANSACTION_ID}:")
    print(f"  amount: {tx_before.get('amount')} {tx_before.get('currency')}")
    print(f"  date: {tx_before.get('date')}")
    print(f"  type: {tx_before.get('type')}")
    print(f"  category: {tx_before.get('category')}")
    print(f"  fulfillment_type: {tx_before.get('fulfillment_type')}")
    print(f"  amazon_order_item_ids: {tx_before.get('amazon_order_item_ids')}")
    
    print(f"\nItem {ORDER_ITEM_ID}:")
    print(f"  match_status: {item_before.get('match_status')}")
    print(f"  sku: {item_before.get('sku')}")
    print(f"  asin: {item_before.get('asin')}")
    
    print(f"\nCanonical order:")
    if canonical_before:
        print(f"  fulfillment_type: {canonical_before.get('fulfillment_type')}")
    else:
        print(f"  NOT FOUND (will be created)")
    
    print(f"\nTotal transactions: {tx_count_before}")
    
    # STEP 1: Preview (commit=false)
    print("\n" + "="*80)
    print("UPLOADING TSV FOR PREVIEW")
    print("="*80)
    result_preview = upload_tsv(session, commit=False)
    if not result_preview:
        print("❌ Preview upload failed")
        sys.exit(1)
    
    step1_pass = verify_preview_response(result_preview)
    step1_readonly_pass = verify_preview_readonly(db, tx_before, item_before, tx_count_before)
    
    # STEP 2: Apply (commit=true)
    print("\n" + "="*80)
    print("UPLOADING TSV FOR APPLY")
    print("="*80)
    result_apply = upload_tsv(session, commit=True)
    if not result_apply:
        print("❌ Apply upload failed")
        sys.exit(1)
    
    step2_response_pass = verify_apply_response(result_apply)
    step2_effects_pass = verify_apply_effects(db, tx_before, tx_count_before)
    
    # STEP 3: Re-upload (commit=false)
    print("\n" + "="*80)
    print("RE-UPLOADING TSV FOR IDEMPOTENCY CHECK")
    print("="*80)
    result_reupload = upload_tsv(session, commit=False)
    if not result_reupload:
        print("❌ Re-upload failed")
        sys.exit(1)
    
    step3_pass = verify_reupload_response(result_reupload)
    
    # STEP 4: History endpoint
    step4_pass = verify_history_endpoint(session)
    
    # Final summary
    print("\n" + "="*80)
    print("FINAL SUMMARY")
    print("="*80)
    
    all_pass = (
        step1_pass and 
        step1_readonly_pass and 
        step2_response_pass and 
        step2_effects_pass and 
        step3_pass and 
        step4_pass
    )
    
    print(f"\nSTEP 1 (Preview): {'✅ PASS' if step1_pass else '❌ FAIL'}")
    print(f"STEP 1 (Read-only): {'✅ PASS' if step1_readonly_pass else '❌ FAIL'}")
    print(f"STEP 2 (Apply response): {'✅ PASS' if step2_response_pass else '❌ FAIL'}")
    print(f"STEP 2 (Apply effects): {'✅ PASS' if step2_effects_pass else '❌ FAIL'}")
    print(f"STEP 3 (Re-upload): {'✅ PASS' if step3_pass else '❌ FAIL'}")
    print(f"STEP 4 (History): {'✅ PASS' if step4_pass else '❌ FAIL'}")
    
    if all_pass:
        print(f"\n{'='*80}")
        print(f"✅ ALL TESTS PASSED - SCOPED MATCHER BUG FIX VERIFIED")
        print(f"{'='*80}")
        sys.exit(0)
    else:
        print(f"\n{'='*80}")
        print(f"❌ SOME TESTS FAILED")
        print(f"{'='*80}")
        sys.exit(1)

if __name__ == "__main__":
    main()
