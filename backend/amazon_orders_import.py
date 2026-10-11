"""Amazon All Orders / Fulfillment Import — ayrı modül; mevcut Amazon Payments akışına DOKUNMAZ.

Bu modül finansal işlem OLUŞTURMAZ ve mevcut finansal toplamları DEĞİŞTİRMEZ.
Yalnızca canonical Amazon siparişlerini (amazon_orders) ürün-bazında meta veri ile
zenginleştirir ve fulfillment sınıflandırması (FBA / FBM / MIXED / UNKNOWN) yazar.

Kimlik: amazon-order-id + order-item-id (dosya adı / satır pozisyonu asla kimlik değildir).
Eşleştirme: yalnızca amazon-order-id (pazar yeri gerekmez).
"""
import csv
import hashlib
import io
import logging
import uuid
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from pydantic import BaseModel
from pymongo import UpdateOne

MAX_ROWS = 50000
MAX_FILE_BYTES = 10 * 1024 * 1024

# All Orders raporu başlıkları (tire/alt çizgi/boşluk varyasyonları normalize edilir)
HEADER_MAP = {
    "amazon-order-id": "amazon_order_id",
    "merchant-order-id": "merchant_order_id",
    "purchase-date": "purchase_date",
    "last-updated-date": "last_updated_date",
    "order-status": "order_status",
    "fulfillment-channel": "fulfillment_channel",
    "sales-channel": "sales_channel",
    "product-name": "product_name",
    "sku": "sku",
    "asin": "asin",
    "item-status": "item_status",
    "quantity": "quantity",
    "currency": "currency",
    "item-price": "item_price",
    "item-tax": "item_tax",
    "shipping-price": "shipping_price",
    "shipping-tax": "shipping_tax",
    "order-item-id": "order_item_id",
}

# Yeniden içe aktarmada değişim tespiti için karşılaştırılan alanlar
COMPARE_FIELDS = ("sku", "asin", "quantity", "product_name", "item_status",
                  "fulfillment_channel", "purchase_date", "last_updated_date",
                  "order_status", "currency", "item_price", "merchant_order_id",
                  "sales_channel")

ACTION_ATTACH = "attach"            # eşleşti + yeni kalem
ACTION_UPDATE = "update"            # eşleşti + değişen kalem
ACTION_ENRICH = "enrich"            # eşleşti + kalem aynı AMA finansal satır zenginleştirilmemiş
ACTION_NO_CHANGE = "no_change"      # eşleşti + kalem aynı + finansal satır zaten zenginleştirilmiş
ACTION_UNMATCHED = "unmatched"      # canonical Amazon siparişi yok

FBA = "FBA"
FBM = "FBM"
MIXED = "MIXED"
UNKNOWN = "UNKNOWN"


def _norm_header(value):
    text = str(value or "").strip().lstrip("﻿").lower()
    for ch in ("_", " ", "."):
        text = text.replace(ch, "-")
    while "--" in text:
        text = text.replace("--", "-")
    return text


def _parse_quantity(raw):
    try:
        return int(float(str(raw or "").replace(",", ".").strip() or "0"))
    except (ValueError, TypeError):
        return 0


def resolve_item_fulfillment(raw_channel):
    """fulfillment-channel = Amazon -> FBA, Merchant -> FBM (kalem seviyesi)."""
    text = str(raw_channel or "").strip().lower()
    if text == "amazon":
        return FBA
    if text == "merchant":
        return FBM
    return ""


def _is_cancelled(row):
    blob = f"{row.get('order_status') or ''} {row.get('item_status') or ''}".lower()
    return "cancel" in blob


def is_active_item(row):
    """Aktif kalem: miktar taşıyan ve iptal edilmemiş satır.

    quantity=0 iptal satırları sınıflandırmada yok sayılır; iptal edilmiş sıfır
    miktarlı satır aktif kargolanmış satırı asla ezemez.
    """
    return _parse_quantity(row.get("quantity")) > 0 and not _is_cancelled(row)


def classify_order_fulfillment(items):
    """Sipariş seviyesi: tüm aktif kalemler FBA -> FBA, tümü FBM -> FBM,
    ikisi birden -> MIXED, kullanılabilir veri yok -> UNKNOWN."""
    resolved = {resolve_item_fulfillment(it.get("fulfillment_channel"))
                for it in items if is_active_item(it)}
    resolved.discard("")
    if not resolved:
        return UNKNOWN
    if resolved == {FBA}:
        return FBA
    if resolved == {FBM}:
        return FBM
    return MIXED


