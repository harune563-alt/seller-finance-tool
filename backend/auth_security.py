"""Durable failed-login limits shared by all application workers."""
import math
import os
from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pymongo import ReturnDocument
from pymongo.errors import DuplicateKeyError


def policy():
    return int(os.environ["LOGIN_MAX_ATTEMPTS"]), int(os.environ["LOGIN_LOCKOUT_SECONDS"])


def locked(expires_at, now):
    seconds = max(1, math.ceil((expires_at.replace(tzinfo=timezone.utc) - now).total_seconds()))
    raise HTTPException(429, "Çok fazla hatalı giriş. Lütfen daha sonra tekrar deneyin.", headers={"Retry-After": str(seconds)})


async def check_login_limit(db, identifier):
    maximum, _ = policy()
    now = datetime.now(timezone.utc)
    entry = await db.login_attempts.find_one({"identifier": identifier, "attempts": {"$gte": maximum}, "expires_at": {"$gt": now}}, {"_id": 0})
    if entry:
        locked(entry["expires_at"], now)


async def record_login_failure(db, identifier):
    maximum, duration = policy()
    now = datetime.now(timezone.utc)
    expires = now + timedelta(seconds=duration)
    # Pipeline arithmetic resets expired counters atomically, including concurrent attempts.
    pipeline = [{"$set": {
        "attempts": {"$cond": [{"$gt": ["$expires_at", now]}, {"$add": ["$attempts", 1]}, 1]},
        "expires_at": {"$cond": [{"$gt": ["$expires_at", now]}, "$expires_at", expires]},
    }}, {"$set": {"expires_at": {"$cond": [{"$eq": ["$attempts", maximum]}, expires, "$expires_at"]}}}]
    try:
        entry = await db.login_attempts.find_one_and_update({"identifier": identifier}, pipeline, upsert=True,
                    return_document=ReturnDocument.AFTER, projection={"_id": 0})
    except DuplicateKeyError:
        entry = await db.login_attempts.find_one_and_update({"identifier": identifier}, pipeline,
                    return_document=ReturnDocument.AFTER, projection={"_id": 0})
    if entry["attempts"] >= maximum:
        locked(entry["expires_at"], now)