"""Detaylı Hareket Raporu: row-level, filterable view of Gelir/Gider records.

Read-only. Profit per row and filtered totals come from the SAME helpers used by
Kar/Zarar (usd_ledger.effective_usd_costs + finance.summarize): FBA rows carry
realized FIFO cost on the carrier row only; remaining FBA inventory is never a cost.
"""
import asyncio
import csv
import io
from datetime import date
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response

from finance import summarize, money
from usd_ledger import enrich_records, effective_usd_costs

SOURCE_LABELS = {
    "amazon_payments": "Amazon Payments", "sellerflash": "SellerFlash", "manual": "Manuel",
    "fba_fifo": "FBA FIFO", "extra_cost": "Ekstra Maliyet", "csv_import": "CSV İçe Aktarma",
    "ppc": "PPC", "current_account": "Cari Hesap",
}
COST_SOURCE_LABELS = {"sellerflash": "SellerFlash", "manual": "Manuel", "fba_fifo": "FBA FIFO", "none": "Maliyet yok"}
FULFILLMENTS = ("FBA", "FBM", "MIXED", "UNKNOWN")
SORT_KEYS = {
    "date": lambda r: r["date"], "amount": lambda r: r["amount_usd"], "cost": lambda r: r["total_cost"],
    "net_profit": lambda r: r["net_profit"], "margin": lambda r: r["margin"],
    "store": lambda r: (r["store_name"] or "").lower(), "marketplace": lambda r: r["marketplace"] or "",
}
MAX_ROWS = 50000
PAGE_SIZES = (25, 50, 100)


def _record_source(tx):
    raw = tx.get("source") or "manual"
    return {"amazon_payments_csv": "amazon_payments"}.get(raw, raw if raw in SOURCE_LABELS else "manual")


def _fifo_carrier(tx):
    fifo = tx.get("fba_fifo") or {}
    return tx.get("fulfillment_type") == "FBA" and bool(fifo) and fifo.get("carrier_tx_id") == tx.get("id")


def _cost_source(tx):
    if _fifo_carrier(tx):
        return "fba_fifo"
    if tx.get("fulfillment_type") != "FBA" and (money(tx.get("product_cost")) or money(tx.get("shipping_cost"))):
        return tx.get("cost_source") if tx.get("cost_source") in COST_SOURCE_LABELS else "manual"
    return "none"


def _f(value):
    return None if value is None else float(money(value))


def _qty(value):
    try:
        return int(float(str(value or 0).replace(",", ".")))
    except ValueError:
        return 0


def build_row(tx, store_name, items):
    """One report row. All USD numbers derive from finance.summarize on this single record."""
    income = tx["type"] == "income"
    fba = tx.get("fulfillment_type") == "FBA"
    ready = tx.get("fx_status") != "unavailable" and tx.get("amount_usd") is not None
    item_skus = sorted({i.get("sku") for i in items if i.get("sku")})
    asins = sorted({i.get("asin") for i in items if i.get("asin")})
    names = list(dict.fromkeys(i.get("product_name") for i in items if i.get("product_name")))
    item_ids = list(dict.fromkeys([*(tx.get("amazon_order_item_ids") or []), *(i.get("order_item_id") for i in items if i.get("order_item_id"))]))
    quantity = tx.get("quantity") or (str(sum(_qty(i.get("quantity")) for i in items)) if items else "")
    source = _record_source(tx)
    cost_source = _cost_source(tx)
    tags = {source, cost_source} - {"none"}
    if tx.get("section") == "ppc":
        tags.add("ppc")
    if money(tx.get("extra_cost")):
        tags.add("extra_cost")
    row = {
        "id": tx["id"], "date": tx["date"], "store_id": tx["store_id"], "store_name": store_name,
        "marketplace": tx.get("marketplace") or "", "type": tx["type"], "category": tx.get("category") or "",
        "source": source, "source_label": SOURCE_LABELS.get(source, source),
        "cost_source": cost_source, "cost_source_label": COST_SOURCE_LABELS[cost_source],
        "source_tags": sorted(tags), "fulfillment": tx.get("fulfillment_type") or "UNKNOWN",
        "order_id": (tx.get("order_id") or "").strip(), "order_item_ids": item_ids,
        "sku": tx.get("sku") or ", ".join(item_skus), "skus": sorted({*item_skus, *([tx["sku"]] if tx.get("sku") else [])}),
        "asin": ", ".join(asins), "asins": asins, "product_name": " | ".join(names),
        "quantity": quantity, "currency": tx.get("currency") or "", "original_amount": _f(tx.get("amount")),
        "description": tx.get("description") or "", "fx_status": "ready" if ready else "unavailable",
        "amount_usd": None, "product_cost": None, "shipping_cost": None, "fba_product_cost": None,
        "fba_inbound_cost": None, "extra_cost": None, "total_cost": None, "net_profit": None, "margin": None,
        "profitability": None,
    }
    if not ready:
        return row, None
    costs = effective_usd_costs(tx)
    converted = {**tx, "amount": tx["amount_usd"], **costs}
    s = summarize([converted])
    own_expense = money(tx["amount_usd"]) if tx["type"] == "expense" else Decimal(0)
    if income:  # summarize counts attached costs on income rows only
        row["product_cost"] = None if fba else _f(costs.get("product_cost", 0))
        row["shipping_cost"] = None if fba else _f(costs.get("shipping_cost", 0))
        row["fba_product_cost"] = _f(costs.get("product_cost", 0)) if fba else None
        row["fba_inbound_cost"] = _f(costs.get("shipping_cost", 0)) if fba else None
        row["extra_cost"] = _f(costs.get("extra_cost", 0))
    net = money(s["net_profit"])
    row.update(amount_usd=_f(tx["amount_usd"]), total_cost=float(money(s["expenses"]) - own_expense),
               net_profit=float(net), margin=s["margin"] if s["revenue"] else None,
               profitability="profitable" if net > 0 else "loss" if net < 0 else "break_even")
    return row, converted


