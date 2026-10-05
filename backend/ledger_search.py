"""Search ledger history without truncating or partially valuing an order."""
import re
from collections import defaultdict
from decimal import Decimal
from finance import COST_FIELDS, RECOVERY_FIELDS
from usd_ledger import enrich_records


def order_key(tx):
    order_id = (tx.get("order_id") or "").strip()
    return (tx["store_id"], tx["marketplace"], tx["currency"], "order" if order_id else "single", order_id or tx["id"])


def order_outcome(rows):
    if any(tx.get("fx_status") != "ready" for tx in rows):
        return "unknown"
    net = Decimal(0)
    for tx in rows:
        amount = Decimal(str(tx["amount_usd"]))
        net += amount if tx["type"] == "income" else -amount
        if tx["type"] == "income":
            net -= sum(Decimal(str(tx["usd_costs"].get(k, 0))) for k in COST_FIELDS)
        if tx["category"] == "Refunds":
            net += sum(Decimal(str(tx["usd_costs"].get(k, 0))) for k in RECOVERY_FIELDS)
    return "profit" if net > 0 else "loss" if net < 0 else "neutral"


async def search_history(db, scope, view, search, category, start_date, end_date, outcome, page, page_size):
    query = {**scope, "type": "payout" if view == "payouts" else {"$in": ["income", "expense"]}}
    text = search.strip()
    if text:
        literal = {"$regex": re.escape(text), "$options": "i"}
        if view == "payouts":
            query["$or"] = [{"payment_reference": literal}, {"description": literal}]
        else:
            query["order_id"] = literal
    def date_and_category_match(tx):
        return (not category or tx["category"] == category) and (not start_date or tx["date"] >= start_date) and (not end_date or tx["date"] <= end_date)
    if view == "payouts":
        if category:
            query["category"] = category
        if start_date or end_date:
            query["date"] = {}
            if start_date: query["date"]["$gte"] = start_date
            if end_date: query["date"]["$lte"] = end_date
        total = await db.transactions.count_documents(query)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        rows = await db.transactions.find(query, {"_id": 0}).sort([("date", -1), ("id", 1)]).skip((page - 1) * page_size).to_list(page_size)
    else:
        # Match whole order groups, then page the groups (never individual children).
        rows = await db.transactions.find(query, {"_id": 0}).sort([("date", -1), ("id", 1)]).to_list(None)
        groups = defaultdict(list)
        for tx in rows:
            groups[order_key(tx)].append(tx)
        groups = [records for records in groups.values() if any(date_and_category_match(tx) for tx in records)]
        if outcome != "all":
            enriched = await enrich_records(db, [tx for records in groups for tx in records])
            by_id = {tx["id"]: tx for tx in enriched}
            groups = [[by_id[tx["id"]] for tx in records] for records in groups]
            groups = [records for records in groups if order_outcome(records) == outcome]
        total = len(groups)
        total_pages = max(1, (total + page_size - 1) // page_size)
        page = min(page, total_pages)
        rows = [tx for records in groups[(page - 1) * page_size:page * page_size] for tx in records]
    return {"items": await enrich_records(db, rows), "total": total, "page": page, "page_size": page_size, "total_pages": total_pages}