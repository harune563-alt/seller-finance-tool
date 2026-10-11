"""FBA Tracking: inventory lots, FIFO cost allocation and FBA profit / inventory reports.

FBA Tracking is NOT a ledger. It never creates income/expense transactions; Amazon Payments
rows stay the single revenue source. Only `fba_fifo` metadata is written onto existing rows.
"""
import asyncio
import logging
import uuid
from collections import defaultdict
from datetime import date as calendar_date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field, field_validator
from pymongo import UpdateMany

from amazon_orders_import import is_active_item
from usd_ledger import enrich_records

logger = logging.getLogger(__name__)

OPEN, DEPLETED, CLOSED = "OPEN", "DEPLETED", "CLOSED"
COSTED, PARTIAL, MISSING = "costed", "partial", "missing"
COST_SOURCE = "FBA FIFO"
_locks: dict = defaultdict(asyncio.Lock)


def D(value):
    return Decimal(str(value or 0))


def q2(value):
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def q4(value):
    return D(value).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)


def f(value):
    return None if value is None else float(value)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def lot_costs(original_quantity, product_unit_cost, inbound_total):
    """inbound/unit = inbound_total / original_qty; landed = product_unit + inbound/unit."""
    inbound_unit = q4(D(inbound_total) / D(original_quantity)) if original_quantity else Decimal(0)
    return {"inbound_shipping_unit_usd": float(inbound_unit),
            "landed_unit_cost_usd": float(q4(D(product_unit_cost) + inbound_unit))}


def _valid_date(value):
    return calendar_date.fromisoformat(value).isoformat() if value else None


class LotIn(BaseModel):
    store_id: str
    marketplace: str = Field(default="", max_length=10)
    sku: str = Field(min_length=1, max_length=200)
    asin: str = Field(default="", max_length=40)
    product_name: str = Field(default="", max_length=500)
    purchase_date: str
    fba_received_date: Optional[str] = None
    original_quantity: int = Field(gt=0, le=10_000_000)
    product_unit_cost_usd: float = Field(ge=0, le=1_000_000, allow_inf_nan=False)
    inbound_shipping_total_usd: float = Field(default=0, ge=0, le=1_000_000_000, allow_inf_nan=False)
    note: str = Field(default="", max_length=500)

    @field_validator("sku", "asin", "product_name", "marketplace", mode="before")
    @classmethod
    def strip(cls, v):
        return (v or "").strip() if isinstance(v, str) or v is None else v

    @field_validator("purchase_date")
    @classmethod
    def valid_purchase_date(cls, v):
        return calendar_date.fromisoformat(v).isoformat()

    @field_validator("fba_received_date")
    @classmethod
    def valid_dates(cls, v):
        return _valid_date(v)


class LotUpdateIn(BaseModel):
    marketplace: Optional[str] = Field(default=None, max_length=10)
    sku: Optional[str] = Field(default=None, min_length=1, max_length=200)
    asin: Optional[str] = Field(default=None, max_length=40)
    product_name: Optional[str] = Field(default=None, max_length=500)
    purchase_date: Optional[str] = None
    fba_received_date: Optional[str] = None
    product_unit_cost_usd: Optional[float] = Field(default=None, ge=0, le=1_000_000, allow_inf_nan=False)
    note: str = Field(default="", max_length=500)

    @field_validator("purchase_date", "fba_received_date")
    @classmethod
    def valid_dates(cls, v):
        return _valid_date(v)


AdjustType = Literal["increase_quantity", "decrease_quantity", "correct_remaining",
                     "update_inbound_shipping", "close_lot"]


class AdjustIn(BaseModel):
    adjustment_type: AdjustType
    value: Optional[float] = Field(default=None, ge=0, le=1_000_000_000, allow_inf_nan=False)
    note: str = Field(default="", max_length=500)


class ReallocateIn(BaseModel):
    store_id: str
    order_id: str = Field(min_length=1, max_length=100)
    note: str = Field(default="", max_length=500)


