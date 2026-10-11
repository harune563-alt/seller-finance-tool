"""SellerFlash Cost Import — ayrı modül; mevcut Amazon Payments akışına dokunmaz.

SellerFlash verisi finansal işlem OLUŞTURMAZ; eşleşen Amazon siparişinin gelir kaydına
ürün/kargo maliyeti olarak eklenir (manuel maliyet asla ezilmez).
Eşleşme yalnızca Seller Order Id = Amazon Order ID. SellerFlash maliyetleri HER ZAMAN USD'dir
(kur dönüşümü yok). Ürün ve kargo maliyeti bağımsızdır: boş hücre "yeni bilgi yok" demektir.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from pymongo import UpdateOne

from finance import money
from sellerflash import normalize_marketplace, parse_sellerflash

STATUS_NEW = "new"
STATUS_RESTORE = "restore_missing_record"
STATUS_PARTIAL = "partial_cost_completion"
STATUS_UNCHANGED = "existing_unchanged"
STATUS_UPDATED = "updated"
STATUS_MANUAL = "manual_override_preserved"
STATUS_NOT_FOUND = "amazon_order_not_found"
STATUS_NO_COST = "no_cost_data"
STATUS_FBA = "fba_order_fifo_cost"

APPLY_STATUSES = (STATUS_NEW, STATUS_RESTORE, STATUS_PARTIAL, STATUS_UPDATED)
COST_KEYS = (("product_cost", "product"), ("initial_shipment_cost", "shipping"))
REFERENCE_FIELDS = ("seller_refund", "buyer_refund", "seller_order_status", "buyer_order_status",
                    "buyer_order_id", "price", "profit", "profit_rate", "order_date", "order_date_raw",
                    "delivery_end_date", "notes")
COMPARE_FIELDS = ("product_cost", "initial_shipment_cost", *REFERENCE_FIELDS)


class SellerFlashRowOut(BaseModel):
    line: int
    seller_order_id: str
    marketplace: str = ""
    sellerflash_marketplace: str = ""
    amazon_match: bool = False
    order_date: Optional[str] = None
    current_product_cost: Optional[float] = None
    incoming_product_cost: Optional[float] = None
    current_shipping_cost: Optional[float] = None
    incoming_shipping_cost: Optional[float] = None
    product_cost: Optional[float] = None
    initial_shipment_cost: Optional[float] = None
    seller_refund: Optional[float] = None
    buyer_refund: Optional[float] = None
    profit: Optional[float] = None
    profit_rate: Optional[float] = None
    currency: str = "USD"
    cost_currency: str = "USD"
    cost_source: str = ""
    existing_amazon_net_total: Optional[float] = None
    estimated_actual_profit: Optional[float] = None
    match_status: str
    action: str = ""
    note: str = ""


class SellerFlashImportOut(BaseModel):
    total_rows: int
    matched: int = 0
    new: int = 0
    updated: int = 0
    partial_completion: int = 0
    restored: int = 0
    manual_preserved: int = 0
    unchanged: int = 0
    unmatched: int = 0
    conflicts: int = 0
    missing_product_cost: int = 0
    missing_shipping_cost: int = 0
    actionable: int = 0
    rejected_count: int = 0
    issues: List[dict] = Field(default_factory=list)
    preview: List[SellerFlashRowOut] = Field(default_factory=list)
    committed: bool = False
    batch_id: Optional[str] = None
    applied_costs: int = 0


class SellerFlashBatchOut(BaseModel):
    id: str
    file_name: str = ""
    file_type: str = ""
    uploaded_at: str
    marketplaces: List[str] = Field(default_factory=list)
    total_rows: int = 0
    matched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: int = 0
    conflicts: int = 0
    status: str = "completed"


def _has_manual_costs(tx):
    """Kullanıcı manuel maliyet girdiyse SellerFlash asla ezmez (öncelik 1)."""
    if not tx:
        return False
    if tx.get("cost_source") == "manual":
        return True
    if tx.get("cost_source") == "sellerflash":
        return False
    return any(money(tx.get(key, 0)) != 0 for key in ("product_cost", "shipping_cost"))


def _blank(value):
    return value is None or value == ""


def _same(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return money(a) == money(b)
    return a == b


def merge_cost_fields(existing, incoming):
    """Alan-bazında bağımsız birleştirme: boş gelen alan mevcut değeri KORUR; 0 açık sıfırdır.
    Döner: (birleşik değerler, eklenen alanlar, değişen alanlar {alan: [eski, yeni]})."""
    existing = existing or {}
    merged, added, changed = {}, [], {}
    for field in COMPARE_FIELDS:
        cur, new = existing.get(field), incoming.get(field)
        if _blank(new):
            merged[field] = cur
        elif _blank(cur):
            merged[field] = new
            added.append(field)
        else:
            merged[field] = new
            if not _same(cur, new):
                changed[field] = [cur, new]
    return merged, added, changed


def _tx_in_sync(tx, rec_id, merged):
    """İşlem satırı birleşik SellerFlash maliyetlerini zaten taşıyor mu?"""
    if not tx or tx.get("cost_source") != "sellerflash" or tx.get("sellerflash_cost_id") != rec_id:
        return False
    return all(merged.get(src) is None or money(tx.get(dst, 0)) == money(merged[src])
               for src, dst in (("product_cost", "product_cost"), ("initial_shipment_cost", "shipping_cost")))


def sellerflash_router(db, get_current_user, marketplaces):
    router = APIRouter()

    @router.post("/sellerflash/import", response_model=SellerFlashImportOut)
    async def import_sellerflash(
        file: UploadFile = File(...),
        store_id: str = Query(...),
        commit: bool = False,
        user=Depends(get_current_user),
    ):
        store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0})
        if not store:
            raise HTTPException(400, "Mağaza bulunamadı")
        name = (file.filename or "").lower()
        file_type = next((ext for ext in (".csv", ".xlsx", ".xls") if name.endswith(ext)), None)
        if not file_type:
            raise HTTPException(400, "SellerFlash raporu için .csv, .xlsx veya .xls dosyası seçin")
        content = await file.read(10 * 1024 * 1024 + 1)
        await file.close()
        if len(content) > 10 * 1024 * 1024:
            raise HTTPException(413, "Dosya en fazla 10 MB olabilir")
        try:
            rows, issues = parse_sellerflash(content, file.filename or "")
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, f"SellerFlash raporu okunamadı: {exc}")

        scope = {"user_id": user["id"], "store_id": store_id}
        valid_codes = set(marketplaces.keys())
        now = datetime.now(timezone.utc).isoformat()
        counts = {k: 0 for k in ("matched", "new", "updated", "partial_completion", "restored",
                                 "manual_preserved", "unchanged", "unmatched", "conflicts",
                                 "missing_product_cost", "missing_shipping_cost")}
        preview, plan = [], []

        for row in rows:
            oid = row["seller_order_id"]
            sf_mp = normalize_marketplace(row.get("marketplace"), valid_codes) or ""
            # Eşleşme: YALNIZCA Seller Order Id = Amazon Order ID (pazar yeri / SKU engellemez)
            order_txs = await db.transactions.find({**scope, "order_id": oid}, {"_id": 0}).to_list(50)
            incomes = sorted((t for t in order_txs if t.get("type") == "income"), key=lambda t: (t["date"], t["id"]))
            income_tx = incomes[0] if incomes else None
            existing_sf = await db.sellerflash_costs.find_one({**scope, "seller_order_id": oid}, {"_id": 0})
            merged, added, changed = merge_cost_fields(existing_sf, row)
            cost_added = [f for f, _ in COST_KEYS if f in added]
            cost_changed = [f for f, _ in COST_KEYS if f in changed]
            has_cost = merged["product_cost"] is not None or merged["initial_shipment_cost"] is not None
            amazon_mp = (income_tx or (order_txs[0] if order_txs else {})).get("marketplace", "")
            is_fba = any(t.get("fulfillment_type") == "FBA" for t in order_txs)

            if not order_txs:
                status = STATUS_NOT_FOUND
            elif is_fba:
                status = STATUS_FBA
            elif not has_cost:
                status = STATUS_NO_COST
            elif _has_manual_costs(income_tx):
                status = STATUS_MANUAL
            elif not existing_sf:
                status = STATUS_NEW
            elif cost_added:
                status = STATUS_PARTIAL
            elif cost_changed:
                status = STATUS_UPDATED
            elif income_tx and not _tx_in_sync(income_tx, existing_sf["id"], merged):
                status = STATUS_RESTORE
            else:
                status = STATUS_UNCHANGED
            key = {STATUS_NOT_FOUND: "unmatched", STATUS_NEW: "new", STATUS_UPDATED: "updated",
                   STATUS_PARTIAL: "partial_completion", STATUS_RESTORE: "restored",
                   STATUS_MANUAL: "manual_preserved", STATUS_UNCHANGED: "unchanged",
                   STATUS_FBA: "conflicts"}.get(status)
            if key:
                counts[key] += 1
            if order_txs:
                counts["matched"] += 1
            if merged["product_cost"] is None:
                counts["missing_product_cost"] += 1
            if merged["initial_shipment_cost"] is None:
                counts["missing_shipping_cost"] += 1

            manual = status == STATUS_MANUAL
            cur_p = (existing_sf or {}).get("product_cost")
            cur_s = (existing_sf or {}).get("initial_shipment_cost")
            if manual:
                cur_p, cur_s = income_tx.get("product_cost"), income_tx.get("shipping_cost")
            source = "FBA FIFO" if is_fba else "manual" if manual else \
                (income_tx or {}).get("cost_source") or ("sellerflash" if existing_sf else "")
            actions = []
            if status in APPLY_STATUSES:
                for f, label in (("product_cost", "Ürün maliyeti"), ("initial_shipment_cost", "Kargo maliyeti")):
                    if f in added or status == STATUS_NEW and merged[f] is not None:
                        actions.append(f"{label} eklenecek")
                    elif f in changed:
                        actions.append(f"{label} güncellenecek")
                if status == STATUS_RESTORE:
                    actions.append("İşlem maliyeti SellerFlash kaydından geri yüklenecek")
            action = ", ".join(actions) or {
                STATUS_MANUAL: "Manuel maliyet korunur; yalnızca SellerFlash referansı güncellenir",
                STATUS_NOT_FOUND: "Referans olarak saklanır; Amazon siparişi gelince eşleşir",
                STATUS_NO_COST: "Maliyet değeri oluşturulmaz",
                STATUS_FBA: "FBA siparişi — maliyet FBA FIFO lotlarından gelir",
            }.get(status, "Değişiklik yok")

            estimated = net_usd = None
            if order_txs and not is_fba:
                inc = sum(Decimal(str(t.get("amount_usd") or 0)) for t in order_txs if t.get("type") == "income")
                exp = sum(Decimal(str(t.get("amount_usd") or 0)) for t in order_txs if t.get("type") == "expense")
                net_usd = float(money(inc - exp))
                extra = money(((income_tx or {}).get("usd_costs") or {}).get("extra_cost", 0))
                estimated = float(money(Decimal(str(net_usd)) - money(merged["product_cost"] or 0)
                                        - money(merged["initial_shipment_cost"] or 0) - extra))

            plan.append({"row": row, "status": status, "merged": merged, "changed": changed,
                         "income_tx": income_tx, "existing_sf": existing_sf,
                         "mp": amazon_mp or sf_mp, "sf_mp": sf_mp})
            preview.append(SellerFlashRowOut(
                line=row["line"], seller_order_id=oid, marketplace=amazon_mp or sf_mp,
                sellerflash_marketplace=row.get("marketplace", ""), amazon_match=bool(order_txs),
                order_date=merged.get("order_date"),
                current_product_cost=cur_p, incoming_product_cost=row.get("product_cost"),
                current_shipping_cost=cur_s, incoming_shipping_cost=row.get("initial_shipment_cost"),
                product_cost=merged["product_cost"], initial_shipment_cost=merged["initial_shipment_cost"],
                seller_refund=merged.get("seller_refund"), buyer_refund=merged.get("buyer_refund"),
                profit=merged.get("profit"), profit_rate=merged.get("profit_rate"),
                cost_source=source, existing_amazon_net_total=net_usd, estimated_actual_profit=estimated,
                match_status=status, action=action))

        batch_id = None
        applied = 0
        if commit:
            batch_id = str(uuid.uuid4())
            for item in plan:
                row, status, merged, existing_sf = item["row"], item["status"], item["merged"], item["existing_sf"]
                oid = row["seller_order_id"]
                if existing_sf and status in (STATUS_UNCHANGED,) and not item["changed"]:
                    await db.sellerflash_costs.update_one(
                        {"id": existing_sf["id"]}, {"$set": {"last_seen_at": now, "last_import_batch_id": batch_id}})
                    continue
                record = {
                    **scope, "seller_order_id": oid, "marketplace": item["mp"],
                    "sellerflash_marketplace": row.get("marketplace", "") or (existing_sf or {}).get("sellerflash_marketplace", ""),
                    **merged,
                    "currency": "USD",
                    "product_cost_usd": merged["product_cost"], "shipping_cost_usd": merged["initial_shipment_cost"],
                    "fx": None, "fx_cost_date": None,
                    "linked_transaction_id": (item["income_tx"] or {}).get("id") or (existing_sf or {}).get("linked_transaction_id"),
                    "match_status": "unmatched" if status == STATUS_NOT_FOUND else "matched",
                    "source": "sellerflash", "last_seen_at": now, "last_updated_at": now,
                    "last_import_batch_id": batch_id,
                }
                if existing_sf:
                    rec_id = existing_sf["id"]
                    await db.sellerflash_costs.update_one({"id": rec_id}, {"$set": record})
                    if item["changed"]:
                        await db.sellerflash_history.insert_one({
                            "id": str(uuid.uuid4()), **scope, "sellerflash_cost_id": rec_id,
                            "seller_order_id": oid, "marketplace": item["mp"], "changes": item["changed"],
                            "status": status, "detected_at": now, "import_batch_id": batch_id})
                else:
                    rec_id = str(uuid.uuid4())
                    await db.sellerflash_costs.update_one(
                        {**scope, "seller_order_id": oid},
                        {"$set": record, "$setOnInsert": {"id": rec_id, "first_imported_at": now}}, upsert=True)
                    rec_id = (await db.sellerflash_costs.find_one({**scope, "seller_order_id": oid}, {"id": 1}))["id"]
                tx = item["income_tx"]
                # Kâr yalnızca efektif ürün/kargo maliyeti gerçekten değişirse yeniden hesaplanır
                if status in APPLY_STATUSES and tx and not _tx_in_sync(tx, rec_id, merged):
                    await _apply_costs(db, scope, tx, {"product": merged["product_cost"],
                                                       "shipping": merged["initial_shipment_cost"]}, rec_id)
                    applied += 1
            await db.sellerflash_imports.insert_one({
                "id": batch_id, **scope, "file_name": file.filename or "",
                "file_type": file_type.lstrip("."), "uploaded_at": now,
                "marketplaces": sorted({i["mp"] for i in plan if i["mp"]}), "total_rows": len(rows),
                "matched": counts["matched"], "new": counts["new"],
                "updated": counts["updated"] + counts["partial_completion"] + counts["restored"],
                "unchanged": counts["unchanged"], "unmatched": counts["unmatched"],
                "conflicts": counts["conflicts"], "rejected_count": len(issues),
                "applied_costs": applied, "status": "completed",
            })

        actionable = sum(1 for i in plan if i["status"] in APPLY_STATUSES)
        return SellerFlashImportOut(
            total_rows=len(rows), **counts, actionable=actionable,
            rejected_count=len(issues), issues=issues[:100],
            preview=preview[:200], committed=commit, batch_id=batch_id, applied_costs=applied)

    @router.get("/sellerflash/history", response_model=List[SellerFlashBatchOut])
    async def sellerflash_history(store_id: Optional[str] = None, limit: int = 50,
                                  user=Depends(get_current_user)):
        """Audit-only SellerFlash import history; finansal toplamları etkilemez."""
        q = {"user_id": user["id"]}
        if store_id:
            q["store_id"] = store_id
        docs = await db.sellerflash_imports.find(q, {"_id": 0}).sort("uploaded_at", -1).to_list(min(max(limit, 1), 200))
        return [SellerFlashBatchOut(**d) for d in docs]

    @router.get("/sellerflash/costs")
    async def sellerflash_cost_for_order(store_id: str, order_id: str, marketplace: Optional[str] = None,
                                         user=Depends(get_current_user)):
        # Order-ID-only: pazar yeri yalnızca görüntü bilgisidir
        doc = await db.sellerflash_costs.find_one(
            {"user_id": user["id"], "store_id": store_id, "seller_order_id": order_id}, {"_id": 0})
        return {"found": bool(doc), "record": doc}

    @router.get("/sellerflash/unmatched")
    async def sellerflash_unmatched(store_id: Optional[str] = None, user=Depends(get_current_user)):
        q = {"user_id": user["id"], "match_status": "unmatched"}
        if store_id:
            q["store_id"] = store_id
        docs = await db.sellerflash_costs.find(q, {"_id": 0}).sort("last_seen_at", -1).to_list(500)
        return {"items": docs, "total": len(docs)}

    return router


async def _apply_costs(db, scope, tx, usd, rec_id):
    """SellerFlash USD maliyetlerini siparişin gelir kaydına uygular (ayrı işlem oluşturmaz).
    Yalnızca değeri olan alan yazılır; eksik alan mevcut değeri korur."""
    if tx.get("fulfillment_type") == "FBA":
        return  # FBA maliyeti yalnızca FBA FIFO lotlarından gelir
    usd_costs = dict(tx.get("usd_costs") or {})
    for key in ("product_cost", "shipping_cost", "extra_cost",
                "product_cost_recovery", "shipping_cost_recovery"):
        usd_costs.setdefault(key, 0)
    sets = {"cost_currency": "USD", "cost_source": "sellerflash", "sellerflash_cost_id": rec_id}
    if usd.get("product") is not None:
        sets["product_cost"] = float(money(usd["product"]))
        usd_costs["product_cost"] = float(money(usd["product"]))
    if usd.get("shipping") is not None:
        sets["shipping_cost"] = float(money(usd["shipping"]))
        usd_costs["shipping_cost"] = float(money(usd["shipping"]))
    sets["usd_costs"] = usd_costs
    await db.transactions.update_one({"id": tx["id"], **scope}, {"$set": sets})


async def initialize_sellerflash_indexes(db):
    await db.sellerflash_costs.create_index(
        [("user_id", 1), ("store_id", 1), ("marketplace", 1), ("seller_order_id", 1)], unique=True)
    await db.sellerflash_costs.create_index([("user_id", 1), ("store_id", 1), ("seller_order_id", 1)])
    await db.sellerflash_costs.create_index([("user_id", 1), ("match_status", 1)])
    await db.sellerflash_history.create_index([("user_id", 1), ("seller_order_id", 1)])
    await db.sellerflash_imports.create_index([("user_id", 1), ("uploaded_at", -1)])


async def backfill_amazon_orders(db):
    """Mevcut (Faz A öncesi) Amazon işlemlerinden canonical sipariş kaydı üretir."""
    pipeline = [
        {"$match": {"order_id": {"$nin": ["", None]}, "marketplace": {"$nin": ["", None]}}},
        {"$group": {"_id": {"u": "$user_id", "s": "$store_id", "m": "$marketplace", "o": "$order_id"},
                    "first": {"$min": "$created_at"}}},
    ]
    rows = await db.transactions.aggregate(pipeline).to_list(None)
    if not rows:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    ops = [UpdateOne(
        {"user_id": r["_id"]["u"], "store_id": r["_id"]["s"],
         "marketplace": r["_id"]["m"], "order_id": r["_id"]["o"]},
        {"$setOnInsert": {"id": str(uuid.uuid4()), "first_seen_at": r.get("first") or now,
                          "created_at": r.get("first") or now},
         "$set": {"last_seen_at": now}},
        upsert=True) for r in rows]
    for start in range(0, len(ops), 500):
        await db.amazon_orders.bulk_write(ops[start:start + 500], ordered=False)
    return len(ops)
