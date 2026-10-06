from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from fastapi import HTTPException

def now():
    return datetime.now(timezone.utc).isoformat()

def cents(amount):
    return int((Decimal(str(amount)) * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))

def cash(cents_value):
    return float(Decimal(cents_value) / 100)

async def owned(db, collection, record_id, user_id):
    record = await db[collection].find_one({"id": record_id, "user_id": user_id}, {"_id": 0})
    if not record: raise HTTPException(404, "Kayıt bulunamadı")
    return record

async def names(db, user_id):
    people = await db.company_people.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    stores = await db.stores.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    return {p["id"]: p for p in people}, {s["id"]: s for s in stores}

async def initialize_indexes(db):
    for name in ("company_people", "company_debts", "company_cash", "company_closings"):
        await db[name].create_index([("user_id", 1), ("id", 1)], unique=True)
    await db.company_capital.create_index([("user_id", 1), ("store_id", 1), ("person_id", 1), ("currency", 1)], unique=True)
    await db.company_closings.create_index([("user_id", 1), ("store_id", 1), ("period", 1)], unique=True)
    await db.company_jobs.create_index("run_id", unique=True)