# ---------------------------------------------------------------------------
# Order source: existing FBA-enriched Income/Expense rows + All Orders item metadata
# ---------------------------------------------------------------------------
async def load_fba_orders(db, user_id, store_id):
    txs = await db.transactions.find(
        {"user_id": user_id, "store_id": store_id, "fulfillment_type": "FBA",
         "order_id": {"$nin": ["", None]}, "type": {"$in": ["income", "expense"]}},
        {"_id": 0}).to_list(None)
    txs = await enrich_records(db, txs)
    groups = {}
    for t in txs:
        groups.setdefault((t["marketplace"], t["order_id"].strip()), []).append(t)
    order_ids = sorted({oid for _, oid in groups})
    items = await db.amazon_order_items.find(
        {"user_id": user_id, "amazon_order_id": {"$in": order_ids}}, {"_id": 0}).to_list(None)
    items_by_order = defaultdict(list)
    for it in items:
        if it.get("resolved_fulfillment") == "FBA" and is_active_item(it):
            items_by_order[it["amazon_order_id"]].append(it)
    orders = []
    for (mp, oid), records in groups.items():
        its = sorted(items_by_order.get(oid, []), key=lambda i: i.get("order_item_id") or "")
        fx_ready = all(r.get("fx_status") == "ready" for r in records)
        income = sum(D(r.get("amount_usd")) for r in records if r["type"] == "income")
        expense = sum(D(r.get("amount_usd")) for r in records if r["type"] == "expense")
        extra = sum(D((r.get("usd_costs") or {}).get("extra_cost")) for r in records if r["type"] == "income")
        item_date = min(((i.get("purchase_date") or "")[:10] for i in its if i.get("purchase_date")), default="")
        tx_date = min((r.get("original_transaction_date") or r["date"]) for r in records)
        orders.append({
            "order_id": oid, "marketplace": mp, "store_id": store_id, "items": its, "records": records,
            "date": item_date or tx_date, "fx_ready": fx_ready,
            "amazon_net": q2(income - expense) if fx_ready else None, "extra_cost": q2(extra),
        })
    orders.sort(key=lambda o: (o["date"], o["order_id"]))
    return orders


async def _active_allocations(db, user_id, store_id, order_ids=None):
    q = {"user_id": user_id, "store_id": store_id, "status": "active"}
    if order_ids is not None:
        q["amazon_order_id"] = {"$in": list(order_ids)}
    return await db.fba_allocations.find(q, {"_id": 0}).sort("allocated_at", 1).to_list(None)


def summarize_order(order, allocations):
    required = sum(int(i.get("quantity") or 0) for i in order["items"])
    allocated = sum(a["quantity"] for a in allocations)
    product = q2(sum(D(a["allocated_product_cost_usd"]) for a in allocations))
    inbound = q2(sum(D(a["allocated_inbound_cost_usd"]) for a in allocations))
    total = q2(product + inbound)
    status = COSTED if required and allocated >= required else PARTIAL if allocated else MISSING
    net = margin = None
    if status == COSTED and order["amazon_net"] is not None:
        net = q2(order["amazon_net"] - total - order["extra_cost"])
        margin = q2(net / order["amazon_net"] * 100) if order["amazon_net"] != 0 else None
    return {"cost_status": status, "required_units": required, "allocated_units": allocated,
            "product_cost_usd": float(product), "inbound_cost_usd": float(inbound),
            "total_cost_usd": float(total), "extra_cost_usd": float(order["extra_cost"]),
            "amazon_net_usd": f(order["amazon_net"]), "net_profit_usd": f(net),
            "margin_percent": f(margin), "cost_source": COST_SOURCE}