def item_fingerprint(row):
    payload = "|".join(str(row.get(f) or "") for f in COMPARE_FIELDS)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def parse_all_orders(content, filename):
    """Amazon All Orders raporunu ayrıştırır (.txt/.tsv/.csv; sekme, virgül veya noktalı virgül).

    Hiçbir şeyi değiştirmez; (satırlar, reddedilenler) döndürür.
    """
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        text = content.decode("latin-1")

    header_idx = None
    delimiter = None
    mapping = None
    lines = text.splitlines()
    for idx, line in enumerate(lines[:50]):
        if not line.strip():
            continue
        for cand in ("\t", ",", ";"):
            cells = next(csv.reader([line], delimiter=cand), None) or []
            normed = [_norm_header(c) for c in cells]
            cand_map = {i: HEADER_MAP[h] for i, h in enumerate(normed) if h in HEADER_MAP}
            if "amazon_order_id" in cand_map.values() and "order_item_id" in cand_map.values():
                header_idx, delimiter, mapping = idx, cand, cand_map
                break
        if mapping:
            break
    if mapping is None:
        raise ValueError("Amazon All Orders başlıkları bulunamadı (amazon-order-id / order-item-id gerekli)")

    rows, issues = [], []
    reader = csv.reader(lines[header_idx + 1:], delimiter=delimiter)
    for offset, cells in enumerate(reader, start=1):
        if not cells or not any(str(c).strip() for c in cells):
            continue
        row = {field: (cells[i] if i < len(cells) else "").strip() for i, field in mapping.items()}
        line = header_idx + 1 + offset
        if not row.get("amazon_order_id"):
            issues.append({"line": line, "reason": "amazon-order-id eksik"})
            continue
        if not row.get("order_item_id"):
            issues.append({"line": line, "reason": "order-item-id eksik"})
            continue
        row["line"] = line
        row["quantity"] = _parse_quantity(row.get("quantity"))
        rows.append(row)
        if len(rows) > MAX_ROWS:
            raise ValueError(f"Rapor en fazla {MAX_ROWS} satır içerebilir")
    return rows, issues


class OrderItemRowOut(BaseModel):
    line: int
    amazon_order_id: str
    order_item_id: str
    sku: str = ""
    asin: str = ""
    quantity: int = 0
    product_name: str = ""
    fulfillment_channel: str = ""
    resolved_fulfillment: str = ""
    order_status: str = ""
    item_status: str = ""
    matched: bool = False
    action: str


class OrdersImportOut(BaseModel):
    total_rows: int
    matched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: int = 0
    enrichment_required: int = 0
    fba_items: int = 0
    fbm_items: int = 0
    mixed_orders: int = 0
    rejected_count: int = 0
    issues: list = []
    preview: List[OrderItemRowOut] = []
    committed: bool = False
    batch_id: Optional[str] = None


class OrdersBatchOut(BaseModel):
    id: str
    file_name: str = ""
    uploaded_at: Optional[str] = None
    total_rows: int = 0
    matched: int = 0
    new: int = 0
    updated: int = 0
    unchanged: int = 0
    unmatched: int = 0
    enrichment_required: int = 0
    fba_items: int = 0
    fbm_items: int = 0
    mixed_orders: int = 0
    status: str = "completed"


