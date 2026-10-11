"""Dashboard insights: store-scoped FBA/FBM split, inventory value, ASIN highlights, low stock.
All money comes from the shared summary_usd / FBA report services (no new accounting logic)."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from fba import allocate_store, asin_report, inventory_report, order_rows
from fba_stock import HEALTHY, stock_status
from ledger_search import order_key
from usd_ledger import enrich_records, summary_usd

KEYS = ("revenue", "expenses", "net_profit", "margin")


def dashboard_router(db, get_current_user):
    router = APIRouter(prefix="/dashboard", tags=["dashboard"])

    @router.get("/insights")
    async def insights(store_id: Optional[str] = None, marketplace: Optional[str] = None,
                       start_date: Optional[str] = None, end_date: Optional[str] = None, user=Depends(get_current_user)):
        stores = await db.stores.find({"user_id": user["id"]}, {"_id": 0}).to_list(None)
        if store_id and store_id != "ALL":
            stores = [s for s in stores if s["id"] == store_id]
            if not stores:
                raise HTTPException(404, "Mağaza bulunamadı")
        ids = [s["id"] for s in stores]
        q = {"user_id": user["id"], "store_id": {"$in": ids}, "type": {"$in": ["income", "expense"]}}
        if marketplace and marketplace != "ALL":
            q["marketplace"] = marketplace
        if start_date or end_date:
            q["date"] = {**({"$gte": start_date} if start_date else {}), **({"$lte": end_date} if end_date else {})}
        txs = await enrich_records(db, await db.transactions.find(q, {"_id": 0}).to_list(None))

        def part(rows):
            s = summary_usd(rows)
            return {**{k: s[k] for k in KEYS}, "orders": len({order_key(t) for t in rows})}

        fba_rows, fba_inventory, stock = [], 0.0, []
        for s in stores:
            result = await allocate_store(db, user["id"], s["id"])
            orders = [o for o in result["orders"]
                      if (not start_date or o["date"] >= start_date) and (not end_date or o["date"] <= end_date)
                      and (not marketplace or marketplace == "ALL" or o["marketplace"] == marketplace)]
            fba_rows += order_rows(orders, result["allocations"])
            fba_inventory += (await inventory_report(db, user["id"], s["id"]))["totals"]["inventory_value_usd"]
            stock += [{**r, "store_id": s["id"], "store_name": s["name"]}
                      for r in await stock_status(db, user["id"], s["id"]) if r["stock_status"] != HEALTHY]
        asins = asin_report(fba_rows)
        return {
            "fba": part([t for t in txs if t.get("fulfillment_type") == "FBA"]),
            "fbm": part([t for t in txs if t.get("fulfillment_type") == "FBM"]),
            "unclassified": part([t for t in txs if t.get("fulfillment_type") not in ("FBA", "FBM")]),
            "order_count": len({order_key(t) for t in txs if (t.get("order_id") or "").strip()}),
            "fba_inventory_value_usd": round(fba_inventory, 2),
            "top_asins": sorted(asins, key=lambda a: -a["net_profit_usd"])[:5],
            "bottom_asins": sorted(asins, key=lambda a: a["net_profit_usd"])[:5],
            "low_stock": stock[:20],
            "store_scope": store_id or "ALL",
        }

    return router
