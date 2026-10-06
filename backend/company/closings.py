import hashlib
import json
import logging
from collections import defaultdict
from datetime import datetime, timezone, timedelta
from pymongo.errors import DuplicateKeyError
from company.common import now
from usd_ledger import enrich_records, summary_usd


async def reconcile_user(db, user_id):
    current_month = datetime.now(timezone.utc).strftime("%Y-%m")
    stores = {s["id"]: s for s in await db.stores.find({"user_id": user_id}, {"_id": 0}).to_list(None)}
    rows = await db.transactions.find({"user_id": user_id, "type": {"$in": ["income", "expense"]}, "date": {"$lt": current_month + "-01"}}, {"_id": 0}).to_list(None)
    buckets = defaultdict(list)
    for row in rows:
        if row["store_id"] in stores: buckets[(row["store_id"], row["date"][:7])].append(row)
    prior = await db.company_closings.find({"user_id": user_id, "period": {"$lt": current_month}}, {"_id": 0}).to_list(None)
    for record in prior:
        if record["store_id"] in stores: buckets.setdefault((record["store_id"], record["period"]), [])
    for (store_id, period), transactions in buckets.items():
        enriched = await enrich_records(db, transactions)
        result = summary_usd(enriched)
        status = "blocked" if result["incomplete_count"] else "posted"
        financial = {k: result[k] for k in ("revenue", "expenses", "net_profit")}
        digest = hashlib.sha256(json.dumps({"status": status, **financial}, sort_keys=True).encode()).hexdigest()
        identity = {"user_id": user_id, "store_id": store_id, "period": period}
        record_id = hashlib.sha256(f"{user_id}|{store_id}|{period}".encode()).hexdigest()
        current = await db.company_closings.find_one(identity, {"_id": 0})
        values = {**financial, "status": status, "error": "; ".join(result["fx_errors"]), "source_digest": digest,
                  "store_name": stores[store_id]["name"], "updated_at": now()}
        if current:
            if current["source_digest"] != digest:
                await db.company_closings.update_one({**identity, "source_digest": current["source_digest"]},
                    {"$set": values, "$inc": {"revision": 1}, "$push": {"revisions": {"net_profit": current["net_profit"], "status": current["status"], "replaced_at": now()}}})
        else:
            try:
                await db.company_closings.insert_one({**identity, **values, "id": record_id, "revision": 1, "revisions": [], "created_at": now()})
            except DuplicateKeyError:
                pass
    return len(buckets)


async def run_close_job(db, run_id, user_id=None):
    claimed = await db.company_jobs.find_one_and_update({"run_id": run_id, "status": "pending"}, {"$set": {"status": "running", "updated_at": now()}}, projection={"_id": 0})
    if not claimed: return
    processed = 0
    try:
        users = [user_id] if user_id else await db.stores.distinct("user_id")
        for uid in users:
            activity_id = run_id if user_id else f"{run_id}:user:{uid}"
            if not user_id:
                await db.company_jobs.update_one({"run_id": activity_id}, {"$setOnInsert": {"user_id": uid, "created_at": now(), "error": "", "processed": 0}, "$set": {"status": "running", "updated_at": now()}}, upsert=True)
            count = await reconcile_user(db, uid)
            processed += count
            if not user_id: await db.company_jobs.update_one({"run_id": activity_id}, {"$set": {"status": "completed", "processed": count, "updated_at": now()}})
        await db.company_jobs.update_one({"run_id": run_id}, {"$set": {"status": "completed", "processed": processed, "updated_at": now()}})
        # A fresh daily reconciliation covers work lost if a previous process stopped.
        cutoff = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
        stale = {"status": {"$in": ["pending", "running"]}, "created_at": {"$lt": cutoff}}
        if user_id: stale["user_id"] = user_id
        await db.company_jobs.update_many(stale, {"$set": {"status": "interrupted", "error": "Sonraki eşitleme tarafından yeniden hesaplandı", "updated_at": now()}})
    except Exception:
        logging.getLogger(__name__).exception("Company close job failed: %s", run_id)
        await db.company_jobs.update_one({"run_id": run_id}, {"$set": {"status": "failed", "processed": processed, "error": "Kapanış tamamlanamadı; yeniden eşitleyin.", "updated_at": now()}})


async def queue_close(db, background_tasks, run_id, user_id=None):
    job = {"run_id": run_id, "user_id": user_id, "status": "pending", "created_at": now(), "updated_at": now(), "processed": 0, "error": ""}
    try: await db.company_jobs.insert_one(dict(job))
    except DuplicateKeyError: return {"accepted": True, "duplicate": True, "run_id": run_id}
    background_tasks.add_task(run_close_job, db, run_id, user_id)
    return {"accepted": True, "duplicate": False, "run_id": run_id}