async def allocate_store(db, user_id, store_id):
    """Idempotent FIFO pass: only still-uncosted FBA item units consume lots, oldest order first.
    Existing allocations are never touched, so historical COGS stays stable."""
    async with _locks[(user_id, store_id)]:
        orders = await load_fba_orders(db, user_id, store_id)
        existing = await _active_allocations(db, user_id, store_id)
        done = defaultdict(int)
        for a in existing:
            done[(a["amazon_order_id"], a.get("order_item_id") or "")] += a["quantity"]
        created = 0
        for order in orders:
            for it in order["items"]:
                sku = (it.get("sku") or "").strip()
                key = (order["order_id"], it.get("order_item_id") or "")
                need = int(it.get("quantity") or 0) - done[key]
                while sku and need > 0:
                    lot = await db.fba_lots.find_one(
                        {"user_id": user_id, "store_id": store_id, "sku": sku, "lot_status": OPEN,
                         "remaining_quantity": {"$gt": 0}}, {"_id": 0},
                        sort=[("purchase_date", 1), ("created_at", 1)])
                    if not lot:
                        break
                    take = min(need, lot["remaining_quantity"])
                    left = lot["remaining_quantity"] - take
                    res = await db.fba_lots.update_one(
                        {"id": lot["id"], "remaining_quantity": lot["remaining_quantity"], "lot_status": OPEN},
                        {"$inc": {"remaining_quantity": -take},
                         "$set": {"lot_status": DEPLETED if left == 0 else OPEN, "updated_at": now_iso()}})
                    if not res.modified_count:
                        continue
                    product = q2(D(lot["product_unit_cost_usd"]) * take)
                    total = q2(D(lot["landed_unit_cost_usd"]) * take)
                    await db.fba_allocations.insert_one({
                        "id": str(uuid.uuid4()), "user_id": user_id, "store_id": store_id,
                        "marketplace": order["marketplace"], "amazon_order_id": order["order_id"],
                        "order_item_id": it.get("order_item_id") or "", "sku": sku, "asin": it.get("asin") or "",
                        "order_date": order["date"], "quantity": take, "lot_id": lot["id"],
                        "lot_code": lot.get("lot_code", ""),
                        "product_unit_cost_usd": lot["product_unit_cost_usd"],
                        "inbound_unit_cost_usd": lot["inbound_shipping_unit_usd"],
                        "landed_unit_cost_usd": lot["landed_unit_cost_usd"],
                        "allocated_product_cost_usd": float(product),
                        "allocated_inbound_cost_usd": float(q2(total - product)),
                        "total_allocated_cost_usd": float(total),
                        "status": "active", "allocated_at": now_iso()})
                    done[key] += take
                    need -= take
                    created += 1
        allocations = await _active_allocations(db, user_id, store_id)
        by_order = defaultdict(list)
        for a in allocations:
            by_order[a["amazon_order_id"]].append(a)

        def carrier_id(o):
            incomes = sorted((r for r in o["records"] if r["type"] == "income"), key=lambda r: (r["date"], r["id"]))
            return incomes[0]["id"] if incomes else None

        ops = [UpdateMany({"user_id": user_id, "store_id": store_id, "marketplace": o["marketplace"],
                           "order_id": o["order_id"], "fulfillment_type": "FBA"},
                          {"$set": {"fba_fifo": {**summarize_order(o, by_order[o["order_id"]]),
                                                 "carrier_tx_id": carrier_id(o), "updated_at": now_iso()}}})
               for o in orders]
        if ops:
            await db.transactions.bulk_write(ops, ordered=False)
        return {"orders": orders, "allocations": by_order, "created_allocations": created}


