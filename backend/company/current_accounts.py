from datetime import datetime, timedelta, timezone
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError

from company.common import cash, cents, names, now, owned


def _cash_signed(entry):
    if entry.get("cash_status") != "completed" or entry.get("cash_effect") not in {"in", "out"}:
        return 0
    amount = entry["amount_cents"]
    return amount if entry["cash_effect"] == "in" else -amount


def _balance_signed(entry):
    amount = entry["amount_cents"]
    return amount if entry["direction"] == "payable" else -amount


def due_status(entry):
    if entry.get("cash_status") == "completed":
        return "completed"
    if not entry.get("due_date"):
        return "none"
    today = datetime.now(timezone.utc).date()
    due = datetime.fromisoformat(entry["due_date"]).date()
    if due < today:
        return "overdue"
    if due <= today + timedelta(days=7):
        return "due_soon"
    return "upcoming"


def current_entry_output(doc, people, stores, balance_after=None):
    return {
        **doc,
        "person_name": people.get(doc["person_id"], {}).get("name", "—"),
        "store_name": stores.get(doc.get("store_id"), {}).get("name"),
        "amount": cash(doc["amount_cents"]),
        "due_status": due_status(doc),
        "balance_after": cash(balance_after) if balance_after is not None else 0,
    }


def _sorted_entries(entries):
    return sorted(entries, key=lambda item: (item["date"], item.get("created_at", ""), item["id"]))


def _with_balances(entries):
    balances = {}
    output = []
    for entry in _sorted_entries(entries):
        key = (entry["person_id"], entry["currency"])
        balances[key] = balances.get(key, 0) + _balance_signed(entry)
        output.append((entry, balances[key]))
    return output


async def create_current_entry(db, user_id, data):
    await owned(db, "company_people", data.person_id, user_id)
    if data.store_id:
        await owned(db, "stores", data.store_id, user_id)
    doc = {
        **data.model_dump(mode="json", exclude={"request_id", "amount"}),
        "id": str(data.request_id),
        "user_id": user_id,
        "amount_cents": cents(data.amount),
        "created_at": now(),
    }
    try:
        await db.company_current_entries.insert_one(dict(doc))
    except DuplicateKeyError:
        previous = await owned(db, "company_current_entries", doc["id"], user_id)
        compare = ("person_id", "store_id", "direction", "currency", "amount_cents", "date", "due_date", "cash_effect", "cash_status", "note")
        if any(previous.get(key) != doc.get(key) for key in compare):
            raise HTTPException(409, "Aynı işlem anahtarı farklı bir cari hareket için kullanılamaz")
        doc = previous
    people, stores = await names(db, user_id)
    return current_entry_output(doc, people, stores)


async def current_entries(db, user_id, person_id=None, currency=None, store_id=None):
    query = {"user_id": user_id}
    if person_id:
        query["person_id"] = person_id
    if currency:
        query["currency"] = currency
    if store_id:
        query["store_id"] = store_id
    docs = await db.company_current_entries.find(query, {"_id": 0}).to_list(None)
    people, stores = await names(db, user_id)
    balance_pairs = _with_balances(docs)
    output = [current_entry_output(entry, people, stores, balance) for entry, balance in balance_pairs]
    output.sort(key=lambda item: (item["date"], item.get("created_at", "")), reverse=True)
    return output


async def current_account_summary(db, user_id, person_id=None, currency=None, store_id=None):
    query = {"user_id": user_id}
    if person_id:
        query["person_id"] = person_id
    if currency:
        query["currency"] = currency
    if store_id:
        query["store_id"] = store_id
    docs = await db.company_current_entries.find(query, {"_id": 0}).to_list(None)
    people, _ = await names(db, user_id)
    totals = {}
    for entry in docs:
        key = (entry["person_id"], entry["currency"])
        bucket = totals.setdefault(key, {"total_payable": 0, "total_receivable": 0, "net_balance": 0, "entry_count": 0})
        amount = entry["amount_cents"]
        bucket["total_payable"] += amount if entry["direction"] == "payable" else 0
        bucket["total_receivable"] += amount if entry["direction"] == "receivable" else 0
        bucket["net_balance"] += _balance_signed(entry)
        bucket["entry_count"] += 1
    summaries = [
        {
            "person_id": person,
            "person_name": people.get(person, {}).get("name", "—"),
            "currency": curr,
            "total_payable": cash(values["total_payable"]),
            "total_receivable": cash(values["total_receivable"]),
            "net_balance": cash(values["net_balance"]),
            "entry_count": values["entry_count"],
        }
        for (person, curr), values in sorted(totals.items(), key=lambda pair: (people.get(pair[0][0], {}).get("name", ""), pair[0][1]))
    ]
    return {"summaries": summaries, "entries": await current_entries(db, user_id, person_id, currency, store_id)}