def amazon_orders_router(db, get_current_user):
    router = APIRouter(prefix="/amazon-orders", tags=["amazon-orders"])

    @router.post("/import", response_model=OrdersImportOut)
    async def import_all_orders(
        file: UploadFile = File(...),
        commit: Optional[str] = Query(None),
        commit_form: Optional[str] = Form(None),
        user=Depends(get_current_user),
    ):
        # Hem query (?commit=true) hem multipart form alanı kabul edilir
        do_commit = str(commit if commit is not None else (commit_form or "")).strip().lower() \
            in ("1", "true", "yes", "on")
        name = (file.filename or "").lower()
        if not name.endswith((".txt", ".tsv", ".csv")):
            raise HTTPException(400, "Amazon All Orders raporu için .txt, .tsv veya .csv dosyası seçin")
        content = await file.read(MAX_FILE_BYTES + 1)
        await file.close()
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(413, "Dosya en fazla 10 MB olabilir")
        try:
            rows, issues = parse_all_orders(content, file.filename or "")
        except (ValueError, UnicodeError) as exc:
            raise HTTPException(400, f"Amazon All Orders raporu okunamadı: {exc}")

        scope = {"user_id": user["id"]}
        now = datetime.now(timezone.utc).isoformat()

        # 1) Eşleşme — YALNIZCA normalize amazon-order-id, KAYNAK BAĞIMSIZ:
        #    canonical kayıt (Amazon Payments import) VEYA mevcut Income/Expense
        #    işlemi (manuel oluşturulmuş dahil) aynı Order ID'yi taşıyorsa Matched.
        #    Import kaynağı, pazar yeri, SKU ve order-item-id eşleşmede KULLANILMAZ.
        order_ids = sorted({r["amazon_order_id"] for r in rows})
        canonical = await db.amazon_orders.find(
            {**scope, "order_id": {"$in": order_ids}}, {"_id": 0}).to_list(None)
        canonical_by_order = {}
        for doc in canonical:
            key = (doc.get("order_id") or "").strip()
            if key:
                canonical_by_order.setdefault(key, []).append(doc)

        tx_docs = await db.transactions.find(
            {**scope, "order_id": {"$in": order_ids}},
            {"_id": 0, "order_id": 1, "store_id": 1, "marketplace": 1,
             "fulfillment_type": 1, "amazon_order_item_ids": 1,
             "fulfillment_last_updated_at": 1}).to_list(None)
        tx_by_order = {}
        for t in tx_docs:
            key = (t.get("order_id") or "").strip()
            if key:
                tx_by_order.setdefault(key, []).append(t)

        # 2) Mevcut saklanan kalemler (idempotency)
        identities = [(r["amazon_order_id"], r["order_item_id"]) for r in rows]
        existing_items = await db.amazon_order_items.find(
            {**scope, "amazon_order_id": {"$in": order_ids}}, {"_id": 0}).to_list(None)
        existing_by_key = {(d.get("amazon_order_id"), d.get("order_item_id")): d
                           for d in existing_items}
        incoming_keys = set(identities)

        # 3) Sipariş seviyesi sınıflandırma (mevcut + gelen kalemlerin birleşimi)
        merged_by_order = {}
        for doc in existing_items:
            key = (doc.get("amazon_order_id"), doc.get("order_item_id"))
            if key not in incoming_keys:
                merged_by_order.setdefault(doc.get("amazon_order_id"), []).append(doc)
        for row in rows:
            merged_by_order.setdefault(row["amazon_order_id"], []).append(row)
        classification = {oid: classify_order_fulfillment(items)
                          for oid, items in merged_by_order.items()}

        def _enriched(oid):
            """Finansal zenginleştirme durumu (kalem durumundan BAĞIMSIZ):
            mevcut Income/Expense satırları doğru fulfillment_type, tam kalem
            ilişkisi ve zaman damgası taşıyor mu?"""
            txs = tx_by_order.get(oid) or []
            if not txs:
                return True  # yazılacak finansal satır yok
            want_items = sorted({(it.get("order_item_id") or "")
                                 for it in merged_by_order.get(oid, [])} - {""})
            want_type = classification.get(oid, UNKNOWN)
            for t in txs:
                if (t.get("fulfillment_type") or "") != want_type:
                    return False
                if not t.get("fulfillment_last_updated_at"):
                    return False
                if sorted(t.get("amazon_order_item_ids") or []) != want_items:
                    return False
            return True

        counts = {"matched": 0, "new": 0, "updated": 0, "unchanged": 0,
                  "unmatched": 0, "fba_items": 0, "fbm_items": 0,
                  "enrichment_required": 0}
        preview, plan = [], []

        for row in rows:
            oid, iid = row["amazon_order_id"], row["order_item_id"]
            resolved = resolve_item_fulfillment(row.get("fulfillment_channel"))
            if resolved == FBA:
                counts["fba_items"] += 1
            elif resolved == FBM:
                counts["fbm_items"] += 1

            matched = oid in canonical_by_order or oid in tx_by_order
            existing = existing_by_key.get((oid, iid))
            fp = item_fingerprint(row)
            if not matched:
                action = ACTION_UNMATCHED
                counts["unmatched"] += 1
            elif existing is None:
                action = ACTION_ATTACH
                counts["matched"] += 1
                counts["new"] += 1
            elif existing.get("item_fingerprint") != fp:
                action = ACTION_UPDATE
                counts["matched"] += 1
                counts["updated"] += 1
            elif not _enriched(oid):
                # Kalem meta verisi AYNI ama finansal satır henüz zenginleştirilmemiş
                action = ACTION_ENRICH
                counts["matched"] += 1
                counts["enrichment_required"] += 1
            else:
                action = ACTION_NO_CHANGE
                counts["matched"] += 1
                counts["unchanged"] += 1

            plan.append({"row": row, "action": action, "matched": matched,
                         "existing": existing, "fingerprint": fp})
            preview.append(OrderItemRowOut(
                line=row["line"], amazon_order_id=oid, order_item_id=iid,
                sku=row.get("sku", ""), asin=row.get("asin", ""),
                quantity=row.get("quantity", 0), product_name=row.get("product_name", ""),
                fulfillment_channel=row.get("fulfillment_channel", ""),
                resolved_fulfillment=resolved or "—",
                order_status=row.get("order_status", ""), item_status=row.get("item_status", ""),
                matched=matched, action=action))

        # 4) Mixed sipariş sayısı (kaynak bağımsız eşleşen siparişler üzerinden)
        matched_order_ids = {r["amazon_order_id"] for r in rows
                             if r["amazon_order_id"] in canonical_by_order
                             or r["amazon_order_id"] in tx_by_order}
        mixed_orders = sum(1 for oid in matched_order_ids if classification.get(oid) == MIXED)

        batch_id = None
        if do_commit:
            batch_id = str(uuid.uuid4())
            for item in plan:
                row, action, existing = item["row"], item["action"], item["existing"]
                oid, iid = row["amazon_order_id"], row["order_item_id"]
                record = {
                    **scope,
                    "amazon_order_id": oid,
                    "order_item_id": iid,
                    "merchant_order_id": row.get("merchant_order_id", ""),
                    "sku": row.get("sku", ""),
                    "asin": row.get("asin", ""),
                    "quantity": row.get("quantity", 0),
                    "product_name": row.get("product_name", ""),
                    "item_status": row.get("item_status", ""),
                    "order_status": row.get("order_status", ""),
                    "fulfillment_channel": row.get("fulfillment_channel", ""),
                    "resolved_fulfillment": resolve_item_fulfillment(row.get("fulfillment_channel")),
                    "purchase_date": row.get("purchase_date", ""),
                    "last_updated_date": row.get("last_updated_date", ""),
                    "sales_channel": row.get("sales_channel", ""),
                    "currency": row.get("currency", ""),
                    "item_price": row.get("item_price", ""),
                    "item_fingerprint": item["fingerprint"],
                    "match_status": "matched" if item["matched"] else "unmatched",
                    "last_seen_at": now,
                    "last_import_batch_id": batch_id,
                }
                identity = {**scope, "amazon_order_id": oid, "order_item_id": iid}
                if action == ACTION_NO_CHANGE:
                    await db.amazon_order_items.update_one(
                        identity, {"$set": {"last_seen_at": now,
                                            "last_import_batch_id": batch_id,
                                            "match_status": record["match_status"]}})
                    continue
                await db.amazon_order_items.update_one(
                    identity,
                    {"$set": record,
                     "$setOnInsert": {"id": str(uuid.uuid4()), "first_imported_at": now}},
                    upsert=True)
                if action == ACTION_UPDATE and existing:
                    changes = {f: {"old": existing.get(f), "new": record.get(f)}
                               for f in COMPARE_FIELDS
                               if str(existing.get(f) or "") != str(record.get(f) or "")}
                    if changes:
                        await db.amazon_order_item_history.insert_one({
                            "id": str(uuid.uuid4()), **scope,
                            "amazon_order_id": oid, "order_item_id": iid,
                            "changes": changes, "detected_at": now,
                            "import_batch_id": batch_id})

            # 5) Kaynak bağımsız eşleşen siparişler için canonical kayıt tamamlama
            #    (manuel Income/Expense işlemleri dahil; finansal alan İÇERMEZ)
            matched_oids = sorted({item["row"]["amazon_order_id"] for item in plan if item["matched"]})
            registry_ops = []
            for oid in matched_oids:
                if oid in canonical_by_order:
                    continue
                for t in (tx_by_order.get(oid) or []):
                    if not t.get("store_id") or not t.get("marketplace"):
                        continue
                    registry_ops.append(UpdateOne(
                        {**scope, "store_id": t["store_id"], "marketplace": t["marketplace"],
                         "order_id": oid},
                        {"$setOnInsert": {"id": str(uuid.uuid4()), "first_seen_at": now,
                                          "created_at": now},
                         "$set": {"last_seen_at": now, "last_import_batch_id": batch_id}},
                        upsert=True))
            if registry_ops:
                await db.amazon_orders.bulk_write(registry_ops, ordered=False)

            # 6) Canonical siparişlere fulfillment sınıflandırması yaz (finansal alanlara DOKUNULMAZ)
            if matched_oids:
                await db.amazon_orders.bulk_write([
                    UpdateOne({**scope, "order_id": oid},
                              {"$set": {"fulfillment_type": classification.get(oid, UNKNOWN),
                                        "fulfillment_last_updated_at": now}})
                    for oid in matched_oids
                ], ordered=False)

            # 7) Mevcut finansal kayıtları zenginleştir — YALNIZCA meta veri.
            #    Aynı Amazon Order ID'ye ait var olan Income/Expense satırlarına fulfillment
            #    ve kalem ilişkisi yazılır. Asla yeni işlem OLUŞTURULMAZ (upsert yok),
            #    tutar/tarih/maliyet/kategori gibi finansal alanlara DOKUNULMAZ.
            for oid in matched_oids:
                item_ids = sorted({(it.get("order_item_id") or "") for it in merged_by_order.get(oid, [])}
                                  - {""})
                await db.transactions.update_many(
                    {**scope, "order_id": oid},
                    {"$set": {
                        "fulfillment_type": classification.get(oid, UNKNOWN),
                        "fulfillment_last_updated_at": now,
                        "amazon_order_item_ids": item_ids,
                    }})

            await db.amazon_order_import_batches.insert_one({
                "id": batch_id, **scope, "file_name": file.filename or "",
                "uploaded_at": now, "total_rows": len(rows),
                "matched": counts["matched"], "new": counts["new"],
                "updated": counts["updated"], "unchanged": counts["unchanged"],
                "unmatched": counts["unmatched"],
                "enrichment_required": counts["enrichment_required"],
                "fba_items": counts["fba_items"], "fbm_items": counts["fbm_items"],
                "mixed_orders": mixed_orders, "rejected_count": len(issues),
                "status": "completed",
            })
            # FBA FIFO maliyet tahsisi (yalnızca meta veri; finansal işlem oluşturmaz)
            from fba import allocate_user_stores
            try:
                await allocate_user_stores(db, user["id"])
            except Exception:
                logging.getLogger(__name__).exception("FBA FIFO allocation after orders import failed")

        return OrdersImportOut(
            total_rows=len(rows), matched=counts["matched"], new=counts["new"],
            updated=counts["updated"], unchanged=counts["unchanged"],
            unmatched=counts["unmatched"],
            enrichment_required=counts["enrichment_required"],
            fba_items=counts["fba_items"], fbm_items=counts["fbm_items"],
            mixed_orders=mixed_orders, rejected_count=len(issues), issues=issues[:100],
            preview=preview[:500], committed=do_commit, batch_id=batch_id)

    @router.get("/history", response_model=List[OrdersBatchOut])
    async def orders_import_history(limit: int = 50, user=Depends(get_current_user)):
        """Denetim amaçlı içe aktarma geçmişi; finansal toplamları etkilemez."""
        docs = await db.amazon_order_import_batches.find(
            {"user_id": user["id"]}, {"_id": 0}).sort("uploaded_at", -1).to_list(min(max(limit, 1), 200))
        return [OrdersBatchOut(**d) for d in docs]

    @router.get("/unmatched")
    async def orders_unmatched(user=Depends(get_current_user)):
        docs = await db.amazon_order_items.find(
            {"user_id": user["id"], "match_status": "unmatched"},
            {"_id": 0}).sort("last_seen_at", -1).to_list(500)
        return {"items": docs, "total": len(docs)}

    @router.get("/items")
    async def order_items(order_id: str = Query(...), user=Depends(get_current_user)):
        """Bir Amazon Order ID için saklanan ürün kalemleri (canonical sipariş ilişkisi)."""
        docs = await db.amazon_order_items.find(
            {"user_id": user["id"], "amazon_order_id": order_id.strip()},
            {"_id": 0}).sort("order_item_id", 1).to_list(500)
        canonical = await db.amazon_orders.find(
            {"user_id": user["id"], "order_id": order_id.strip()},
            {"_id": 0, "id": 1, "store_id": 1, "marketplace": 1, "order_id": 1,
             "fulfillment_type": 1, "fulfillment_last_updated_at": 1}).to_list(20)
        return {"items": docs, "total": len(docs), "canonical_orders": canonical}

    return router


async def initialize_amazon_orders_import_indexes(db):
    await db.amazon_order_items.create_index(
        [("user_id", 1), ("amazon_order_id", 1), ("order_item_id", 1)], unique=True)
    await db.amazon_order_items.create_index([("user_id", 1), ("match_status", 1)])
    await db.amazon_order_item_history.create_index([("user_id", 1), ("amazon_order_id", 1)])
    await db.amazon_order_import_batches.create_index([("user_id", 1), ("uploaded_at", -1)])
