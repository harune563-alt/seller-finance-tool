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
import csv
import io
import re
import uuid
from datetime import date as calendar_date, datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Query
from pydantic import BaseModel, Field, field_validator

from amazon_csv import parse_amount, parse_date
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
RECON_PARTIAL = "partially_reconciled"
RECON_PENDING = "pending_match"
RECON_FIN_ONLY = "financial_only"
RECON_PPC_ONLY = "ppc_only"
RECON_UNMATCHED = "unmatched"

RECON_LABELS = {
    RECON_RECONCILED: "Amazon Payments ile mutabık",
    RECON_PARTIAL: "Kısmen mutabık",
    RECON_PENDING: "Ödeme eşleşmesi bekliyor",
    RECON_FIN_ONLY: "Yalnızca finansal",
    RECON_PPC_ONLY: "Yalnızca PPC verisi",
    RECON_UNMATCHED: "Eşleşmedi",
}
TOLERANCE = Decimal("0.005")


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
        or tx.get("section") == "ppc" or tx.get("classification") == "PPC_ADVERTISING_EXPENSE"


def idem_key(store_id, source, marketplace, date, campaign, asin, sku):
    parts = [store_id, source, (marketplace or "").upper(), date,
             (campaign or "").strip().lower(), (asin or "").strip().upper(),
             (sku or "").strip().upper()]
    return "|".join(parts)


async def initialize_ppc_indexes(db):
    await db.ppc_attributions.create_index([("user_id", 1), ("idem_key", 1)], unique=True)
    await db.ppc_attributions.create_index([("user_id", 1), ("store_id", 1), ("date", 1)])
    await db.ppc_attributions.create_index([("user_id", 1), ("store_id", 1), ("asin", 1)])


def scope_query(user_id, store_id, marketplace):
    q = {"user_id": user_id}
    if store_id and store_id != "ALL":
        q["store_id"] = store_id
    if marketplace and marketplace != "ALL":
        q["marketplace"] = marketplace
    return q


async def financial_ad_expenses(db, user_id, store_id, marketplace=None):
    """REAL advertising expense transactions (Amazon Payments / manual), USD-enriched. Read-only."""
    txs = await db.transactions.find(scope_query(user_id, store_id, marketplace), {"_id": 0}).to_list(None)
    return await enrich_records(db, [t for t in txs if is_ad_expense(t)])


def by_month(items, amount_of):
    out = {}
    for item in items:
        amount = amount_of(item)
        if amount is None:
            continue
        key = (item.get("marketplace", ""), (item.get("date") or "")[:7])
        out[key] = out.get(key, Decimal(0)) + D(amount)
    return out


async def financial_ad_expense_by_month(db, user_id, store_id, marketplace=None):
    return by_month(await financial_ad_expenses(db, user_id, store_id, marketplace), lambda t: t.get("amount_usd"))


def month_status(fin, att):
    if fin > 0 and att <= 0:
        return RECON_FIN_ONLY
    if fin <= 0 and att > 0:
        return RECON_PENDING
    if fin > 0 and att >= fin - TOLERANCE:
        return RECON_RECONCILED
    if fin > 0:
        return RECON_PARTIAL
    return RECON_UNMATCHED


def reconciliation_status(record, ad_by_month, att_by_month):
    if not (record.get("asin") or record.get("campaign")):
        return RECON_UNMATCHED
    key = (record.get("marketplace", ""), (record.get("date") or "")[:7])
    fin = ad_by_month.get(key, Decimal(0))
    if fin <= 0:
        return RECON_PPC_ONLY if record.get("source") == SOURCE_MANUAL else RECON_PENDING
    return month_status(fin, att_by_month.get(key, Decimal(0)))


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
# PPC report (Amazon Advertising export) parsing
# ---------------------------------------------------------------------------
PPC_HEADER_ALIASES = {
    "date": {"date", "day", "startdate", "reportdate", "tarih"},
    "campaign": {"campaignname", "campaign", "kampanya", "kampanyaadi"},
    "ad_type": {"adtype", "campaigntype", "adproduct", "reklamtipi"},
    "asin": {"advertisedasin", "asin"},
    "sku": {"advertisedsku", "sku"},
    "ad_spend_usd": {"spend", "cost", "adspend", "totalspend", "harcama"},
    "ppc_sales_usd": {"7daytotalsales", "14daytotalsales", "30daytotalsales", "sales", "totalsales",
                      "ppcsales", "attributedsales", "7dayadvertisedskusales"},
    "orders": {"7daytotalorders", "14daytotalorders", "30daytotalorders", "orders", "totalorders",
               "ppcorders", "purchases"},
    "clicks": {"clicks", "tiklama"},
    "impressions": {"impressions", "gosterim"},
}


