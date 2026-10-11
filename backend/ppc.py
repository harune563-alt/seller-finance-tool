"""PPC advertising-cost ATTRIBUTION module.

Financial principle (do not violate):
- Amazon Payments is the ONLY financial accounting source for PPC/advertising
  spend once Amazon has deducted the charge from the seller balance.
- This module stores ASIN/campaign ATTRIBUTION only. It NEVER creates an expense
  transaction, so general Total Expense / P&L / Dashboard / Cash Flow can never be
  double-counted. The $300 Amazon charge stays $300; PPC merely explains that
  ASIN-A consumed $180 and ASIN-B $120 of that same $300.

Reconciliation status per attribution (marketplace + month scope):
- "reconciled"      : a financial advertising expense exists in Amazon Payments.
- "pending_match"   : imported PPC exists but no financial charge appeared yet.
- "manual_ppc"      : manually entered PPC with no financial charge yet.
- "unmatched"       : attribution has neither ASIN nor campaign to attach to.
"""
import uuid
from datetime import date as calendar_date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

from usd_ledger import enrich_records

SOURCE_IMPORT, SOURCE_MANUAL = "ppc_import", "manual_ppc"

# A transaction is a FINANCIAL advertising expense (the real accounting source)
# when it is an expense and is categorised as advertising OR lives in the PPC lane.
PPC_EXPENSE_CATEGORIES = {
    "ppc reklam harcaması", "reklam harcaması", "reklam",
    "advertising", "cost of advertising", "cost of advertising(ppc)",
    "ppc", "sponsored products", "amazon advertising",
}

RECON_RECONCILED = "reconciled"
RECON_PENDING = "pending_match"
RECON_MANUAL = "manual_ppc"
RECON_UNMATCHED = "unmatched"

RECON_LABELS = {
    RECON_RECONCILED: "Amazon Payments ile eşleşti",
    RECON_PENDING: "Ödeme eşleşmesi bekliyor",
    RECON_MANUAL: "Manuel PPC",
    RECON_UNMATCHED: "Eşleşmedi",
}


def D(value):
    return Decimal(str(value or 0))


def q2(value):
    return D(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def in_range(day, start, end):
    return (not start or day >= start) and (not end or day <= end)


def is_ad_expense(tx):
    if tx.get("type") != "expense":
        return False
    return (tx.get("category") or "").strip().lower() in PPC_EXPENSE_CATEGORIES \
        or tx.get("section") == "ppc"


def idem_key(store_id, source, marketplace, date, campaign, asin, sku):
    parts = [store_id, source, (marketplace or "").upper(), date,
             (campaign or "").strip().lower(), (asin or "").strip().upper(),
             (sku or "").strip().upper()]
    return "|".join(parts)


async def initialize_ppc_indexes(db):
    await db.ppc_attributions.create_index([("user_id", 1), ("idem_key", 1)], unique=True)
    await db.ppc_attributions.create_index([("user_id", 1), ("store_id", 1), ("date", 1)])
    await db.ppc_attributions.create_index([("user_id", 1), ("store_id", 1), ("asin", 1)])


async def financial_ad_expense_by_month(db, user_id, store_id, marketplace=None):
    """Sum of REAL advertising expenses (Amazon Payments / manual) per (marketplace, month).

    This is the single accounting source used to decide reconciliation; it reads
    existing transactions and never writes."""
    q = {"user_id": user_id}
    if store_id and store_id != "ALL":
        q["store_id"] = store_id
    if marketplace and marketplace != "ALL":
        q["marketplace"] = marketplace
    txs = await db.transactions.find(q, {"_id": 0}).to_list(None)
    ad = [t for t in txs if is_ad_expense(t)]
    ad = await enrich_records(db, ad)
    by_month = {}
    for t in ad:
        amount = t.get("amount_usd")
        if amount is None:
            continue
        key = (t.get("marketplace", ""), (t.get("date") or "")[:7])
        by_month[key] = by_month.get(key, Decimal(0)) + D(amount)
    return by_month


def reconciliation_status(record, ad_by_month):
    if not (record.get("asin") or record.get("campaign")):
        return RECON_UNMATCHED
    key = (record.get("marketplace", ""), (record.get("date") or "")[:7])
    if ad_by_month.get(key, Decimal(0)) > 0:
        return RECON_RECONCILED
    if record.get("source") == SOURCE_MANUAL:
        return RECON_MANUAL
    return RECON_PENDING


async def ppc_attribution_by_asin(db, user_id, store_id, start=None, end=None, marketplace=None):
    """{asin: {"spend": Decimal, "sales": Decimal}} for the FBA ASIN profit report."""
    q = {"user_id": user_id}
    if store_id and store_id != "ALL":
        q["store_id"] = store_id
    if marketplace and marketplace != "ALL":
        q["marketplace"] = marketplace
    out = {}
    async for rec in db.ppc_attributions.find(q, {"_id": 0}):
        if not in_range(rec.get("date", ""), start, end):
            continue
        asin = (rec.get("asin") or "—").strip() or "—"
        b = out.setdefault(asin, {"spend": Decimal(0), "sales": Decimal(0)})
        b["spend"] += D(rec.get("ad_spend_usd"))
        b["sales"] += D(rec.get("ppc_sales_usd"))
    return out


# ---------------------------------------------------------------------------
# Request models
# ---------------------------------------------------------------------------
class AttributionIn(BaseModel):
    store_id: str
    marketplace: str = Field(default="", max_length=10)
    date: str
    campaign: str = Field(default="", max_length=200)
    asin: str = Field(default="", max_length=40)
    sku: str = Field(default="", max_length=200)
    ad_spend_usd: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False)
    ppc_sales_usd: float = Field(default=0, ge=0, le=1_000_000_000, allow_inf_nan=False)
    clicks: int = Field(default=0, ge=0, le=1_000_000_000)
    impressions: int = Field(default=0, ge=0, le=1_000_000_000_000)
    orders: int = Field(default=0, ge=0, le=1_000_000_000)

    @field_validator("date")
    @classmethod
    def valid_date(cls, v):
        return calendar_date.fromisoformat(v).isoformat()

    @field_validator("campaign", "asin", "sku", "marketplace", mode="before")
    @classmethod
    def strip_text(cls, v):
        return v.strip() if isinstance(v, str) else (v or "")


