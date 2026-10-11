"""Amazon Payments import reconciliation — additive module.

Provides a stable, DATE-INDEPENDENT identity for Amazon financial events so that
re-uploaded or overlapping reports never create duplicate revenue/orders, and so
Amazon-side date changes are tracked without overwriting the original date.

Rules enforced here:
- Fingerprints never include any date, import time, or file name.
- original_transaction_date is immutable once written by the caller.
"""
import hashlib

from pymongo import UpdateOne

from finance import money

STATUS_NEW = "new"
STATUS_UNCHANGED = "existing_unchanged"
STATUS_UPDATED = "existing_updated"
STATUS_DATE_CHANGED = "date_changed"
STATUS_POSSIBLE_DUPLICATE = "possible_duplicate"
STATUS_CONFLICT = "conflict"
STATUS_UNMATCHED = "unmatched"

CHANGE_APPLY_STATUSES = (STATUS_NEW, STATUS_UPDATED, STATUS_DATE_CHANGED)


def stable_event_key(doc):
    """Identity of one Amazon financial event, excluding every date field."""
    return "|".join([
        (doc.get("marketplace") or "").strip().upper(),
        (doc.get("order_id") or "").strip(),
        (doc.get("category") or "").strip(),
        (doc.get("sku") or "").strip(),
        str(doc.get("quantity") or "").strip(),
        str(money(doc.get("amount", 0))),
        (doc.get("currency") or "").strip().upper(),
        " ".join(str(doc.get("description") or "").split()).lower(),
    ])


def event_fingerprint(key, occurrence):
    return hashlib.sha256(f"event-v1|{key}|{occurrence}".encode()).hexdigest()


def assign_event_fingerprints(docs):
    """Assign a stable fingerprint per row; duplicates within one file keep order."""
    counts = {}
    for doc in docs:
        key = stable_event_key(doc)
        counts[key] = counts.get(key, 0) + 1
        doc["event_fingerprint"] = event_fingerprint(key, counts[key])
    return docs


def near_key(doc):
    """Loose identity used only to flag possible duplicates for human review."""
    return "|".join([
        (doc.get("order_id") or "").strip(),
        (doc.get("category") or "").strip(),
        str(money(doc.get("amount", 0))),
        (doc.get("currency") or "").strip().upper(),
    ])


def classify_rows(docs, existing_docs):
    """Classify each parsed row against existing canonical records.

    Returns a list parallel to `docs`:
    {"doc", "status", "match", "previous_date"}
    """
    by_event = {}
    by_source = {}
    near_index = set()
    for existing in existing_docs:
        if existing.get("event_fingerprint"):
            by_event.setdefault(existing["event_fingerprint"], existing)
        if existing.get("source_fingerprint"):
            by_source.setdefault(existing["source_fingerprint"], existing)
        if (existing.get("order_id") or "").strip():
            near_index.add(near_key(existing))

    results = []
    for doc in docs:
        match = by_event.get(doc["event_fingerprint"]) or by_source.get(doc["source_fingerprint"])
        status = STATUS_NEW
        previous = None
        if match and (match.get("currency") or "").strip().upper() != (doc.get("currency") or "").strip().upper():
            status = STATUS_CONFLICT
        elif match:
            current_latest = match.get("latest_amazon_reported_date") or match.get("date")
            if doc["date"] == current_latest or doc["date"] == match.get("date"):
                incoming_desc = " ".join(str(doc.get("description") or "").split())
                existing_desc = " ".join(str(match.get("description") or "").split())
                upgraded_txn_id = bool(doc.get("amazon_txn_id")) and not match.get("amazon_txn_id")
                status = STATUS_UPDATED if (incoming_desc != existing_desc or upgraded_txn_id) else STATUS_UNCHANGED
            else:
                status = STATUS_DATE_CHANGED
                previous = current_latest
        elif (doc.get("order_id") or "").strip() and near_key(doc) in near_index:
            status = STATUS_POSSIBLE_DUPLICATE
        results.append({"doc": doc, "status": status, "match": match, "previous_date": previous})
    return results


def legacy_date_backfill(now_iso):
    """Pipeline update: fill date-preservation fields for pre-existing records."""
    return [{
        "$set": {
            "original_transaction_date": "$date",
            "latest_amazon_reported_date": "$date",
            "first_seen_at": {"$ifNull": ["$created_at", now_iso]},
            "last_seen_at": {"$ifNull": ["$created_at", now_iso]},
            "date_changed": False,
        }
    }]


async def backfill_event_fingerprints(db):
    """Assign stable event fingerprints to legacy Amazon CSV imports (idempotent)."""
    docs = await db.transactions.find(
        {"source": "amazon_payments_csv", "event_fingerprint": {"$exists": False}},
        {"_id": 0},
    ).to_list(None)
    if not docs:
        return 0
    counts = {}
    operations = []
    for doc in sorted(docs, key=lambda d: (d.get("created_at") or "", d.get("id") or "")):
        partition = (doc.get("user_id"), doc.get("store_id"), stable_event_key(doc))
        counts[partition] = counts.get(partition, 0) + 1
        fingerprint = event_fingerprint(partition[2], counts[partition])
        operations.append(UpdateOne(
            {"id": doc["id"], "user_id": doc["user_id"]},
            {"$set": {"event_fingerprint": fingerprint}},
        ))
    for start in range(0, len(operations), 500):
        await db.transactions.bulk_write(operations[start:start + 500], ordered=False)
    return len(operations)