async def allocate_user_stores(db, user_id):
    for store in await db.stores.find({"user_id": user_id}, {"_id": 0, "id": 1}).to_list(None):
        await allocate_store(db, user_id, store["id"])


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------
def order_rows(orders, by_order):
    rows = []
    for o in orders:
        allocs = by_order.get(o["order_id"], [])
        its = o["items"]
        rows.append({
            "order_id": o["order_id"], "marketplace": o["marketplace"], "date": o["date"],
            "asin": ", ".join(sorted({i.get("asin") or "" for i in its} - {""})),
            "sku": ", ".join(sorted({i.get("sku") or "" for i in its} - {""})),
            "product_name": " | ".join(dict.fromkeys(i.get("product_name") or "" for i in its if i.get("product_name"))),
            "quantity": sum(int(i.get("quantity") or 0) for i in its),
            "order_status": ", ".join(sorted({i.get("order_status") or "" for i in its} - {""})),
            "item_status": ", ".join(sorted({i.get("item_status") or "" for i in its} - {""})),
            "record_ids": [r["id"] for r in o["records"]],
            **summarize_order(o, allocs),
            "allocations": [{k: a[k] for k in ("lot_id", "lot_code", "order_item_id", "sku", "quantity",
                                               "landed_unit_cost_usd", "product_unit_cost_usd",
                                               "inbound_unit_cost_usd", "allocated_product_cost_usd",
                                               "allocated_inbound_cost_usd", "total_allocated_cost_usd",
                                               "allocated_at")} for a in allocs],
            "_order": o, "_allocs": allocs,
        })
    return rows


def _split(amount, weights):
    """Split an order amount over items by quantity share; remainder goes to the last item."""
    total_w = sum(weights)
    if not weights:
        return []
    parts, used = [], Decimal(0)
    for i, w in enumerate(weights):
        part = amount - used if i == len(weights) - 1 else q2(amount * D(w) / D(total_w or 1))
        parts.append(part)
        used += part
    return parts


def summary_totals(rows):
    revenue = sum(D(r["amazon_net_usd"]) for r in rows)
    product = sum(D(r["product_cost_usd"]) for r in rows)
    inbound = sum(D(r["inbound_cost_usd"]) for r in rows)
    extra = sum(D(r["extra_cost_usd"]) for r in rows)
    total = product + inbound
    net = revenue - total - extra
    return {"orders": len(rows), "units_sold": sum(r["quantity"] for r in rows),
            "amazon_net_revenue_usd": float(q2(revenue)), "product_cost_usd": float(q2(product)),
            "inbound_cost_usd": float(q2(inbound)), "total_fba_cost_usd": float(q2(total)),
            "extra_cost_usd": float(q2(extra)), "net_profit_usd": float(q2(net)),
            "margin_percent": float(q2(net / revenue * 100)) if revenue else None,
            "pending_cost_orders": sum(1 for r in rows if r["cost_status"] != COSTED),
            "fx_pending_orders": sum(1 for r in rows if r["amazon_net_usd"] is None)}


def asin_report(rows):
    buckets = {}
    for r in rows:
        o, allocs = r["_order"], r["_allocs"]
        its = o["items"] or [{"asin": "", "sku": "", "quantity": 0, "order_item_id": ""}]
        weights = [int(i.get("quantity") or 0) or 1 for i in its]
        rev_parts = _split(D(r["amazon_net_usd"]), weights)
        extra_parts = _split(D(r["extra_cost_usd"]), weights)
        for it, rev, extra in zip(its, rev_parts, extra_parts):
            asin = it.get("asin") or "—"
            b = buckets.setdefault(asin, {"asin": asin, "product_name": it.get("product_name") or "",
                                          "skus": set(), "orders": set(), "units_sold": 0,
                                          "revenue": Decimal(0), "product": Decimal(0),
                                          "inbound": Decimal(0), "extra": Decimal(0)})
            if it.get("sku"):
                b["skus"].add(it["sku"])
            b["orders"].add((r["marketplace"], r["order_id"]))
            b["units_sold"] += int(it.get("quantity") or 0)
            b["revenue"] += rev
            b["extra"] += extra
            for a in allocs:
                if (a.get("order_item_id") or "") == (it.get("order_item_id") or ""):
                    b["product"] += D(a["allocated_product_cost_usd"])
                    b["inbound"] += D(a["allocated_inbound_cost_usd"])
    out = []
    for b in buckets.values():
        total = b["product"] + b["inbound"]
        net = b["revenue"] - total - b["extra"]
        out.append({"asin": b["asin"], "product_name": b["product_name"], "skus": sorted(b["skus"]),
                    "orders": len(b["orders"]), "units_sold": b["units_sold"],
                    "amazon_net_revenue_usd": float(q2(b["revenue"])), "product_cost_usd": float(q2(b["product"])),
                    "inbound_cost_usd": float(q2(b["inbound"])), "total_fba_cost_usd": float(q2(total)),
                    "extra_cost_usd": float(q2(b["extra"])), "net_profit_usd": float(q2(net)),
                    "margin_percent": float(q2(net / b["revenue"] * 100)) if b["revenue"] else None})
    return sorted(out, key=lambda x: -x["amazon_net_revenue_usd"])