class AttributionImportIn(BaseModel):
    store_id: str
    rows: List[AttributionIn]


# ---------------------------------------------------------------------------
# Router
# ---------------------------------------------------------------------------
def ppc_router(db, get_current_user, marketplaces):
    router = APIRouter(prefix="/ppc", tags=["ppc"])

    async def own_store(store_id, user):
        store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0})
        if not store:
            raise HTTPException(404, "Mağaza bulunamadı")
        return store

    def build_doc(user, data: AttributionIn, source):
        key = idem_key(data.store_id, source, data.marketplace, data.date,
                       data.campaign, data.asin, data.sku)
        return {
            "user_id": user["id"], "store_id": data.store_id, "marketplace": data.marketplace,
            "date": data.date, "campaign": data.campaign, "asin": data.asin, "sku": data.sku,
            "ad_spend_usd": float(q2(data.ad_spend_usd)), "ppc_sales_usd": float(q2(data.ppc_sales_usd)),
            "clicks": data.clicks, "impressions": data.impressions, "orders": data.orders,
            "source": source, "idem_key": key,
        }

    async def upsert(doc):
        now = now_iso()
        res = await db.ppc_attributions.update_one(
            {"user_id": doc["user_id"], "idem_key": doc["idem_key"]},
            {"$set": {**doc, "updated_at": now},
             "$setOnInsert": {"id": str(uuid.uuid4()), "created_at": now}},
            upsert=True)
        return bool(res.upserted_id)

    @router.post("/attributions", status_code=201)
    async def create_attribution(data: AttributionIn, user=Depends(get_current_user)):
        store = await own_store(data.store_id, user)
        if data.marketplace and data.marketplace not in store["marketplaces"]:
            raise HTTPException(400, "Geçerli bir pazar yeri seçin")
        doc = build_doc(user, data, SOURCE_MANUAL)
        inserted = await upsert(doc)
        saved = await db.ppc_attributions.find_one(
            {"user_id": user["id"], "idem_key": doc["idem_key"]}, {"_id": 0})
        return {"inserted": inserted, "attribution": saved}

    @router.post("/attributions/import")
    async def import_attributions(data: AttributionImportIn, user=Depends(get_current_user)):
        store = await own_store(data.store_id, user)
        inserted = updated = 0
        for row in data.rows:
            if row.store_id != data.store_id:
                raise HTTPException(400, "Satır mağazası yüklemeyle uyuşmuyor")
            if row.marketplace and row.marketplace not in store["marketplaces"]:
                raise HTTPException(400, f"Geçersiz pazar yeri: {row.marketplace}")
            doc = build_doc(user, row, SOURCE_IMPORT)
            if await upsert(doc):
                inserted += 1
            else:
                updated += 1
        return {"inserted": inserted, "updated": updated, "total": len(data.rows)}

    @router.get("/attributions")
    async def list_attributions(user=Depends(get_current_user), store_id: Optional[str] = None,
                                marketplace: Optional[str] = None, start_date: Optional[str] = None,
                                end_date: Optional[str] = None):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(400, "Başlangıç tarihi bitişten sonra olamaz")
        q = {"user_id": user["id"]}
        if store_id and store_id != "ALL":
            q["store_id"] = store_id
        if marketplace and marketplace != "ALL":
            q["marketplace"] = marketplace
        records = await db.ppc_attributions.find(q, {"_id": 0}).to_list(None)
        records = [r for r in records if in_range(r.get("date", ""), start_date, end_date)]
        records.sort(key=lambda r: (r.get("date", ""), r.get("campaign", ""), r.get("asin", "")))
        ad_by_month = await financial_ad_expense_by_month(db, user["id"], store_id, marketplace)
        rows, totals = [], {"ad_spend": Decimal(0), "ppc_sales": Decimal(0)}
        status_counts = {k: 0 for k in RECON_LABELS}
        for r in records:
            status = reconciliation_status(r, ad_by_month)
            status_counts[status] += 1
            totals["ad_spend"] += D(r["ad_spend_usd"])
            totals["ppc_sales"] += D(r["ppc_sales_usd"])
            spend, sales = D(r["ad_spend_usd"]), D(r["ppc_sales_usd"])
            rows.append({**r, "reconciliation_status": status,
                         "reconciliation_label": RECON_LABELS[status],
                         "acos_percent": float(q2(spend / sales * 100)) if sales else None,
                         "roas": float(q2(sales / spend)) if spend else None})
        financial_total = sum(ad_by_month.values())
        return {
            "rows": rows,
            "summary": {
                "attributed_ad_spend_usd": float(q2(totals["ad_spend"])),
                "attributed_ppc_sales_usd": float(q2(totals["ppc_sales"])),
                "financial_ad_expense_usd": float(q2(financial_total)),
                "status_counts": status_counts,
                "acos_percent": float(q2(totals["ad_spend"] / totals["ppc_sales"] * 100)) if totals["ppc_sales"] else None,
                "roas": float(q2(totals["ppc_sales"] / totals["ad_spend"])) if totals["ad_spend"] else None,
            },
            "currency": "USD",
        }

    @router.get("/reconciliation")
    async def reconciliation(user=Depends(get_current_user), store_id: Optional[str] = None,
                             marketplace: Optional[str] = None):
        ad_by_month = await financial_ad_expense_by_month(db, user["id"], store_id, marketplace)
        q = {"user_id": user["id"]}
        if store_id and store_id != "ALL":
            q["store_id"] = store_id
        if marketplace and marketplace != "ALL":
            q["marketplace"] = marketplace
        attributed = {}
        async for r in db.ppc_attributions.find(q, {"_id": 0}):
            key = (r.get("marketplace", ""), (r.get("date") or "")[:7])
            attributed[key] = attributed.get(key, Decimal(0)) + D(r["ad_spend_usd"])
        keys = sorted(set(ad_by_month) | set(attributed))
        rows = []
        for (mp, month) in keys:
            fin = ad_by_month.get((mp, month), Decimal(0))
            att = attributed.get((mp, month), Decimal(0))
            rows.append({
                "marketplace": mp, "month": month,
                "financial_ad_expense_usd": float(q2(fin)),
                "attributed_ad_spend_usd": float(q2(att)),
                "unattributed_usd": float(q2(fin - att)),
                "status": RECON_RECONCILED if fin > 0 and att > 0 else
                          RECON_PENDING if att > 0 and fin == 0 else "financial_only",
            })
        return {"rows": rows, "currency": "USD"}

    @router.delete("/attributions/{attribution_id}")
    async def delete_attribution(attribution_id: str, user=Depends(get_current_user)):
        res = await db.ppc_attributions.delete_one({"id": attribution_id, "user_id": user["id"]})
        if not res.deleted_count:
            raise HTTPException(404, "PPC kaydı bulunamadı")
        return {"deleted": True, "id": attribution_id}

    return router
