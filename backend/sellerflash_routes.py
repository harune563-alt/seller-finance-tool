"""SellerFlash Cost Import — ayrı modül; mevcut Amazon Payments akışına dokunmaz.

SellerFlash verisi finansal işlem OLUŞTURMAZ; eşleşen canonical Amazon siparişinin
gelir kaydına ürün/kargo maliyeti olarak eklenir (kullanıcı manuel maliyeti varsa
asla ezilmez) ve tüm SellerFlash alanları ayrı, denetlenebilir bir kayıtta saklanır.
"""
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, Field
from pymongo import UpdateOne

from finance import money
from fx_service import FxError, get_rate
from sellerflash import MAX_ROWS, normalize_marketplace, parse_sellerflash

STATUS_MATCHED = "matched"
STATUS_NOT_FOUND = "amazon_order_not_found"
STATUS_MP_MISMATCH = "marketplace_mismatch"
STATUS_NO_PRODUCT_COST = "missing_product_cost"
STATUS_NO_SHIPPING_COST = "missing_shipping_cost"
STATUS_ALREADY_IMPORTED = "already_imported"
STATUS_WILL_UPDATE = "existing_record_will_be_updated"
STATUS_CONFLICT = "conflict"

COMPARE_FIELDS = ("product_cost", "initial_shipment_cost", "seller_refund", "buyer_refund",
                  "seller_order_status", "buyer_order_status", "price", "profit",
                  "profit_rate", "delivery_end_date", "notes")


class SellerFlashRowOut(BaseModel):
    line: int
    seller_order_id: str
    marketplace: str = ""
    order_date: Optional[str] = None
    product_cost: Optional[float] = None
    initial_shipment_cost: Optional[float] = None
    seller_refund: Optional[float] = None
    buyer_refund: Optional[float] = None
    profit: Optional[float] = None
    profit_rate: Optional[float] = None
    currency: str = ""
    existing_amazon_net_total: Optional[float] = None
    estimated_actual_profit: Optional[float] = None
    match_status: str
    note: str = ""


class SellerFlashImportOut(BaseModel):
    total_rows: int
    matched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: int = 0
    conflicts: int = 0
    missing_product_cost: int = 0
    missing_shipping_cost: int = 0
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


def _diff_fields(existing, incoming):
    changes = {}
    for field in COMPARE_FIELDS:
        old = existing.get(field)
        new = incoming.get(field)
        old_n = money(old) if isinstance(old, (int, float)) and old is not None else old
        new_n = money(new) if isinstance(new, (int, float)) and new is not None else new
        if (old_n is None or old_n == "") and (new_n is None or new_n == ""):
            continue
        if old_n != new_n:
            changes[field] = [None if old is None else old, None if new is None else new]
    return changes