async def inventory_report(db, user_id, store_id):
    lots = await db.fba_lots.find({"user_id": user_id, "store_id": store_id, "lot_status": OPEN,
                                   "remaining_quantity": {"$gt": 0}}, {"_id": 0}).to_list(None)
    buckets = {}
    for lot in lots:
        rem = lot["remaining_quantity"]
        b = buckets.setdefault((lot.get("asin") or "", lot["sku"]), {
            "asin": lot.get("asin") or "", "sku": lot["sku"], "product_name": lot.get("product_name") or "",
            "remaining_units": 0, "product": Decimal(0), "inbound": Decimal(0), "value": Decimal(0), "open_lots": 0})
        b["remaining_units"] += rem
        b["product"] += q2(D(lot["product_unit_cost_usd"]) * rem)
        b["inbound"] += q2(D(lot["inbound_shipping_unit_usd"]) * rem)
        b["value"] += q2(D(lot["landed_unit_cost_usd"]) * rem)
        b["open_lots"] += 1
    rows = [{"asin": b["asin"], "sku": b["sku"], "product_name": b["product_name"],
             "remaining_units": b["remaining_units"], "remaining_product_cost_usd": float(b["product"]),
             "remaining_inbound_cost_usd": float(b["inbound"]), "remaining_value_usd": float(b["value"]),
             "open_lots": b["open_lots"]} for b in buckets.values()]
    rows.sort(key=lambda r: -r["remaining_value_usd"])
    return {"rows": rows, "totals": {
        "remaining_units": sum(r["remaining_units"] for r in rows),
        "remaining_product_cost_usd": float(sum(D(r["remaining_product_cost_usd"]) for r in rows)),
        "remaining_inbound_cost_usd": float(sum(D(r["remaining_inbound_cost_usd"]) for r in rows)),
        "inventory_value_usd": float(sum(D(r["remaining_value_usd"]) for r in rows)),
        "open_lots": sum(r["open_lots"] for r in rows)}}