async def update_current_entry(db, user_id, entry_id, data):
    current = await owned(db, "company_current_entries", entry_id, user_id)
    await owned(db, "company_people", data.person_id, user_id)
    if data.store_id:
        await owned(db, "stores", data.store_id, user_id)
    changes = {
        **data.model_dump(mode="json", exclude={"amount"}),
        "amount_cents": cents(data.amount),
    }
    updated = await db.company_current_entries.find_one_and_update(
        {"id": entry_id, "user_id": user_id}, {"$set": changes}, return_document=True, projection={"_id": 0}
    )
    if not updated:
        raise HTTPException(404, "Cari hareket bulunamadı")
    people, stores = await names(db, user_id)
    return current_entry_output(updated, people, stores)


async def delete_current_entry(db, user_id, entry_id):
    result = await db.company_current_entries.delete_one({"id": entry_id, "user_id": user_id})
    if result.deleted_count == 0:
        raise HTTPException(404, "Cari hareket bulunamadı")
    return {"ok": True}


async def complete_current_entries(db, user_id, entry_ids):
    ids = list(dict.fromkeys(entry_ids))
    result = await db.company_current_entries.update_many(
        {"id": {"$in": ids}, "user_id": user_id, "cash_status": "pending"},
        {"$set": {"cash_status": "completed"}},
    )
    if result.matched_count == 0:
        raise HTTPException(404, "Bekleyen cari hareket bulunamadı")
    return {"ok": True, "updated": result.modified_count, "ids": ids}


async def current_report_data(db, user_id, person_id=None, currency=None, start_date=None, end_date=None):
    query = {"user_id": user_id}
    if person_id:
        query["person_id"] = person_id
    if currency:
        query["currency"] = currency
    docs = await db.company_current_entries.find(query, {"_id": 0}).to_list(None)
    people, stores = await names(db, user_id)
    pairs = _with_balances(docs)
    filtered = [(entry, balance) for entry, balance in pairs if (not start_date or entry["date"] >= start_date) and (not end_date or entry["date"] <= end_date)]
    rows = [current_entry_output(entry, people, stores, balance) for entry, balance in filtered]
    totals = {"total_payable": 0, "total_receivable": 0, "net_balance": 0}
    for entry, _ in filtered:
        amount = entry["amount_cents"]
        totals["total_payable"] += amount if entry["direction"] == "payable" else 0
        totals["total_receivable"] += amount if entry["direction"] == "receivable" else 0
        totals["net_balance"] += _balance_signed(entry)
    rows.sort(key=lambda item: (item["date"], item.get("created_at", "")))
    return {"rows": rows, "totals": {key: cash(value) for key, value in totals.items()}, "people": people}


def current_cash_ledger(entry, people, stores):
    signed = _cash_signed(entry)
    if not signed:
        return None
    return {
        "id": entry["id"],
        "date": entry["date"],
        "currency": entry["currency"],
        "amount": cash(signed),
        "kind": "current_cash_in" if signed > 0 else "current_cash_out",
        "note": entry.get("note", ""),
        "person_name": people.get(entry["person_id"], {}).get("name", ""),
        "store_name": stores.get(entry.get("store_id"), {}).get("name", ""),
        "created_at": entry["created_at"],
        "source": "current_account",
    }


async def current_cash_ledger_entries(db, user_id):
    entries = await db.company_current_entries.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    people, stores = await names(db, user_id)
    return [ledger for entry in entries if (ledger := current_cash_ledger(entry, people, stores))]