def sellerflash_router(db, get_current_user, marketplaces):
    router = APIRouter()

    async def _convert(currency, date_iso, amount):
        """Bir kerelik kur dönüşümü; tarihsel değerler sonradan asla değişmez."""
        if amount is None:
            return None, None
        if currency == "USD":
            return float(money(amount)), {"base": currency, "quote": "USD", "rate": "1",
                                          "requested_date": date_iso, "rate_date": date_iso,
                                          "source": "identity"}
        quote = await get_rate(db, currency, date_iso)
        converted = money(Decimal(str(amount)) * Decimal(str(quote["rate"])))
        return float(converted), quote

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
        preview = []
        counts = {"matched": 0, "new": 0, "updated": 0, "unchanged": 0,
                  "unmatched": 0, "conflicts": 0, "missing_product_cost": 0,
                  "missing_shipping_cost": 0}
        plan = []

        for row in rows:
            note = ""
            mp = normalize_marketplace(row.get("marketplace"), valid_codes)
            status = None
            income_tx = None
            order_txs = []
            order_net_usd = None
            estimated = None
            existing_sf = None

            if not mp:
                status = STATUS_NOT_FOUND
                note = f"Pazar yeri tanınamadı: {row.get('marketplace') or 'boş'}"
                counts["unmatched"] += 1
            elif mp not in (store.get("marketplaces") or []):
                status = STATUS_NOT_FOUND
                note = "Bu pazar yeri mağazada aktif değil"
                counts["unmatched"] += 1
            else:
                order_txs = await db.transactions.find(
                    {**scope, "marketplace": mp, "order_id": row["seller_order_id"]},
                    {"_id": 0}).to_list(50)
                income_tx = next((t for t in order_txs if t.get("type") == "income"), None)
                existing_sf = await db.sellerflash_costs.find_one(
                    {**scope, "seller_order_id": row["seller_order_id"]}, {"_id": 0})
                if existing_sf and existing_sf.get("marketplace") != mp:
                    status = STATUS_MP_MISMATCH
                    note = f"Kayıt {existing_sf.get('marketplace')} pazarı ile eşleşmiş"
                    counts["conflicts"] += 1
                elif existing_sf:
                    changes = _diff_fields(existing_sf, row)
                    status = STATUS_WILL_UPDATE if changes else STATUS_ALREADY_IMPORTED
                    counts["updated" if changes else "unchanged"] += 1
                    row["_changes"] = changes
                elif not order_txs:
                    status = STATUS_NOT_FOUND
                    counts["unmatched"] += 1
                elif row.get("product_cost") is None:
                    status = STATUS_NO_PRODUCT_COST
                    counts["missing_product_cost"] += 1
                elif row.get("initial_shipment_cost") is None:
                    status = STATUS_NO_SHIPPING_COST
                    counts["missing_shipping_cost"] += 1
                elif _has_manual_costs(income_tx):
                    status = STATUS_CONFLICT
                    note = "Siparişte manuel girilmiş maliyet var; SellerFlash ezmez"
                    counts["conflicts"] += 1
                else:
                    status = STATUS_MATCHED
                    counts["matched"] += 1
                    counts["new"] += 1

            currency = marketplaces[mp]["currency"] if mp else ""
            if mp and status in (STATUS_MATCHED, STATUS_WILL_UPDATE, STATUS_NO_PRODUCT_COST,
                                 STATUS_NO_SHIPPING_COST, STATUS_CONFLICT) and order_txs:
                income_usd = sum(Decimal(str(t.get("amount_usd") or 0)) for t in order_txs if t.get("type") == "income")
                expense_usd = sum(Decimal(str(t.get("amount_usd") or 0)) for t in order_txs if t.get("type") == "expense")
                order_net_usd = float(money(income_usd - expense_usd))
                cost_date = row.get("order_date") or (income_tx or {}).get("original_transaction_date") \
                    or (income_tx or {}).get("date") or now[:10]
                try:
                    product_usd, quote = await _convert(currency, cost_date, row.get("product_cost"))
                    ship_usd, quote2 = await _convert(currency, cost_date, row.get("initial_shipment_cost"))
                    row["_usd"] = {"product": product_usd, "shipping": ship_usd,
                                   "quote": quote or quote2, "cost_date": cost_date}
                    extra_usd = money(((income_tx or {}).get("usd_costs") or {}).get("extra_cost", 0))
                    estimated = float(money(Decimal(str(order_net_usd))
                                            - Decimal(str(product_usd or 0))
                                            - Decimal(str(ship_usd or 0))
                                            - extra_usd))
                except FxError as exc:
                    if status == STATUS_MATCHED:
                        counts["matched"] -= 1
                        counts["new"] -= 1
                    status = STATUS_CONFLICT
                    note = f"Kur alınamadı: {exc}"
                    counts["conflicts"] += 1

            row["_status"] = status
            row["_mp"] = mp
            row["_income_tx_id"] = (income_tx or {}).get("id")
            plan.append({"row": row, "status": status, "mp": mp, "income_tx": income_tx,
                         "existing_sf": existing_sf, "note": note})
            preview.append(SellerFlashRowOut(
                line=row["line"], seller_order_id=row["seller_order_id"],
                marketplace=mp or row.get("marketplace", ""), order_date=row.get("order_date"),
                product_cost=row.get("product_cost"), initial_shipment_cost=row.get("initial_shipment_cost"),
                seller_refund=row.get("seller_refund"), buyer_refund=row.get("buyer_refund"),
                profit=row.get("profit"), profit_rate=row.get("profit_rate"),
                currency=currency, existing_amazon_net_total=order_net_usd,
                estimated_actual_profit=estimated, match_status=status, note=note))

        batch_id = None
        applied = 0
        if commit:
            batch_id = str(uuid.uuid4())
            for item in plan:
                row, status, mp = item["row"], item["status"], item["mp"]
                if not mp or status == STATUS_MP_MISMATCH:
                    continue
                usd = row.get("_usd") or {}
                record = {
                    **scope,
                    "marketplace": mp,
                    "seller_order_id": row["seller_order_id"],
                    "buyer_order_id": row.get("buyer_order_id", ""),
                    "seller_order_status": row.get("seller_order_status", ""),
                    "buyer_order_status": row.get("buyer_order_status", ""),
                    "price": row.get("price"), "profit": row.get("profit"),
                    "profit_rate": row.get("profit_rate"),
                    "order_date": row.get("order_date"), "order_date_raw": row.get("order_date_raw", ""),
                    "product_cost": row.get("product_cost"),
                    "initial_shipment_cost": row.get("initial_shipment_cost"),
                    "seller_refund": row.get("seller_refund"), "buyer_refund": row.get("buyer_refund"),
                    "delivery_end_date": row.get("delivery_end_date"), "notes": row.get("notes", ""),
                    "currency": marketplaces[mp]["currency"],
                    "product_cost_usd": usd.get("product"), "shipping_cost_usd": usd.get("shipping"),
                    "fx": usd.get("quote"), "fx_cost_date": usd.get("cost_date"),
                    "linked_transaction_id": row.get("_income_tx_id"),
                    "match_status": "matched" if status in (STATUS_MATCHED, STATUS_WILL_UPDATE) else "unmatched",
                    "source": "sellerflash",
                    "last_seen_at": now, "last_updated_at": now,
                    "last_import_batch_id": batch_id,
                }
                identity = {**scope, "marketplace": mp, "seller_order_id": row["seller_order_id"]}
                if status == STATUS_ALREADY_IMPORTED:
                    await db.sellerflash_costs.update_one(
                        identity, {"$set": {"last_seen_at": now, "last_import_batch_id": batch_id}})
                    continue
                if status == STATUS_WILL_UPDATE and item["existing_sf"]:
                    rec_id = item["existing_sf"]["id"]
                    changes = row.get("_changes") or {}
                    await db.sellerflash_costs.update_one({"id": rec_id}, {"$set": record})
                    if changes:
                        await db.sellerflash_history.insert_one({
                            "id": str(uuid.uuid4()), **scope, "sellerflash_cost_id": rec_id,
                            "seller_order_id": row["seller_order_id"], "marketplace": mp,
                            "changes": changes, "detected_at": now, "import_batch_id": batch_id})
                    # Kullanıcı sonradan manuel değiştirmediyse maliyeti güncelle
                    tx = None
                    linked_id = item["existing_sf"].get("linked_transaction_id")
                    if linked_id:
                        tx = await db.transactions.find_one({"id": linked_id, **scope}, {"_id": 0})
                    if not tx and item["income_tx"]:
                        tx = item["income_tx"]
                        await db.sellerflash_costs.update_one(
                            {"id": rec_id}, {"$set": {"linked_transaction_id": tx["id"],
                                                      "match_status": "matched"}})
                    if tx and not _has_manual_costs(tx) and (usd.get("product") is not None or usd.get("shipping") is not None):
                        await _apply_costs(db, scope, tx, usd, rec_id)
                        applied += 1
                    continue
                # Yeni kayıt (matched / eksik maliyet / conflict / unmatched hepsi referans olarak saklanır)
                rec_id = str(uuid.uuid4())
                record["id"] = rec_id
                await db.sellerflash_costs.update_one(
                    identity, {"$set": {k: v for k, v in record.items() if k not in ("id", "first_imported_at")},
                               "$setOnInsert": {"id": rec_id, "first_imported_at": now}},
                    upsert=True)
                if status == STATUS_MATCHED and item["income_tx"] and not _has_manual_costs(item["income_tx"]):
                    await _apply_costs(db, scope, item["income_tx"], usd, rec_id)
                    applied += 1
            marketplaces_seen = sorted({item["mp"] for item in plan if item["mp"]})
            await db.sellerflash_imports.insert_one({
                "id": batch_id, **scope, "file_name": file.filename or "",
                "file_type": file_type.lstrip("."), "uploaded_at": now,
                "marketplaces": marketplaces_seen, "total_rows": len(rows),
                "matched": counts["matched"], "new": counts["new"], "updated": counts["updated"],
                "unchanged": counts["unchanged"], "unmatched": counts["unmatched"],
                "conflicts": counts["conflicts"], "rejected_count": len(issues),
                "applied_costs": applied, "status": "completed",
            })

        return SellerFlashImportOut(
            total_rows=len(rows), matched=counts["matched"], new=counts["new"],
            updated=counts["updated"], unchanged=counts["unchanged"],
            unmatched=counts["unmatched"], conflicts=counts["conflicts"],
            missing_product_cost=counts["missing_product_cost"],
            missing_shipping_cost=counts["missing_shipping_cost"],
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
    async def sellerflash_cost_for_order(store_id: str, marketplace: str, order_id: str,
                                         user=Depends(get_current_user)):
        doc = await db.sellerflash_costs.find_one(
            {"user_id": user["id"], "store_id": store_id, "marketplace": marketplace,
             "seller_order_id": order_id}, {"_id": 0})
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
    """SellerFlash maliyetlerini siparişin gelir kaydına USD snapshot ile uygular.

    Ayrı finansal işlem oluşturulmaz; mevcut canonical kaydın maliyet alanları
    tek sefer yazılır. Manuel maliyetler çağıran tarafça zaten korunur.
    """
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