def filtered_summary(rows, converted):
    ready = [c for c in converted if c is not None]
    incomplete = sum(1 for r in rows if r["fx_status"] != "ready")
    base = {"record_count": len(rows), "incomplete_count": incomplete, "currency": "USD"}
    if incomplete:
        return {**base, **{k: None for k in ("total_income", "total_expense", "total_effective_cost", "net_profit", "margin", "fba_profit", "fbm_profit")}}
    s = summarize(ready)
    total_expense = sum(money(c["amount"]) for c in ready if c["type"] == "expense")
    by = lambda kind: summarize([c for c in ready if c.get("fulfillment_type") == kind])["net_profit"]
    return {**base, "total_income": s["revenue"], "total_expense": float(total_expense),
            "total_effective_cost": float(money(s["expenses"]) - total_expense), "net_profit": s["net_profit"],
            "margin": s["margin"] if s["revenue"] else None, "fba_profit": by("FBA"), "fbm_profit": by("FBM")}


def _contains(needle, *haystacks):
    needle = (needle or "").strip().lower()
    return not needle or any(needle in (h or "").lower() for h in haystacks)


class Filters:
    def __init__(self, start_date: date, end_date: date, store_id: Optional[str] = None, marketplace: Optional[str] = None,
                 currency: Optional[str] = None, direction: str = Query("ALL", pattern="^(ALL|income|expense)$"),
                 category: Optional[str] = None, fulfillment: str = Query("ALL", pattern="^(ALL|FBA|FBM|MIXED|UNKNOWN)$"),
                 source: Optional[str] = None, cost_source: Optional[str] = None, order_id: Optional[str] = None,
                 sku: Optional[str] = None, asin: Optional[str] = None, product_name: Optional[str] = None,
                 order_item_id: Optional[str] = None, min_amount: Optional[float] = None, max_amount: Optional[float] = None,
                 profitability: str = Query("ALL", pattern="^(ALL|profitable|loss|break_even)$"), q: Optional[str] = None,
                 sort: str = Query("date", pattern="^(date|amount|cost|net_profit|margin|store|marketplace)$"),
                 order: str = Query("desc", pattern="^(asc|desc)$")):
        if start_date > end_date:
            raise HTTPException(422, "Başlangıç tarihi bitişten sonra olamaz")
        self.__dict__.update({k: v for k, v in locals().items() if k != "self"})


