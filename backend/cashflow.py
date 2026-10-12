"""Standalone Cash Flow (Nakit Akışı) module.

Cash flow tracks ACTUAL cash movement — a separate concept from Profit/Loss.
- P&L keeps realized profitability (e.g. FIFO COGS when a unit sells).
- Cash flow records when money actually moves (e.g. full lot cost on purchase day).

This module only READS existing canonical records (Amazon payment transactions,
FBA lots, SellerFlash cost records, FBA FIFO allocations) and mirrors them into a
normalized `cash_flow_entries` collection using idempotent upserts keyed by
(source_type, source_id). It never writes to any existing collection, so Amazon
Payments / SellerFlash / FBA FIFO / Dashboard logic stay untouched.

Manual cash entries and opening balances live exclusively in this module and
never alter Profit/Loss.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from pymongo.errors import DuplicateKeyError

from finance import money
from fx_service import FxError, get_rate

IN, OUT = "IN", "OUT"
AMAZON_PAYMENT = "AMAZON_PAYMENT"  # legacy; order rows are no longer cash-in
AMAZON_DISBURSEMENT = "AMAZON_DISBURSEMENT"
FBA_INVENTORY_PURCHASE = "FBA_INVENTORY_PURCHASE"
FBA_INBOUND_SHIPPING = "FBA_INBOUND_SHIPPING"
FBM_PRODUCT_COST = "FBM_PRODUCT_COST"
FBM_SHIPPING_COST = "FBM_SHIPPING_COST"
EXTRA_COST = "EXTRA_COST"
MANUAL = "MANUAL"
# Sermaye & Kasa (financing/equity) — cash flow only, never P&L.
CAPITAL_INJECTION = "CAPITAL_INJECTION"
OWNER_WITHDRAWAL = "OWNER_WITHDRAWAL"
CASH_DEPOSIT = "CASH_DEPOSIT"
CASH_WITHDRAWAL = "CASH_WITHDRAWAL"
FINANCING_IN = (CAPITAL_INJECTION, CASH_DEPOSIT)
FINANCING_OUT = (OWNER_WITHDRAWAL, CASH_WITHDRAWAL)
COMPANY_SCOPE = ""  # store_id of company-level (storeless) Kasa movements

SOURCE_LABELS = {
    AMAZON_PAYMENT: "Amazon Tahsilatı",
    AMAZON_DISBURSEMENT: "Amazon Ödemesi (Bankada)",
    FBA_INVENTORY_PURCHASE: "FBA Envanter Alımı",
    FBA_INBOUND_SHIPPING: "FBA Inbound Nakliye",
    FBM_PRODUCT_COST: "FBM Ürün Maliyeti",
    FBM_SHIPPING_COST: "FBM Kargo Maliyeti",
    EXTRA_COST: "Ekstra Maliyet",
    MANUAL: "Manuel",
    CAPITAL_INJECTION: "Sermaye Ekleme",
    OWNER_WITHDRAWAL: "Sermaye Çekme",
    CASH_DEPOSIT: "Kasa Girişi",
    CASH_WITHDRAWAL: "Kasa Çıkışı",
}
SOURCE_MODULES = {
    **{key: "Sermaye & Kasa" for key in (*FINANCING_IN, *FINANCING_OUT)},
    AMAZON_DISBURSEMENT: "Amazon Ödemeleri & Bakiye",
    FBA_INVENTORY_PURCHASE: "FBA Envanter", FBA_INBOUND_SHIPPING: "FBA Envanter",
    FBM_PRODUCT_COST: "SellerFlash", FBM_SHIPPING_COST: "SellerFlash",
    EXTRA_COST: "Ekstra Maliyetler", MANUAL: "Nakit Akışı",
}


async def _native_to_usd(db, amount, currency, date, quote=None):
    if (currency or "USD") == "USD":
        return money(amount)
    rate = (quote or {}).get("rate") or (await get_rate(db, currency, date))["rate"]
    return money(D(amount) * D(rate))


def D(value):
    return Decimal(str(value or 0))


def q2(value):
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def in_range(day, start, end):
    return (not start or day >= start) and (not end or day <= end)


async def initialize_cashflow_indexes(db):
    await db.cash_flow_entries.create_index([("user_id", 1), ("idem_key", 1)], unique=True)
    await db.cash_flow_entries.create_index([("user_id", 1), ("store_id", 1), ("date", 1)])
    await db.cash_flow_opening_balances.create_index([("user_id", 1), ("store_id", 1)], unique=True)
    await db.cash_flow_audit.create_index([("user_id", 1), ("timestamp", -1)])


# ---------------------------------------------------------------------------
# Idempotent sync: canonical records -> normalized cash-flow entries
# ---------------------------------------------------------------------------
async def _usd_amount(db, doc, amount_field, usd_bucket=None):
    """USD value for a transaction amount/cost, using the stored snapshot first."""
    if usd_bucket is not None:
        costs = doc.get("usd_costs") or {}
        if costs.get(usd_bucket) is not None:
            return money(costs[usd_bucket])
    if doc.get("amount_usd") is not None and usd_bucket is None:
        return money(doc["amount_usd"])
    raw = D(doc.get(amount_field, 0))
    cost_currency = doc.get("cost_currency") or doc.get("currency") or "USD"
    if cost_currency == "USD":
        return money(raw)
    quote = await get_rate(db, cost_currency, doc["date"])
    return money(raw * D(quote["rate"]))


async def sync_cash_flow(db, user_id):
    """Rebuild desired system entries and diff against stored ones.

    Idempotent: stable idem_key per (source_type, source_id); re-runs never
    duplicate, late-arriving SellerFlash components complete the record, and
    entries whose source disappeared are removed. Manual entries are untouched.
    """
    now = now_iso()
    desired = {}

    def put(source_type, source_id, *, store_id, marketplace, date, direction,
            amount, order_id="", lot_id="", description="", category=None, **extra):
        amount = q2(amount)
        key = f"{source_type}:{source_id}"
        if amount <= 0:
            return
        # Sources stored natively in USD (FBA lots, SellerFlash, extra costs, manual) report USD as original.
        extra.setdefault("original_amount", float(amount))
        extra.setdefault("original_currency", "USD")
        extra.setdefault("payment_reference", "")
        desired[key] = {
            "user_id": user_id, "idem_key": key, "store_id": store_id,
            "marketplace": marketplace or "", "date": date, "direction": direction,
            "category": category or SOURCE_LABELS[source_type],
            "amount_usd": float(amount), "source_type": source_type,
            "source_id": source_id, "order_id": order_id or "", "lot_id": lot_id or "",
            "description": description or "", "is_manual": False, **extra,
        }

    # 1) FBA lots -> inventory purchase + inbound shipping cash out on purchase date.
    lots = await db.fba_lots.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    for lot in lots:
        label = f"FBA lot {lot.get('lot_code') or lot['id'][:8]} · {lot.get('sku', '')}"
        put(FBA_INVENTORY_PURCHASE, lot["id"], store_id=lot["store_id"],
            marketplace=lot.get("marketplace", ""), date=lot["purchase_date"], direction=OUT,
            amount=D(lot["original_quantity"]) * D(lot["product_unit_cost_usd"]),
            lot_id=lot["id"], description=f"Envanter alımı · {label}")
        put(FBA_INBOUND_SHIPPING, lot["id"], store_id=lot["store_id"],
            marketplace=lot.get("marketplace", ""), date=lot["purchase_date"], direction=OUT,
            amount=D(lot.get("inbound_shipping_total_usd", 0)),
            lot_id=lot["id"], description=f"Inbound nakliye · {label}")

    # 2) FBM product/shipping cost -> cash out (never for FBA orders;
    #    FBA inventory cash already left at lot purchase; FIFO COGS is P&L only).
    #    Primary source: the order's ledger costs (SellerFlash applies its USD costs
    #    onto the matched income transaction — same values P&L uses). Raw SellerFlash
    #    records only fill a component the ledger does not carry (e.g. unmatched orders).
    #    Each component is independent and keyed by order id (or transaction id).
    fba_order_ids = {oid for oid in await db.transactions.distinct(
        "order_id", {"user_id": user_id, "fulfillment_type": "FBA"}) if oid}
    fbm = {}

    def fbm_slot(key, store_id, marketplace, date, order_id):
        return fbm.setdefault(key, {"store_id": store_id, "marketplace": marketplace or "", "date": date,
                                    "order_id": order_id, "ledger": {}, "sf": {}})

    sf_records = await db.sellerflash_costs.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    for rec in sf_records:
        oid = rec.get("seller_order_id") or ""
        if not oid or oid in fba_order_ids:
            continue
        date = rec.get("order_date") or (rec.get("first_imported_at") or rec.get("last_seen_at") or now)[:10]
        slot = fbm_slot(oid, rec["store_id"], rec.get("marketplace", ""), date, oid)
        for comp, fields in (("product", ("product_cost_usd", "product_cost")),
                             ("shipping", ("shipping_cost_usd", "initial_shipment_cost"))):
            value = next((rec[f] for f in fields if rec.get(f) is not None), None)
            if value is not None:  # blank = no information; stored values are already USD
                slot["sf"][comp] = D(value)
    async for tx in db.transactions.find({
            "user_id": user_id, "type": "income", "fulfillment_type": {"$ne": "FBA"},
            "$or": [{"product_cost": {"$gt": 0}}, {"shipping_cost": {"$gt": 0}}]}, {"_id": 0}):
        oid = tx.get("order_id") or ""
        if oid and oid in fba_order_ids:
            continue
        slot = fbm_slot(oid or tx["id"], tx["store_id"], tx.get("marketplace", ""), tx["date"], oid)
        slot["store_id"], slot["marketplace"], slot["date"] = tx["store_id"], tx.get("marketplace", "") or slot["marketplace"], tx["date"]
        for comp, field in (("product", "product_cost"), ("shipping", "shipping_cost")):
            if D(tx.get(field) or 0) > 0:
                try:
                    value = await _usd_amount(db, tx, field, usd_bucket=field)
                except FxError:
                    continue
                slot["ledger"][comp] = slot["ledger"].get(comp, D(0)) + value
    for key, slot in fbm.items():
        ref = slot["order_id"] or f"İşlem {key[:8]}"
        for comp, source_type, label in (("product", FBM_PRODUCT_COST, "ürün maliyeti"),
                                         ("shipping", FBM_SHIPPING_COST, "kargo maliyeti")):
            value = slot["ledger"].get(comp)
            if value is None:
                value = slot["sf"].get(comp)
            if value is None:
                continue
            put(source_type, key, store_id=slot["store_id"], marketplace=slot["marketplace"],
                date=slot["date"], direction=OUT, amount=value, order_id=slot["order_id"],
                description=f"FBM {label} · {ref}")

    # 3) Amazon disbursement (payout) that reached the bank -> cash in.
    #    Amazon order/payment rows are operational activity only (P&L / Amazon
    #    balance); counting them here too would double count the same money.
    async for tx in db.transactions.find(
            {"user_id": user_id, "type": "payout", "category": "Bankada"}, {"_id": 0}):
        try:
            # Payouts carry amount_usd=0 by design (not P&L); convert the real payout amount.
            currency = tx.get("currency") or "USD"
            rate = D(1) if currency == "USD" else D((await get_rate(db, currency, tx["date"]))["rate"])
            amount = money(D(tx["amount"]) * rate)
        except FxError:
            continue  # FX not available yet; entry appears on a later sync.
        original = money(tx["amount"])
        reference = (tx.get("payment_reference") or "").strip()
        desc = f"Amazon ödemesi · {original} {tx.get('currency', '')}"
        if reference:
            desc += f" · Ref {reference}"
        put(AMAZON_DISBURSEMENT, tx["id"], store_id=tx["store_id"], marketplace=tx.get("marketplace", ""),
            date=tx["date"], direction=IN, amount=amount, description=desc,
            original_amount=float(original), original_currency=tx.get("currency", ""),
            payment_reference=reference)

    # 4) Existing extra costs -> cash out.
    async for tx in db.transactions.find(
            {"user_id": user_id, "extra_cost": {"$gt": 0}}, {"_id": 0}):
        try:
            amount = await _usd_amount(db, tx, "extra_cost", usd_bucket="extra_cost")
        except FxError:
            continue
        put(EXTRA_COST, tx["id"], store_id=tx["store_id"], marketplace=tx.get("marketplace", ""),
            date=tx["date"], direction=OUT, amount=amount, order_id=tx.get("order_id") or "",
            description=tx.get("description") or "Ekstra maliyet")

    # 5) Sermaye & Kasa -> financing cash movements (read-only; never touches P&L).
    #    Stable source id = the capital entry id / cash movement id.
    people = {p["id"]: p.get("name", "") for p in await db.company_people.find(
        {"user_id": user_id}, {"_id": 0, "id": 1, "name": 1}).to_list(None)}
    async for account in db.company_capital.find({"user_id": user_id}, {"_id": 0}):
        currency = account.get("currency") or "USD"
        for entry in account.get("entries", []):
            contribution = entry["direction"] == "contribution"
            original = D(entry["amount_cents"]) / 100
            try:
                amount = await _native_to_usd(db, original, currency, entry["date"],
                                              entry.get("fx") if contribution else None)
            except FxError:
                continue
            source_type = CAPITAL_INJECTION if contribution else OWNER_WITHDRAWAL
            person = people.get(account.get("person_id"), "")
            desc = f"{SOURCE_LABELS[source_type]} · {q2(original)} {currency}"
            if person:
                desc += f" · {person}"
            if entry.get("note"):
                desc += f" · {entry['note']}"
            put(source_type, entry["id"], store_id=account["store_id"], marketplace="",
                date=entry["date"], direction=IN if contribution else OUT, amount=amount,
                description=desc, original_amount=float(q2(original)), original_currency=currency,
                payment_reference="")
    async for movement in db.company_cash.find({"user_id": user_id}, {"_id": 0}):
        currency = movement.get("currency") or "USD"
        original = D(movement["amount_cents"]) / 100
        try:
            amount = await _native_to_usd(db, original, currency, movement["date"])
        except FxError:
            continue
        deposit = movement["direction"] == "in"
        source_type = CASH_DEPOSIT if deposit else CASH_WITHDRAWAL
        desc = f"{SOURCE_LABELS[source_type]} · {q2(original)} {currency}"
        if movement.get("note"):
            desc += f" · {movement['note']}"
        put(source_type, movement["id"], store_id=COMPANY_SCOPE, marketplace="",
            date=movement["date"], direction=IN if deposit else OUT, amount=amount,
            description=desc, original_amount=float(q2(original)), original_currency=currency,
            payment_reference="")

    # 6) Other Kasa-affecting Sermaye & Kasa records, mirroring the Kasa ledger rules
    #    (company/treasury.py): completed current-account movements with a cash effect,
    #    cash-effect debt principals, and debt repayments/collections.
    async def kasa_move(record_id, *, deposit, cents_amount, currency, date, store_id, person_id, label, note):
        currency = currency or "USD"
        original = D(cents_amount) / 100
        try:
            amount = await _native_to_usd(db, original, currency, date)
        except FxError:
            return
        source_type = CASH_DEPOSIT if deposit else CASH_WITHDRAWAL
        desc = f"{label} · {q2(original)} {currency}"
        if people.get(person_id):
            desc += f" · {people[person_id]}"
        if note:
            desc += f" · {note}"
        put(source_type, record_id, store_id=store_id or COMPANY_SCOPE, marketplace="", date=date,
            direction=IN if deposit else OUT, amount=amount, description=desc,
            category=f"{SOURCE_LABELS[source_type]} · {label}",
            original_amount=float(q2(original)), original_currency=currency, payment_reference="")

    async for entry in db.company_current_entries.find(
            {"user_id": user_id, "cash_status": "completed", "cash_effect": {"$in": ["in", "out"]}}, {"_id": 0}):
        deposit = entry["cash_effect"] == "in"
        await kasa_move(entry["id"], deposit=deposit, cents_amount=entry["amount_cents"],
                        currency=entry.get("currency"), date=entry["date"], store_id=entry.get("store_id"),
                        person_id=entry.get("person_id"), label="Cari · " + ("Kasaya giriş" if deposit else "Kasadan çıkış"),
                        note=entry.get("note"))
    async for debt in db.company_debts.find({"user_id": user_id}, {"_id": 0}):
        payable = debt["direction"] == "payable"  # borrowed money: principal in, repayments out
        common = dict(currency=debt.get("currency"), store_id=debt.get("store_id"), person_id=debt.get("person_id"))
        if debt.get("cash_effect"):
            await kasa_move(debt["id"], deposit=payable, cents_amount=debt["principal_cents"], date=debt["date"],
                            label="Borç alındı" if payable else "Borç verildi", note=debt.get("note"), **common)
        for payment in debt.get("payments", []):
            await kasa_move(payment["id"], deposit=not payable, cents_amount=payment["amount_cents"], date=payment["date"],
                            label="Borç ödemesi" if payable else "Alacak tahsilatı", note=payment.get("note"), **common)

    existing = {e["idem_key"]: e for e in await db.cash_flow_entries.find(
        {"user_id": user_id}, {"_id": 0}).to_list(None)}

    comparable = ("store_id", "marketplace", "date", "direction", "category",
                  "amount_usd", "order_id", "lot_id", "description",
                  "original_amount", "original_currency", "payment_reference")
    for key, doc in desired.items():
        cur = existing.get(key)
        if cur is None:
            try:
                await db.cash_flow_entries.update_one(
                    {"user_id": user_id, "idem_key": key},
                    {"$setOnInsert": {"id": str(uuid.uuid4()), **doc, "created_at": now, "updated_at": now}},
                    upsert=True)
            except DuplicateKeyError:
                pass  # a concurrent sync already inserted this exact source entry
        elif any(cur.get(field) != doc.get(field) for field in comparable):
            await db.cash_flow_entries.update_one(
                {"user_id": user_id, "idem_key": key},
                {"$set": {**doc, "updated_at": now}})

    stale = [e["idem_key"] for e in existing.values()
             if not e.get("is_manual") and e["idem_key"] not in desired]
    if stale:
        await db.cash_flow_entries.delete_many(
            {"user_id": user_id, "is_manual": {"$ne": True}, "idem_key": {"$in": stale}})


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class ManualEntryIn(BaseModel):
    store_id: str
    marketplace: Optional[str] = ""
    date: str
    direction: Literal["IN", "OUT"]
    category: str = Field(min_length=1, max_length=120)
    amount_usd: float = Field(gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    description: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        from datetime import date as calendar_date
        return calendar_date.fromisoformat(value).isoformat()

    @field_validator("marketplace", "category", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else (value or "")

    @field_validator("amount_usd")
    @classmethod
    def round_amount(cls, value):
        return float(money(value))


class ManualEntryUpdateIn(BaseModel):
    marketplace: Optional[str] = None
    date: Optional[str] = None
    direction: Optional[Literal["IN", "OUT"]] = None
    category: Optional[str] = Field(default=None, min_length=1, max_length=120)
    amount_usd: Optional[float] = Field(default=None, gt=0, le=1_000_000_000_000, allow_inf_nan=False)
    description: Optional[str] = Field(default=None, max_length=500)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        if value is None:
            return None
        from datetime import date as calendar_date
        return calendar_date.fromisoformat(value).isoformat()

    @field_validator("marketplace", "category", "description", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else value

    @field_validator("amount_usd")
    @classmethod
    def round_amount(cls, value):
        return None if value is None else float(money(value))


class OpeningBalanceIn(BaseModel):
    store_id: str
    amount_usd: float = Field(ge=0, le=1_000_000_000_000, allow_inf_nan=False)
    note: str = Field(default="", max_length=300)

    @field_validator("amount_usd")
    @classmethod
    def round_amount(cls, value):
        return float(money(value))

    @field_validator("note", mode="before")
    @classmethod
    def strip_text(cls, value):
        return value.strip() if isinstance(value, str) else (value or "")


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def cashflow_router(db, get_current_user, marketplaces):
    router = APIRouter(prefix="/cashflow", tags=["cashflow"])

    async def own_store(store_id, user):
        store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0})
        if not store:
            raise HTTPException(404, "Mağaza bulunamadı")
        return store

    async def scope_stores(user, store_id):
        if store_id and store_id != "ALL":
            store = await own_store(store_id, user)
            return [store["id"]], {store["id"]: store["name"]}
        stores = await db.stores.find({"user_id": user["id"]}, {"_id": 0}).to_list(None)
        return [s["id"] for s in stores], {s["id"]: s["name"] for s in stores}

    async def audit(user, action, store_id, previous, new, note="", entry_id=""):
        await db.cash_flow_audit.insert_one({
            "id": str(uuid.uuid4()), "user_id": user["id"], "user_email": user.get("email", ""),
            "store_id": store_id, "entry_id": entry_id, "action": action,
            "previous_value": previous, "new_value": new, "note": note, "timestamp": now_iso()})

    def entry_query(user, store_ids, marketplace, include_company=False):
        scope = list(store_ids) + ([COMPANY_SCOPE] if include_company else [])
        q = {"user_id": user["id"], "store_id": {"$in": scope}}
        if marketplace and marketplace != "ALL":
            q["marketplace"] = marketplace
        return q

    async def capital_store_ids(user):
        """Stores whose starting cash is already represented by dated Sermaye & Kasa capital."""
        return set(await db.company_capital.distinct(
            "store_id", {"user_id": user["id"], "entries.0": {"$exists": True}}))

    async def opening_total(user, store_ids):
        superseded = await capital_store_ids(user)
        docs = await db.cash_flow_opening_balances.find(
            {"user_id": user["id"], "store_id": {"$in": store_ids}}, {"_id": 0}).to_list(None)
        # A manual opening balance is NOT applied for a store that has Sermaye & Kasa capital:
        # the dated capital injection already carries that starting cash (no double counting).
        return sum(D(d.get("amount_usd", 0)) for d in docs if d["store_id"] not in superseded)

    async def inventory_metrics(user, store_ids, marketplace, start, end):
        lot_q = {"user_id": user["id"], "store_id": {"$in": store_ids}}
        if marketplace and marketplace != "ALL":
            lot_q["marketplace"] = marketplace
        purchases, current_value = Decimal(0), Decimal(0)
        async for lot in db.fba_lots.find(lot_q, {"_id": 0}):
            if in_range(lot["purchase_date"], start, end):
                purchases += q2(D(lot["original_quantity"]) * D(lot["product_unit_cost_usd"])
                                + D(lot.get("inbound_shipping_total_usd", 0)))
            if lot.get("lot_status") == "OPEN" and lot.get("remaining_quantity", 0) > 0:
                current_value += q2(D(lot.get("landed_unit_cost_usd", 0)) * D(lot["remaining_quantity"]))
        alloc_q = {"user_id": user["id"], "store_id": {"$in": store_ids}, "status": "active"}
        if marketplace and marketplace != "ALL":
            alloc_q["marketplace"] = marketplace
        realized = Decimal(0)
        async for alloc in db.fba_allocations.find(alloc_q, {"_id": 0}):
            if in_range(alloc.get("order_date", ""), start, end):
                realized += D(alloc.get("total_allocated_cost_usd", 0))
        return float(q2(purchases)), float(q2(current_value)), float(q2(realized))

    async def load_view(user, store_id, marketplace, start_date, end_date):
        """Shared scope: synced entries + opening cash as of period start."""
        if start_date and end_date and start_date > end_date:
            raise HTTPException(400, "Başlangıç tarihi bitişten sonra olamaz")
        await sync_cash_flow(db, user["id"])
        store_ids, names = await scope_stores(user, store_id)
        company_wide = not store_id or store_id == "ALL"
        if company_wide:
            names = {**names, COMPANY_SCOPE: "Şirket (Genel)"}
        entries = await db.cash_flow_entries.find(
            entry_query(user, store_ids, marketplace, include_company=company_wide), {"_id": 0}).to_list(None)
        entries.sort(key=lambda e: (e["date"], e.get("created_at", ""), e["id"]))
        opening = await opening_total(user, store_ids)
        if start_date:
            prior = sum(D(e["amount_usd"]) if e["direction"] == IN else -D(e["amount_usd"])
                        for e in entries if e["date"] < start_date)
            opening += prior
        return entries, store_ids, names, q2(opening)

    # ------------------------------- reads -------------------------------
    @router.get("/summary")
    async def cashflow_summary(user=Depends(get_current_user), store_id: Optional[str] = None,
                               marketplace: Optional[str] = None, start_date: Optional[str] = None,
                               end_date: Optional[str] = None):
        entries, store_ids, _names, opening = await load_view(user, store_id, marketplace, start_date, end_date)
        period = [e for e in entries if in_range(e["date"], start_date, end_date)]
        cash_in = sum(D(e["amount_usd"]) for e in period if e["direction"] == IN)
        cash_out = sum(D(e["amount_usd"]) for e in period if e["direction"] == OUT)
        net = q2(cash_in - cash_out)
        closing = q2(opening + net)
        purchases, current_value, realized = await inventory_metrics(
            user, store_ids, marketplace, start_date, end_date)
        superseded = sorted(set(store_ids) & await capital_store_ids(user))
        return {
            "currency": "USD",
            "opening_cash": float(q2(opening)),
            "opening_source": "sermaye_kasa" if superseded else "manual",
            "manual_opening_superseded_store_ids": superseded,
            "cash_in": float(q2(cash_in)),
            "cash_out": float(q2(cash_out)),
            "net_cash_flow": float(net),
            "closing_cash": float(closing),
            "inventory_purchases": purchases,
            "current_inventory_value": current_value,
            "capital_tied_in_inventory": current_value,
            "realized_inventory_cost": realized,
            "entry_count": len(period),
            "store_id": store_id or "ALL", "marketplace": marketplace or "ALL",
            "start_date": start_date, "end_date": end_date,
        }

    @router.get("/entries")
    async def cashflow_entries(user=Depends(get_current_user), store_id: Optional[str] = None,
                               marketplace: Optional[str] = None, start_date: Optional[str] = None,
                               end_date: Optional[str] = None):
        entries, _ids, names, opening = await load_view(user, store_id, marketplace, start_date, end_date)
        balance = D(opening)
        rows = []
        for e in entries:
            if not in_range(e["date"], start_date, end_date):
                continue
            signed = D(e["amount_usd"]) if e["direction"] == IN else -D(e["amount_usd"])
            balance += signed
            rows.append({
                "id": e["id"], "date": e["date"], "store_id": e["store_id"],
                "store_name": names.get(e["store_id"], ""), "marketplace": e.get("marketplace", ""),
                "direction": e["direction"], "category": e["category"],
                "description": e.get("description", ""), "source_type": e["source_type"],
                "source_label": SOURCE_LABELS.get(e["source_type"], e["source_type"]),
                "source_module": SOURCE_MODULES.get(e["source_type"], ""),
                "order_id": e.get("order_id", ""), "lot_id": e.get("lot_id", ""),
                "cash_in": float(q2(e["amount_usd"])) if e["direction"] == IN else None,
                "cash_out": float(q2(e["amount_usd"])) if e["direction"] == OUT else None,
                "running_balance": float(q2(balance)), "is_manual": bool(e.get("is_manual")),
                "source_id": e.get("source_id", ""),
                "original_amount": e.get("original_amount"),
                "original_currency": e.get("original_currency", ""),
                "payment_reference": e.get("payment_reference", ""),
            })
        return {"currency": "USD", "opening_cash": float(q2(opening)),
                "closing_cash": float(q2(balance)), "rows": rows}

    @router.get("/monthly")
    async def cashflow_monthly(user=Depends(get_current_user), store_id: Optional[str] = None,
                               marketplace: Optional[str] = None, start_date: Optional[str] = None,
                               end_date: Optional[str] = None):
        entries, _ids, _names, opening = await load_view(user, store_id, marketplace, start_date, end_date)
        months = sorted({e["date"][:7] for e in entries if in_range(e["date"], start_date, end_date)})
        balance = D(opening)
        out = []
        for month in months:
            bucket = [e for e in entries if e["date"][:7] == month]

            def total(direction, *sources):
                return sum(D(e["amount_usd"]) for e in bucket
                           if e["direction"] == direction and e["source_type"] in sources)

            amazon_in = total(IN, AMAZON_PAYMENT, AMAZON_DISBURSEMENT)
            financing_in = total(IN, *FINANCING_IN)
            financing_out = total(OUT, *FINANCING_OUT)
            other_in = total(IN, MANUAL) + financing_in
            purchases = total(OUT, FBA_INVENTORY_PURCHASE)
            inbound = total(OUT, FBA_INBOUND_SHIPPING)
            fbm_product = total(OUT, FBM_PRODUCT_COST)
            fbm_shipping = total(OUT, FBM_SHIPPING_COST)
            extra = total(OUT, EXTRA_COST)
            other_out = total(OUT, MANUAL) + financing_out
            beginning = q2(balance)
            net = q2(amazon_in + other_in - purchases - inbound - fbm_product - fbm_shipping - extra - other_out)
            balance = D(beginning) + net
            out.append({
                "month": month, "beginning_cash": float(beginning),
                "amazon_cash_in": float(q2(amazon_in)), "other_cash_in": float(q2(other_in)),
                "capital_cash_in": float(q2(financing_in)), "capital_cash_out": float(q2(financing_out)),
                "inventory_purchases": float(q2(purchases)), "fba_inbound_shipping": float(q2(inbound)),
                "fbm_product_costs": float(q2(fbm_product)), "fbm_shipping_costs": float(q2(fbm_shipping)),
                "extra_costs": float(q2(extra)), "other_cash_out": float(q2(other_out)),
                "net_cash_flow": float(net), "ending_cash": float(q2(balance)),
            })
        return {"currency": "USD", "months": out}

    # --------------------------- manual entries ---------------------------
    @router.post("/manual", status_code=201)
    async def create_manual(data: ManualEntryIn, user=Depends(get_current_user)):
        store = await own_store(data.store_id, user)
        if data.marketplace and data.marketplace not in store["marketplaces"]:
            raise HTTPException(400, "Geçerli bir pazar yeri seçin")
        now = now_iso()
        entry_id = str(uuid.uuid4())
        doc = {
            "id": entry_id, "user_id": user["id"], "idem_key": f"{MANUAL}:{entry_id}",
            "store_id": store["id"], "marketplace": data.marketplace or "",
            "date": data.date, "direction": data.direction, "category": data.category,
            "amount_usd": data.amount_usd, "source_type": MANUAL, "source_id": entry_id,
            "order_id": "", "lot_id": "", "description": data.description,
            "is_manual": True, "created_at": now, "updated_at": now,
        }
        await db.cash_flow_entries.insert_one(doc)
        await audit(user, "manual_create", store["id"], None,
                    {k: doc[k] for k in ("date", "direction", "category", "amount_usd", "description")},
                    entry_id=entry_id)
        doc.pop("_id", None)
        return doc

    @router.put("/manual/{entry_id}")
    async def update_manual(entry_id: str, data: ManualEntryUpdateIn, user=Depends(get_current_user)):
        entry = await db.cash_flow_entries.find_one(
            {"id": entry_id, "user_id": user["id"], "is_manual": True}, {"_id": 0})
        if not entry:
            raise HTTPException(404, "Manuel kayıt bulunamadı")
        changes = {k: v for k, v in data.model_dump(exclude_none=True).items()}
        if "marketplace" in changes and changes["marketplace"]:
            store = await own_store(entry["store_id"], user)
            if changes["marketplace"] not in store["marketplaces"]:
                raise HTTPException(400, "Geçerli bir pazar yeri seçin")
        if not changes:
            return entry
        previous = {k: entry.get(k) for k in changes}
        changes["updated_at"] = now_iso()
        await db.cash_flow_entries.update_one({"id": entry_id, "user_id": user["id"]}, {"$set": changes})
        await audit(user, "manual_update", entry["store_id"], previous,
                    {k: v for k, v in changes.items() if k != "updated_at"}, entry_id=entry_id)
        return await db.cash_flow_entries.find_one({"id": entry_id}, {"_id": 0})

    @router.delete("/manual/{entry_id}")
    async def delete_manual(entry_id: str, user=Depends(get_current_user)):
        entry = await db.cash_flow_entries.find_one(
            {"id": entry_id, "user_id": user["id"], "is_manual": True}, {"_id": 0})
        if not entry:
            raise HTTPException(404, "Manuel kayıt bulunamadı")
        await db.cash_flow_entries.delete_one({"id": entry_id, "user_id": user["id"]})
        await audit(user, "manual_delete", entry["store_id"],
                    {k: entry.get(k) for k in ("date", "direction", "category", "amount_usd", "description")},
                    None, entry_id=entry_id)
        return {"deleted": True, "id": entry_id}

    # --------------------------- opening balance ---------------------------
    @router.get("/opening-balances")
    async def list_opening_balances(user=Depends(get_current_user)):
        stores = await db.stores.find({"user_id": user["id"]}, {"_id": 0}).to_list(None)
        docs = {d["store_id"]: d for d in await db.cash_flow_opening_balances.find(
            {"user_id": user["id"]}, {"_id": 0}).to_list(None)}
        superseded = await capital_store_ids(user)
        return {"currency": "USD", "balances": [{
            "store_id": s["id"], "store_name": s["name"],
            "amount_usd": float(q2((docs.get(s["id"]) or {}).get("amount_usd", 0))),
            "updated_at": (docs.get(s["id"]) or {}).get("updated_at"),
            "history": (docs.get(s["id"]) or {}).get("history", []),
            "superseded_by_capital": s["id"] in superseded,
        } for s in stores]}

    @router.put("/opening-balance")
    async def set_opening_balance(data: OpeningBalanceIn, user=Depends(get_current_user)):
        store = await own_store(data.store_id, user)
        now = now_iso()
        existing = await db.cash_flow_opening_balances.find_one(
            {"user_id": user["id"], "store_id": store["id"]}, {"_id": 0})
        previous = float(q2((existing or {}).get("amount_usd", 0)))
        history_entry = {"previous_amount_usd": previous, "new_amount_usd": data.amount_usd,
                         "changed_by": user.get("email", ""), "changed_at": now, "note": data.note}
        await db.cash_flow_opening_balances.update_one(
            {"user_id": user["id"], "store_id": store["id"]},
            {"$set": {"amount_usd": data.amount_usd, "updated_at": now},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now},
             "$push": {"history": {"$each": [history_entry], "$slice": -100}}},
            upsert=True)
        await audit(user, "opening_balance_update", store["id"], previous, data.amount_usd, note=data.note)
        return {"store_id": store["id"], "amount_usd": data.amount_usd, "updated_at": now}

    @router.get("/audit")
    async def cashflow_audit(user=Depends(get_current_user), store_id: Optional[str] = None):
        q = {"user_id": user["id"]}
        if store_id and store_id != "ALL":
            q["store_id"] = store_id
        rows = await db.cash_flow_audit.find(q, {"_id": 0}).sort("timestamp", -1).to_list(200)
        return {"rows": rows}

    return router
