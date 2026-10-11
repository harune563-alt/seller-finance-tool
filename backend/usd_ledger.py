"""Keep original ledger amounts intact; attach an immutable USD reporting snapshot."""
import asyncio
from decimal import Decimal
from finance import COST_FIELDS, RECOVERY_FIELDS, EXTERNAL_CATEGORIES, money, summarize
from fx_service import FxError, get_rate

FIELDS = [*COST_FIELDS, *RECOVERY_FIELDS]


async def attach_usd(db, document, persist=False):
    doc = dict(document)
    doc.setdefault("cost_currency", doc["currency"])
    if doc["type"] == "payout":
        return {**doc, "fx_status": "not_required", "amount_usd": 0, "usd_costs": {key: 0 for key in FIELDS}}
    if doc.get("fx") and doc.get("amount_usd") is not None and doc.get("usd_costs") is not None:
        return {**doc, "fx_status": "ready", "fx_error": None}
    quote = await get_rate(db, doc["currency"], doc["date"])
    rate = Decimal(quote["rate"])
    cost_rate = Decimal(1) if doc["cost_currency"] == "USD" else rate
    snapshot = {"fx": quote, "amount_usd": float(money(Decimal(str(doc["amount"])) * rate)),
                "usd_costs": {key: float(money(Decimal(str(doc.get(key, 0))) * cost_rate)) for key in FIELDS}}
    if persist:
        # First writer wins; later reads never revalue a saved transaction with a new quote.
        await db.transactions.update_one({"id": doc["id"], "user_id": doc["user_id"], "fx": {"$exists": False}}, {"$set": snapshot})
        stored = await db.transactions.find_one({"id": doc["id"], "user_id": doc["user_id"]}, {"_id": 0})
        if stored and stored.get("fx"):
            snapshot = {key: stored[key] for key in snapshot}
    return {**doc, **snapshot, "fx_status": "ready", "fx_error": None}


async def enrich_records(db, docs, persist=True, strict=False):
    semaphore = asyncio.Semaphore(6)
    async def enrich(doc):
        async with semaphore:
            try:
                return await attach_usd(db, doc, persist=persist)
            except FxError as exc:
                if strict:
                    raise
                return {**doc, "cost_currency": doc.get("cost_currency", doc["currency"]), "fx_status": "unavailable", "fx_error": str(exc), "amount_usd": None, "usd_costs": {}}
    return await asyncio.gather(*(enrich(doc) for doc in docs))


def summary_usd(docs):
    balances = {}
    for tx in docs:
        bucket = balances.setdefault(tx["currency"], {"amazon_balance": Decimal(0), "payouts_received": Decimal(0)})
        amount = money(tx["amount"])
        if tx["type"] == "income":
            bucket["amazon_balance"] += amount
        elif tx["type"] == "expense" and tx["category"] not in EXTERNAL_CATEGORIES:
            bucket["amazon_balance"] -= amount
        elif tx["type"] == "payout" and tx["category"] == "Bankada":
            bucket["amazon_balance"] -= amount
            bucket["payouts_received"] += amount
    missing = [tx for tx in docs if tx.get("fx_status") == "unavailable"]
    converted = [{**tx, "amount": tx["amount_usd"], **tx["usd_costs"]} for tx in docs if tx.get("fx_status") != "unavailable"]
    result = summarize(converted)
    # Local cash is never summed across currencies or adjusted by USD supplier costs.
    result.pop("amazon_balance")
    result.pop("payouts_received")
    if missing:
        for key in ("revenue", "expenses", "net_profit", "margin"):
            result[key] = None
        for key in ("by_marketplace", "by_category", "trend"):
            result[key] = []
    return {**result, "transaction_count": len(docs), "incomplete_count": len(missing),
            "fx_errors": sorted({tx["fx_error"] for tx in missing}),
            "native_balances": [{"currency": currency, **{k: float(v) for k, v in values.items()}} for currency, values in sorted(balances.items())]}