def transaction_report_router(db, get_user):
    router = APIRouter(tags=["reports"])

    async def run(user_id, f: Filters):
        stores = {s["id"]: s for s in await db.stores.find({"user_id": user_id}, {"_id": 0, "id": 1, "name": 1}).to_list(None)}
        query = {"user_id": user_id, "type": {"$in": ["income", "expense"]},
                 "date": {"$gte": f.start_date.isoformat(), "$lte": f.end_date.isoformat()}}
        if f.store_id and f.store_id != "ALL":
            if f.store_id not in stores:
                raise HTTPException(404, "Mağaza bulunamadı")
            query["store_id"] = f.store_id
        if f.marketplace and f.marketplace != "ALL":
            query["marketplace"] = f.marketplace
        facets = {"categories": sorted(c for c in await db.transactions.distinct("category", query) if c),
                  "currencies": sorted(c for c in await db.transactions.distinct("currency", query) if c),
                  "sources": [{"value": k, "label": v} for k, v in SOURCE_LABELS.items()],
                  "cost_sources": [{"value": k, "label": v} for k, v in COST_SOURCE_LABELS.items()]}
        if f.currency and f.currency != "ALL":
            query["currency"] = f.currency
        if f.direction != "ALL":
            query["type"] = f.direction
        if f.category and f.category != "ALL":
            query["category"] = f.category
        if f.fulfillment == "UNKNOWN":
            query["fulfillment_type"] = {"$in": ["UNKNOWN", None, ""]}
        elif f.fulfillment != "ALL":
            query["fulfillment_type"] = f.fulfillment
        if await db.transactions.count_documents(query) > MAX_ROWS:
            raise HTTPException(413, "Filtreyi daraltın; en fazla 50.000 hareket raporlanabilir")
        docs = await enrich_records(db, await db.transactions.find(query, {"_id": 0}).to_list(None))
        order_ids = sorted({(d.get("order_id") or "").strip() for d in docs} - {""})
        items = {}
        if order_ids:
            async for it in db.amazon_order_items.find({"user_id": user_id, "amazon_order_id": {"$in": order_ids}}, {"_id": 0}):
                items.setdefault((it.get("store_id"), it["amazon_order_id"]), []).append(it)
        rows, converted = [], []
        lo = None if f.min_amount is None else Decimal(str(f.min_amount))
        hi = None if f.max_amount is None else Decimal(str(f.max_amount))
        for tx in docs:
            oid = (tx.get("order_id") or "").strip()
            row, conv = build_row(tx, stores.get(tx["store_id"], {}).get("name", "—"),
                                  items.get((tx["store_id"], oid), []) if oid else [])
            if f.source and f.source != "ALL" and f.source not in row["source_tags"]:
                continue
            if f.cost_source and f.cost_source != "ALL" and row["cost_source"] != f.cost_source:
                continue
            if not (_contains(f.order_id, row["order_id"]) and _contains(f.sku, *row["skus"])
                    and _contains(f.asin, *row["asins"]) and _contains(f.product_name, row["product_name"])
                    and _contains(f.order_item_id, *row["order_item_ids"])):
                continue
            if not _contains(f.q, row["order_id"], *row["skus"], *row["asins"], row["product_name"], row["description"], row["category"]):
                continue
            if (lo is not None or hi is not None):
                if row["amount_usd"] is None:
                    continue
                if (lo is not None and Decimal(str(row["amount_usd"])) < lo) or (hi is not None and Decimal(str(row["amount_usd"])) > hi):
                    continue
            if f.profitability != "ALL" and row["profitability"] != f.profitability:
                continue
            rows.append(row)
            converted.append(conv)
        key = SORT_KEYS[f.sort]
        present = [r for r in rows if key(r) is not None]
        missing = [r for r in rows if key(r) is None]
        present.sort(key=lambda r: (key(r), r["date"], r["id"]), reverse=f.order == "desc")
        return present + missing, filtered_summary(rows, converted), facets

    @router.get("/reports/transactions")
    async def transactions_report(f: Filters = Depends(), page: int = Query(1, ge=1), page_size: int = Query(25),
                                  user=Depends(get_user)):
        if page_size not in PAGE_SIZES:
            raise HTTPException(422, "Sayfa boyutu 25, 50 veya 100 olmalı")
        rows, summary, facets = await run(user["id"], f)
        pages = max(1, -(-len(rows) // page_size))
        page = min(page, pages)
        return {"items": rows[(page - 1) * page_size: page * page_size], "total": len(rows), "page": page,
                "page_size": page_size, "total_pages": pages, "summary": summary, "facets": facets}

    @router.get("/reports/transactions/export")
    async def transactions_export(f: Filters = Depends(), format: str = Query("csv", pattern="^(csv|xlsx)$"),
                                  user=Depends(get_user)):
        rows, summary, _ = await run(user["id"], f)
        name = f"detayli-hareket-{f.start_date}-{f.end_date}.{format}"
        if format == "csv":
            content = await asyncio.to_thread(build_csv, rows)
            return Response(content, media_type="text/csv; charset=utf-8",
                            headers={"Content-Disposition": f'attachment; filename="{name}"'})
        content = await asyncio.to_thread(build_xlsx, rows, summary, f)
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                        headers={"Content-Disposition": f'attachment; filename="{name}"'})

    @router.get("/reports/transactions/{tx_id}/detail")
    async def transaction_detail(tx_id: str, user=Depends(get_user)):
        tx = await db.transactions.find_one({"id": tx_id, "user_id": user["id"], "type": {"$in": ["income", "expense"]}}, {"_id": 0, "user_id": 0})
        if not tx:
            raise HTTPException(404, "Hareket bulunamadı")
        store = await db.stores.find_one({"id": tx["store_id"], "user_id": user["id"]}, {"_id": 0, "name": 1}) or {}
        oid = (tx.get("order_id") or "").strip()
        items = await db.amazon_order_items.find({"user_id": user["id"], "store_id": tx["store_id"], "amazon_order_id": oid},
                                                 {"_id": 0, "user_id": 0}).to_list(200) if oid else []
        enriched = (await enrich_records(db, [{**tx, "user_id": user["id"]}], persist=False))[0]
        row, _ = build_row(enriched, store.get("name", "—"), items)
        return {"row": row, "record": tx, "order_items": items}

    return router


EXPORT_COLUMNS = [
    ("Tarih", "date"), ("Mağaza", "store_name"), ("Pazar Yeri", "marketplace"), ("Tür", "type_label"),
    ("Kategori", "category"), ("Kaynak", "source_label"), ("Maliyet Kaynağı", "cost_source_label"),
    ("Fulfillment", "fulfillment"), ("Order ID", "order_id"), ("Order Item ID", "order_item_id"), ("SKU", "sku"),
    ("ASIN", "asin"), ("Ürün Adı", "product_name"), ("Adet", "quantity"), ("Döviz", "currency"),
    ("Orijinal Tutar", "original_amount"), ("USD Tutar", "amount_usd"), ("Ürün Maliyeti USD", "product_cost"),
    ("Kargo Maliyeti USD", "shipping_cost"), ("FBA Ürün Maliyeti USD", "fba_product_cost"),
    ("FBA Inbound Maliyeti USD", "fba_inbound_cost"), ("Ekstra Maliyet USD", "extra_cost"),
    ("Toplam Efektif Maliyet USD", "total_cost"), ("Net Kâr USD", "net_profit"), ("Kâr Marjı %", "margin"),
    ("Açıklama", "description"), ("Kayıt ID", "id"), ("Kaynak Etiketleri", "source_tags_text"),
]


def _export_values(row):
    flat = {**row, "type_label": "Gelir" if row["type"] == "income" else "Gider",
            "order_item_id": ", ".join(row["order_item_ids"]), "source_tags_text": ", ".join(row["source_tags"])}
    return [flat.get(key) for _, key in EXPORT_COLUMNS]


def _safe(value):
    if isinstance(value, str) and value.lstrip().startswith(("=", "+", "-", "@")):
        return "'" + value
    return value


def build_csv(rows):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow([h for h, _ in EXPORT_COLUMNS])
    for row in rows:
        writer.writerow(["" if v is None else _safe(v) for v in _export_values(row)])
    return ("\ufeff" + out.getvalue()).encode("utf-8")


def build_xlsx(rows, summary, f):
    from openpyxl import Workbook
    from report_workbook import sheet
    wb = Workbook()
    wb.remove(wb.active)
    sheet(wb, "Detaylı Hareketler", [h for h, _ in EXPORT_COLUMNS], [_export_values(r) for r in rows])
    labels = [("Kayıt Sayısı", "record_count"), ("Toplam Gelir USD", "total_income"), ("Toplam Gider USD", "total_expense"),
              ("Toplam Efektif Maliyet USD", "total_effective_cost"), ("Net Kâr USD", "net_profit"), ("Kâr Marjı %", "margin"),
              ("FBA Kâr USD", "fba_profit"), ("FBM Kâr USD", "fbm_profit"), ("Eksik Kur Kayıt", "incomplete_count")]
    active = [(k, v) for k, v in vars(f).items() if v not in (None, "", "ALL") and k not in ("sort", "order")]
    sheet(wb, "Filtre Özeti", ["Alan", "Değer"], [[label, summary.get(key)] for label, key in labels] +
          [["Filtre · " + k, str(v)] for k, v in active])
    buf = io.BytesIO()
    wb.save(buf)
    return buf.getvalue()