def _hkey(value):
    return re.sub(r"[^a-z0-9]", "", str(value or "").lower())


def _report_rows(content, name):
    if name.endswith(".xlsx"):
        from openpyxl import load_workbook
        sheet = load_workbook(io.BytesIO(content), read_only=True, data_only=True).active
        return [list(r) for r in sheet.iter_rows(values_only=True)]
    text = content.decode("utf-8-sig", errors="replace")
    first = text.splitlines()[0] if text else ""
    delimiter = "\t" if "\t" in first else ";" if first.count(";") > first.count(",") else ","
    return list(csv.reader(io.StringIO(text), delimiter=delimiter))


def _num(value, integer=False):
    if value is None or str(value).strip() in ("", "-", "—"):
        return 0
    if isinstance(value, (int, float)):
        return int(value) if integer else float(value)
    amount = parse_amount(str(value).replace("%", ""))
    return int(amount) if integer else float(amount)


def parse_ppc_report(content, name, marketplace):
    """Return (rows aggregated per idempotency identity, issues)."""
    table = _report_rows(content, name)
    header_idx, cols = None, {}
    for i, row in enumerate(table[:30]):
        keys = [_hkey(c) for c in row]
        found = {f: keys.index(k) for f, aliases in PPC_HEADER_ALIASES.items() for k in keys if k in aliases}
        if "date" in found and "ad_spend_usd" in found:
            header_idx, cols = i, found
            break
    if header_idx is None:
        raise ValueError("PPC raporunda Tarih ve Harcama (Spend) sütunları bulunamadı")
    merged, issues = {}, []
    for offset, row in enumerate(table[header_idx + 1:], start=header_idx + 2):
        if not row or not any(str(c or "").strip() for c in row):
            continue
        get = lambda f: row[cols[f]] if f in cols and cols[f] < len(row) else None
        try:
            raw_date = get("date")
            day = raw_date.date().isoformat() if isinstance(raw_date, datetime) else parse_date(str(raw_date or ""), marketplace)
            rec = {"marketplace": marketplace, "date": day,
                   "campaign": str(get("campaign") or "").strip(), "ad_type": str(get("ad_type") or "").strip(),
                   "asin": str(get("asin") or "").strip().upper(), "sku": str(get("sku") or "").strip(),
                   "ad_spend_usd": _num(get("ad_spend_usd")), "ppc_sales_usd": _num(get("ppc_sales_usd")),
                   "clicks": _num(get("clicks"), True), "impressions": _num(get("impressions"), True),
                   "orders": _num(get("orders"), True)}
            if rec["ad_spend_usd"] < 0:
                raise ValueError("Harcama negatif olamaz")
        except (ValueError, TypeError, ArithmeticError) as exc:
            issues.append({"line": offset, "reason": str(exc) or "Geçersiz satır"})
            continue
        key = (rec["date"], rec["campaign"].lower(), rec["asin"], rec["sku"].upper())
        if key in merged:
            m = merged[key]
            for k in ("ad_spend_usd", "ppc_sales_usd", "clicks", "impressions", "orders"):
                m[k] += rec[k]
        else:
            merged[key] = rec
    return list(merged.values()), issues


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
    ppc_category: str = Field(default="PPC Reklam Harcaması", max_length=120)
    ad_type: str = Field(default="", max_length=80)
    notes: str = Field(default="", max_length=1000)

    @field_validator("date")
    @classmethod
    def valid_date(cls, v):
        return calendar_date.fromisoformat(v).isoformat()

    @field_validator("campaign", "asin", "sku", "marketplace", "ppc_category", "ad_type", "notes", mode="before")
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
            "ppc_category": data.ppc_category, "ad_type": data.ad_type, "notes": data.notes,
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

    @router.post("/attributions/import-file")
    async def import_report_file(file: UploadFile = File(...), store_id: str = Query(...),
                                 marketplace: str = Query(...), commit: bool = False,
                                 user=Depends(get_current_user)):
        store = await own_store(store_id, user)
        if marketplace not in store["marketplaces"]:
            raise HTTPException(400, "Geçerli bir pazar yeri seçin")
        name = (file.filename or "").lower()
        if not name.endswith((".csv", ".xlsx", ".tsv", ".txt")):
            raise HTTPException(400, "CSV veya XLSX PPC raporu seçin")
        content = await file.read(10 * 1024 * 1024 + 1)
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "Dosya en fazla 10 MB olabilir")
        try:
            rows, issues = parse_ppc_report(content, name, marketplace)
        except ValueError as exc:
            raise HTTPException(400, str(exc))
        inserted = updated = 0
        docs = [build_doc(user, AttributionIn(store_id=store_id, **r), SOURCE_IMPORT) for r in rows]
        if commit:
            for doc in docs:
                if await upsert(doc):
                    inserted += 1
                else:
                    updated += 1
        else:
            keys = [d["idem_key"] for d in docs]
            existing = await db.ppc_attributions.count_documents({"user_id": user["id"], "idem_key": {"$in": keys}})
            inserted, updated = len(docs) - existing, existing
        return {"committed": commit, "total": len(docs), "new": inserted, "existing": updated,
                "issues": issues[:100], "rejected_count": len(issues),
                "total_spend_usd": float(q2(sum(D(d["ad_spend_usd"]) for d in docs))),
                "preview": docs[:20]}

    @router.get("/asin-lookup")
    async def asin_lookup(store_id: str, asin: str, user=Depends(get_current_user)):
        await own_store(store_id, user)
        key = asin.strip().upper()
        lots = await db.fba_lots.find({"user_id": user["id"], "store_id": store_id,
                                       "asin": {"$regex": f"^{re.escape(key)}$", "$options": "i"}},
                                      {"_id": 0, "sku": 1, "product_name": 1, "marketplace": 1}).to_list(200)
        skus = sorted({l["sku"] for l in lots if l.get("sku")})
        names = [l["product_name"] for l in lots if l.get("product_name")]
        return {"asin": key, "found": bool(lots), "skus": skus, "product_name": names[0] if names else ""}

    @router.get("/attributions")
    async def list_attributions(user=Depends(get_current_user), store_id: Optional[str] = None,
                                marketplace: Optional[str] = None, start_date: Optional[str] = None,
                                end_date: Optional[str] = None, asin: Optional[str] = None,
                                campaign: Optional[str] = None):
        if start_date and end_date and start_date > end_date:
            raise HTTPException(400, "Başlangıç tarihi bitişten sonra olamaz")
        all_records = await db.ppc_attributions.find(
            scope_query(user["id"], store_id, marketplace), {"_id": 0}).to_list(None)
        att_by_month = by_month(all_records, lambda r: r.get("ad_spend_usd"))
        in_scope = [r for r in all_records if in_range(r.get("date", ""), start_date, end_date)]
        asin_q, camp_q = (asin or "").strip().upper(), (campaign or "").strip().lower()
        records = [r for r in in_scope
                   if (not asin_q or asin_q in (r.get("asin") or "").upper())
                   and (not camp_q or camp_q in (r.get("campaign") or "").lower())]
        records.sort(key=lambda r: (r.get("date", ""), r.get("campaign", ""), r.get("asin", "")))
        fin_txs = await financial_ad_expenses(db, user["id"], store_id, marketplace)
        ad_by_month = by_month(fin_txs, lambda t: t.get("amount_usd"))
        rows = []
        t = {k: Decimal(0) for k in ("spend", "sales", "clicks", "impressions", "orders")}
        status_counts = {k: 0 for k in RECON_LABELS}
        for r in records:
            status = reconciliation_status(r, ad_by_month, att_by_month)
            status_counts[status] += 1
            spend, sales = D(r["ad_spend_usd"]), D(r["ppc_sales_usd"])
            t["spend"] += spend
            t["sales"] += sales
            for k in ("clicks", "impressions", "orders"):
                t[k] += D(r.get(k))
            rows.append({**r, "reconciliation_status": status,
                         "reconciliation_label": RECON_LABELS[status],
                         "acos_percent": float(q2(spend / sales * 100)) if sales else None,
                         "roas": float(q2(sales / spend)) if spend else None})
        financial_total = sum((D(x["amount_usd"]) for x in fin_txs if x.get("amount_usd") is not None
                               and in_range(x.get("date", ""), start_date, end_date)), Decimal(0))
        allocated_scope = sum((D(r["ad_spend_usd"]) for r in in_scope), Decimal(0))
        return {
            "rows": rows,
            "summary": {
                "financial_ad_expense_usd": float(q2(financial_total)),
                "allocated_ppc_spend_usd": float(q2(allocated_scope)),
                "unallocated_ppc_spend_usd": float(q2(financial_total - allocated_scope)),
                "attributed_ad_spend_usd": float(q2(t["spend"])),
                "attributed_ppc_sales_usd": float(q2(t["sales"])),
                "clicks": int(t["clicks"]), "impressions": int(t["impressions"]), "orders": int(t["orders"]),
                "ctr_percent": float(q2(t["clicks"] / t["impressions"] * 100)) if t["impressions"] else None,
                "status_counts": status_counts,
                "status_labels": RECON_LABELS,
                "acos_percent": float(q2(t["spend"] / t["sales"] * 100)) if t["sales"] else None,
                "roas": float(q2(t["sales"] / t["spend"])) if t["spend"] else None,
            },
            "currency": "USD",
        }

    @router.get("/financial-expenses")
    async def financial_expenses(user=Depends(get_current_user), store_id: Optional[str] = None,
                                 marketplace: Optional[str] = None, start_date: Optional[str] = None,
                                 end_date: Optional[str] = None):
        txs = await financial_ad_expenses(db, user["id"], store_id, marketplace)
        keep = ("id", "store_id", "date", "marketplace", "category", "raw_transaction_type", "classification",
                "amount", "currency", "amount_usd", "source", "order_id", "description", "section")
        rows = sorted(({k: t.get(k) for k in keep} for t in txs if in_range(t.get("date", ""), start_date, end_date)),
                      key=lambda r: r["date"] or "", reverse=True)
        return {"rows": rows, "total_usd": float(q2(sum((D(r["amount_usd"]) for r in rows
                                                         if r["amount_usd"] is not None), Decimal(0)))),
                "currency": "USD"}

    @router.get("/reconciliation")
    async def reconciliation(user=Depends(get_current_user), store_id: Optional[str] = None,
                             marketplace: Optional[str] = None):
        ad_by_month = await financial_ad_expense_by_month(db, user["id"], store_id, marketplace)
        records = await db.ppc_attributions.find(scope_query(user["id"], store_id, marketplace), {"_id": 0}).to_list(None)
        attributed = by_month(records, lambda r: r.get("ad_spend_usd"))
        rows = []
        for (mp, month) in sorted(set(ad_by_month) | set(attributed)):
            fin = ad_by_month.get((mp, month), Decimal(0))
            att = attributed.get((mp, month), Decimal(0))
            status = month_status(fin, att)
            rows.append({
                "marketplace": mp, "month": month,
                "financial_ad_expense_usd": float(q2(fin)),
                "attributed_ad_spend_usd": float(q2(att)),
                "unattributed_usd": float(q2(fin - att)),
                "status": status, "status_label": RECON_LABELS[status],
            })
        return {"rows": rows, "currency": "USD"}

    @router.delete("/attributions/{attribution_id}")
    async def delete_attribution(attribution_id: str, user=Depends(get_current_user)):
        res = await db.ppc_attributions.delete_one({"id": attribution_id, "user_id": user["id"]})
        if not res.deleted_count:
            raise HTTPException(404, "PPC kaydı bulunamadı")
        return {"deleted": True, "id": attribution_id}

    return router