async def inventory_cash_flow_metrics(db, user_id, store_id, start=None, end=None):
    """Service for a future Cash Flow module. Inventory is an asset, never an expense row.
    current_inventory_value: open lots remaining x landed cost (as of now).
    inventory_purchases: lot cost basis (qty x product unit + inbound total) by purchase_date.
    realized_inventory_cost: FIFO cost consumed by FBA sales by order date."""
    inv = await inventory_report(db, user_id, store_id)
    rng = {}
    if start:
        rng["$gte"] = start
    if end:
        rng["$lte"] = end
    lot_q = {"user_id": user_id, "store_id": store_id, **({"purchase_date": rng} if rng else {})}
    purchases = sum(q2(D(l["original_quantity"]) * D(l["product_unit_cost_usd"]) + D(l["inbound_shipping_total_usd"]))
                    for l in await db.fba_lots.find(lot_q, {"_id": 0}).to_list(None))
    alloc_q = {"user_id": user_id, "store_id": store_id, "status": "active", **({"order_date": rng} if rng else {})}
    realized = sum(D(a["total_allocated_cost_usd"]) for a in await db.fba_allocations.find(alloc_q, {"_id": 0}).to_list(None))
    return {"current_inventory_value": inv["totals"]["inventory_value_usd"],
            "inventory_purchases": float(q2(purchases)), "realized_inventory_cost": float(q2(realized)),
            "currency": "USD", "start_date": start, "end_date": end}


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def fba_router(db, get_current_user):
    router = APIRouter(prefix="/fba", tags=["fba"])

    async def own_store(store_id, user):
        store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0})
        if not store:
            raise HTTPException(404, "Mağaza bulunamadı")
        return store

    async def own_lot(lot_id, user):
        lot = await db.fba_lots.find_one({"id": lot_id, "user_id": user["id"]}, {"_id": 0})
        if not lot:
            raise HTTPException(404, "Lot bulunamadı")
        return lot

    async def audit(user, lot, adjustment_type, previous, new, note=""):
        await db.fba_lot_adjustments.insert_one({
            "id": str(uuid.uuid4()), "user_id": user["id"], "user_email": user.get("email", ""),
            "store_id": lot["store_id"], "lot_id": lot["id"], "lot_code": lot.get("lot_code", ""),
            "adjustment_type": adjustment_type, "previous_value": previous, "new_value": new,
            "note": note, "timestamp": now_iso()})

    async def lot_out(lots):
        ids = [l["id"] for l in lots]
        consumed = defaultdict(int)
        async for a in db.fba_allocations.find({"lot_id": {"$in": ids}, "status": "active"}, {"_id": 0}):
            consumed[a["lot_id"]] += a["quantity"]
        return [{**l, "consumed_quantity": consumed[l["id"]],
                 "remaining_value_usd": float(q2(D(l["landed_unit_cost_usd"]) * l["remaining_quantity"]))
                 if l["lot_status"] == OPEN else 0.0}
                for l in lots]

    @router.get("/lots")
    async def list_lots(store_id: str, user=Depends(get_current_user)):
        await own_store(store_id, user)
        lots = await db.fba_lots.find({"user_id": user["id"], "store_id": store_id}, {"_id": 0, "user_id": 0}) \
            .sort([("sku", 1), ("purchase_date", 1), ("created_at", 1)]).to_list(None)
        return await lot_out(lots)

    @router.post("/lots")
    async def create_lot(data: LotIn, user=Depends(get_current_user)):
        store = await own_store(data.store_id, user)
        if data.marketplace and data.marketplace not in (store.get("marketplaces") or []):
            raise HTTPException(422, "Pazar yeri mağazada aktif değil")
        seq = await db.fba_lots.count_documents({"user_id": user["id"], "store_id": data.store_id}) + 1
        ts = now_iso()
        lot = {"id": str(uuid.uuid4()), "lot_code": f"LOT-{seq:04d}", "user_id": user["id"],
               **data.model_dump(exclude={"note"}),
               "product_unit_cost_usd": float(q2(data.product_unit_cost_usd)),
               "inbound_shipping_total_usd": float(q2(data.inbound_shipping_total_usd)),
               **lot_costs(data.original_quantity, q2(data.product_unit_cost_usd), q2(data.inbound_shipping_total_usd)),
               "remaining_quantity": data.original_quantity, "lot_status": OPEN,
               "created_at": ts, "updated_at": ts}
        await db.fba_lots.insert_one(dict(lot))
        await audit(user, lot, "create_lot", None, {"original_quantity": lot["original_quantity"],
                    "landed_unit_cost_usd": lot["landed_unit_cost_usd"]}, data.note)
        await allocate_store(db, user["id"], data.store_id)
        stored = await db.fba_lots.find_one({"id": lot["id"]}, {"_id": 0, "user_id": 0})
        return (await lot_out([stored]))[0]

    @router.patch("/lots/{lot_id}")
    async def update_lot(lot_id: str, data: LotUpdateIn, user=Depends(get_current_user)):
        lot = await own_lot(lot_id, user)
        changes = {k: v for k, v in data.model_dump(exclude={"note"}, exclude_unset=True).items() if v is not None}
        consumed = await db.fba_allocations.count_documents({"lot_id": lot_id, "status": "active"})
        locked = {"sku", "product_unit_cost_usd", "purchase_date"} & set(changes)
        if consumed and locked:
            raise HTTPException(409, "Satışa tahsis edilmiş lotta SKU, ürün maliyeti ve alış tarihi değiştirilemez")
        if "product_unit_cost_usd" in changes:
            changes["product_unit_cost_usd"] = float(q2(changes["product_unit_cost_usd"]))
            changes.update(lot_costs(lot["original_quantity"], changes["product_unit_cost_usd"],
                                     lot["inbound_shipping_total_usd"]))
        changes = {k: v for k, v in changes.items() if lot.get(k) != v}
        if not changes:
            return (await lot_out([{k: v for k, v in lot.items() if k != "user_id"}]))[0]
        await db.fba_lots.update_one({"id": lot_id}, {"$set": {**changes, "updated_at": now_iso()}})
        await audit(user, lot, "edit_lot", {k: lot.get(k) for k in changes}, changes, data.note)
        await allocate_store(db, user["id"], lot["store_id"])
        stored = await db.fba_lots.find_one({"id": lot_id}, {"_id": 0, "user_id": 0})
        return (await lot_out([stored]))[0]

    @router.post("/lots/{lot_id}/adjust")
    async def adjust_lot(lot_id: str, data: AdjustIn, user=Depends(get_current_user)):
        async with _locks[(user["id"], (await own_lot(lot_id, user))["store_id"])]:
            lot = await own_lot(lot_id, user)
            t, v = data.adjustment_type, data.value
            if lot["lot_status"] == CLOSED:
                raise HTTPException(409, "Kapalı lot düzenlenemez")
            if t != "close_lot" and v is None:
                raise HTTPException(422, "Değer gerekli")
            rem, orig = lot["remaining_quantity"], lot["original_quantity"]
            sets, prev, new = {}, {}, {}
            if t in ("increase_quantity", "decrease_quantity", "correct_remaining") and int(v) != v:
                raise HTTPException(422, "Adet tam sayı olmalı")
            if t == "increase_quantity":
                if v <= 0:
                    raise HTTPException(422, "Artış 0'dan büyük olmalı")
                sets = {"original_quantity": orig + int(v), "remaining_quantity": rem + int(v),
                        **lot_costs(orig + int(v), lot["product_unit_cost_usd"], lot["inbound_shipping_total_usd"])}
            elif t == "decrease_quantity":
                if v <= 0 or v > rem:
                    raise HTTPException(422, "Azaltma kalan adetten büyük olamaz")
                sets = {"remaining_quantity": rem - int(v)}
            elif t == "correct_remaining":
                sets = {"remaining_quantity": int(v)}
            elif t == "update_inbound_shipping":
                sets = {"inbound_shipping_total_usd": float(q2(v)),
                        **lot_costs(orig, lot["product_unit_cost_usd"], q2(v))}
            else:
                sets = {"lot_status": CLOSED}
            if "remaining_quantity" in sets:
                sets["lot_status"] = OPEN if sets["remaining_quantity"] > 0 else DEPLETED
            prev = {k: lot.get(k) for k in sets}
            new = sets
            await db.fba_lots.update_one({"id": lot_id, "updated_at": lot["updated_at"]},
                                         {"$set": {**sets, "updated_at": now_iso()}})
            await audit(user, lot, t, prev, new, data.note)
        await allocate_store(db, user["id"], lot["store_id"])
        stored = await db.fba_lots.find_one({"id": lot_id}, {"_id": 0, "user_id": 0})
        return (await lot_out([stored]))[0]

    @router.get("/lots/{lot_id}/history")
    async def lot_history(lot_id: str, user=Depends(get_current_user)):
        await own_lot(lot_id, user)
        adjustments = await db.fba_lot_adjustments.find(
            {"lot_id": lot_id, "user_id": user["id"]}, {"_id": 0, "user_id": 0}).sort("timestamp", -1).to_list(500)
        allocations = await db.fba_allocations.find(
            {"lot_id": lot_id, "user_id": user["id"]}, {"_id": 0, "user_id": 0}).sort("allocated_at", -1).to_list(2000)
        return {"adjustments": adjustments, "allocations": allocations}

    @router.post("/allocate")
    async def run_allocation(store_id: str, user=Depends(get_current_user)):
        await own_store(store_id, user)
        result = await allocate_store(db, user["id"], store_id)
        return {"created_allocations": result["created_allocations"], "fba_orders": len(result["orders"])}

    @router.post("/orders/reallocate")
    async def reallocate_order(data: ReallocateIn, user=Depends(get_current_user)):
        """Controlled recalculation: reverse this order's FIFO allocations (stock returns to
        the same lots, audited) and run a fresh FIFO pass."""
        await own_store(data.store_id, user)
        async with _locks[(user["id"], data.store_id)]:
            allocs = await db.fba_allocations.find(
                {"user_id": user["id"], "store_id": data.store_id, "amazon_order_id": data.order_id,
                 "status": "active"}, {"_id": 0}).to_list(None)
            for a in allocs:
                lot = await db.fba_lots.find_one({"id": a["lot_id"]}, {"_id": 0})
                new_rem = lot["remaining_quantity"] + a["quantity"]
                status = CLOSED if lot["lot_status"] == CLOSED else OPEN
                await db.fba_lots.update_one({"id": lot["id"]}, {"$inc": {"remaining_quantity": a["quantity"]},
                                                                 "$set": {"lot_status": status, "updated_at": now_iso()}})
                await db.fba_allocations.update_one({"id": a["id"]}, {"$set": {
                    "status": "reversed", "reversed_at": now_iso(), "reversed_by": user.get("email", ""),
                    "reverse_note": data.note}})
                await audit(user, lot, "reallocation_return", {"remaining_quantity": lot["remaining_quantity"]},
                            {"remaining_quantity": new_rem, "amazon_order_id": data.order_id}, data.note)
        await allocate_store(db, user["id"], data.store_id)
        return {"reversed_allocations": len(allocs)}

    @router.get("/orders")
    async def fba_orders(store_id: str, start_date: Optional[str] = None, end_date: Optional[str] = None,
                         marketplace: Optional[str] = None, user=Depends(get_current_user)):
        await own_store(store_id, user)
        result = await allocate_store(db, user["id"], store_id)
        orders = [o for o in result["orders"]
                  if (not start_date or o["date"] >= start_date) and (not end_date or o["date"] <= end_date)
                  and (not marketplace or marketplace == "ALL" or o["marketplace"] == marketplace)]
        rows = order_rows(orders, result["allocations"])
        inv = await inventory_report(db, user["id"], store_id)
        summary = {**summary_totals(rows), "inventory_units": inv["totals"]["remaining_units"],
                   "inventory_value_usd": inv["totals"]["inventory_value_usd"]}
        asin = asin_report(rows)
        for r in rows:
            r.pop("_order"), r.pop("_allocs")
        rows.sort(key=lambda r: (r["date"], r["order_id"]), reverse=True)
        return {"orders": rows, "summary": summary, "asin_report": asin}

    @router.get("/inventory")
    async def fba_inventory(store_id: str, user=Depends(get_current_user)):
        await own_store(store_id, user)
        return await inventory_report(db, user["id"], store_id)

    @router.get("/cash-flow-metrics")
    async def cash_flow_metrics(store_id: str, start_date: Optional[str] = Query(None),
                                end_date: Optional[str] = Query(None), user=Depends(get_current_user)):
        await own_store(store_id, user)
        return await inventory_cash_flow_metrics(db, user["id"], store_id, start_date, end_date)

    return router


async def initialize_fba_indexes(db):
    await db.fba_lots.create_index("id", unique=True)
    await db.fba_lots.create_index([("user_id", 1), ("store_id", 1), ("sku", 1), ("lot_status", 1),
                                    ("purchase_date", 1), ("created_at", 1)])
    await db.fba_allocations.create_index("id", unique=True)
    await db.fba_allocations.create_index([("user_id", 1), ("store_id", 1), ("amazon_order_id", 1), ("status", 1)])
    await db.fba_allocations.create_index([("lot_id", 1), ("status", 1)])
    await db.fba_lot_adjustments.create_index([("lot_id", 1), ("timestamp", -1)])
