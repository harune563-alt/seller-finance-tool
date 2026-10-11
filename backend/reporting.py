"""All-store date-scoped USD profitability and detailed order reports."""
from datetime import date
from collections import defaultdict
from typing import Optional
from pydantic import BaseModel, Field
from fastapi import APIRouter, Depends, HTTPException, Query, Response
from usd_ledger import enrich_records, summary_usd
from ledger_search import order_key
import asyncio

class StoreMetric(BaseModel):
    store_id: str
    store_name: str
    revenue: Optional[float]
    expenses: Optional[float]
    net_profit: Optional[float]
    margin: Optional[float]
    incomplete_count: int

class ReportSummary(BaseModel):
    revenue: Optional[float]
    expenses: Optional[float]
    net_profit: Optional[float]
    margin: Optional[float]
    currency: str = "USD"
    source_currency: str
    available_currencies: list[str]
    incomplete_count: int
    fx_errors: list[str]
    by_category: list[dict]
    by_marketplace: list[dict]
    by_store: list[StoreMetric]
    order_count: int
    transaction_count: int
    start_date: str
    end_date: str

class OrderMetric(BaseModel):
    store_id: str
    store_name: str
    marketplace: str
    currency: str
    order_id: str
    first_date: str
    last_date: str
    records: int
    revenue: Optional[float]
    expenses: Optional[float]
    net_profit: Optional[float]
    margin: Optional[float]

class ReportOrders(BaseModel):
    items: list[OrderMetric]
    total: int
    page: int
    total_pages: int

async def report_data(db, user_id, start, end, store_id=None, marketplace=None, currency=None):
    if start > end: raise HTTPException(422, "Başlangıç tarihi bitişten sonra olamaz")
    stores = {s["id"]: s for s in await db.stores.find({"user_id": user_id}, {"_id": 0}).to_list(None)}
    query = {"user_id": user_id, "date": {"$gte": start.isoformat(), "$lte": end.isoformat()}}
    if store_id and store_id != "ALL":
        if store_id not in stores: raise HTTPException(404, "Mağaza bulunamadı")
        query["store_id"] = store_id
        stores = {store_id: stores[store_id]}
    if marketplace and marketplace != "ALL": query["marketplace"] = marketplace
    available = sorted(await db.transactions.distinct("currency", query))
    if currency and currency != "ALL": query["currency"] = currency
    rows = await db.transactions.find(query, {"_id": 0}).sort([("date", 1), ("id", 1)]).to_list(None)
    rows = await enrich_records(db, rows)
    by_store = []
    grouped = defaultdict(list)
    for row in rows: grouped[row["store_id"]].append(row)
    for sid, store in stores.items():
        values = summary_usd(grouped[sid])
        by_store.append({"store_id": sid, "store_name": store["name"], **values})
    result = summary_usd(rows)
    result.update(currency="USD", source_currency=currency or "ALL", available_currencies=available, by_store=by_store,
                  start_date=start.isoformat(), end_date=end.isoformat(),
                  order_count=len({order_key(r) for r in rows if r["type"] != "payout"}))
    return result, rows, stores

def order_metrics(rows, stores):
    grouped = defaultdict(list)
    for row in rows:
        if row["type"] != "payout": grouped[order_key(row)].append(row)
    result = []
    for items in grouped.values():
        first = items[0]
        summary = summary_usd(items)
        result.append({"store_id": first["store_id"], "store_name": stores.get(first["store_id"], {}).get("name", "—"),
                       "marketplace": first["marketplace"], "currency": first["currency"], "order_id": (first.get("order_id") or "").strip(),
                       "first_date": min(r["date"] for r in items), "last_date": max(r["date"] for r in items), "records": len(items),
                       **{key: summary[key] for key in ("revenue", "expenses", "net_profit", "margin")}})
    return sorted(result, key=lambda r: (r["last_date"], r["order_id"]), reverse=True)

def report_router(db, get_user):
    router = APIRouter(tags=["reports"])
    @router.get("/portfolio/summary", response_model=ReportSummary)
    async def portfolio(start_date: date, end_date: date, store_id: Optional[str] = None, marketplace: Optional[str] = None, currency: Optional[str] = None, user=Depends(get_user)):
        summary, _, _ = await report_data(db, user["id"], start_date, end_date, store_id, marketplace, currency)
        return ReportSummary(**summary)

    @router.get("/reports/orders", response_model=ReportOrders)
    async def orders(start_date: date, end_date: date, store_id: Optional[str] = None, marketplace: Optional[str] = None, currency: Optional[str] = None, page: int = Query(1, ge=1), user=Depends(get_user)):
        _, rows, stores = await report_data(db, user["id"], start_date, end_date, store_id, marketplace, currency)
        metrics = order_metrics(rows, stores)
        pages = max(1, (len(metrics) + 19) // 20)
        page = min(page, pages)
        return ReportOrders(items=[OrderMetric(**r) for r in metrics[(page - 1) * 20:page * 20]], total=len(metrics), page=page, total_pages=pages)

    @router.get("/reports/excel")
    async def excel(start_date: date, end_date: date, store_id: Optional[str] = None, marketplace: Optional[str] = None, currency: Optional[str] = None, user=Depends(get_user)):
        from report_workbook import build_workbook
        summary, rows, stores = await report_data(db, user["id"], start_date, end_date, store_id, marketplace, currency)
        if summary["incomplete_count"]: raise HTTPException(422, "Eksik kur nedeniyle rapor indirilemiyor; önce kur verisini tamamlayın")
        if len(rows) > 50000: raise HTTPException(413, "Excel için tarih aralığını daraltın; en fazla 50.000 hareket")
        content = await asyncio.to_thread(build_workbook, summary, rows, stores, order_metrics(rows, stores))
        return Response(content, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", headers={"Content-Disposition": f'attachment; filename="kar-zarar-{start_date}-{end_date}.xlsx"'})
    return router