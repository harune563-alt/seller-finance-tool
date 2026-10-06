from datetime import datetime, timezone
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from company.common import cash, cents, names, now, owned

def debt_output(doc, people, stores):
    return {**doc, "person_name": people.get(doc["person_id"], {}).get("name", "—"), "store_name": stores.get(doc.get("store_id"), {}).get("name"),
            "principal": cash(doc["principal_cents"]), "remaining": cash(doc["remaining_cents"]),
            "status": "closed" if doc["remaining_cents"] == 0 else "overdue" if doc.get("due_date") and doc["due_date"] < datetime.now(timezone.utc).date().isoformat() else "open",
            "payments": [{**p, "amount": cash(p["amount_cents"])} for p in doc["payments"]]}

async def create_debt(db, user_id, data):
    await owned(db, "company_people", data.person_id, user_id)
    if data.store_id: await owned(db, "stores", data.store_id, user_id)
    doc = {**data.model_dump(mode="json", exclude={"request_id", "amount"}), "id": str(data.request_id), "user_id": user_id,
           "principal_cents": cents(data.amount), "remaining_cents": cents(data.amount), "payments": [], "created_at": now()}
    try: await db.company_debts.insert_one(dict(doc))
    except DuplicateKeyError:
        previous = await owned(db, "company_debts", doc["id"], user_id)
        if any(previous.get(k) != doc.get(k) for k in ("person_id", "store_id", "direction", "currency", "principal_cents", "date", "due_date", "cash_effect", "note")):
            raise HTTPException(409, "Aynı işlem anahtarı farklı bir kayıt için kullanılamaz")
        doc = previous
    return debt_output(doc, *(await names(db, user_id)))

async def settle_debt(db, user_id, debt_id, data):
    doc = await owned(db, "company_debts", debt_id, user_id)
    payment_id = str(data.request_id)
    prior_payment = next((p for p in doc["payments"] if p["id"] == payment_id), None)
    if prior_payment:
        if prior_payment["amount_cents"] != cents(data.amount) or prior_payment["date"] != data.date or prior_payment["note"] != data.note:
            raise HTTPException(409, "Aynı işlem anahtarı farklı bir ödeme için kullanılamaz")
        return debt_output(doc, *(await names(db, user_id)))
    if data.date < doc["date"]: raise HTTPException(422, "Ödeme tarihi borcun açılışından önce olamaz")
    payment = {"id": payment_id, "date": data.date, "amount_cents": cents(data.amount), "note": data.note, "created_at": now()}
    updated = await db.company_debts.find_one_and_update(
        {"id": debt_id, "user_id": user_id, "remaining_cents": {"$gte": payment["amount_cents"]}, "payments.id": {"$ne": payment_id}},
        {"$inc": {"remaining_cents": -payment["amount_cents"]}, "$push": {"payments": payment}}, return_document=True, projection={"_id": 0})
    if not updated:
        current = await owned(db, "company_debts", debt_id, user_id)
        if any(p["id"] == payment_id for p in current["payments"]): return debt_output(current, *(await names(db, user_id)))
        raise HTTPException(422, "Ödeme kalan borç/alacak tutarını aşamaz")
    return debt_output(updated, *(await names(db, user_id)))

async def company_overview(db, user_id):
    people, stores = await names(db, user_id)
    balances = {c: {"currency": c, "cash_balance": 0, "payables": 0, "receivables": 0, "capital": 0} for c in ("USD", "TRY")}
    ledger = []
    def add(record_id, date, currency, amount, kind, note, created_at, person_id=None, store_id=None):
        balances[currency]["cash_balance"] += amount
        ledger.append({"id": record_id, "date": date, "currency": currency, "amount": cash(amount), "kind": kind, "note": note,
                       "person_name": people.get(person_id, {}).get("name", ""), "store_name": stores.get(store_id, {}).get("name", ""), "created_at": created_at})
    accounts = await db.company_capital.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    for a in accounts:
        balances[a["currency"]]["capital"] += a["native_cents"]
        for e in a["entries"]:
            add(e["id"], e["date"], a["currency"], e["amount_cents"] * (1 if e["direction"] == "contribution" else -1), "capital_" + e["direction"], e["note"], e["created_at"], a["person_id"], a["store_id"])
    debts = await db.company_debts.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    for d in debts:
        balances[d["currency"]]["payables" if d["direction"] == "payable" else "receivables"] += d["remaining_cents"]
        sign = 1 if d["direction"] == "payable" else -1
        if d["cash_effect"]: add(d["id"], d["date"], d["currency"], d["principal_cents"] * sign, "debt_" + d["direction"], d["note"], d["created_at"], d["person_id"], d.get("store_id"))
        for p in d["payments"]:
            add(p["id"], p["date"], d["currency"], -sign * p["amount_cents"], "repayment" if sign == 1 else "collection", p["note"], p["created_at"], d["person_id"], d.get("store_id"))
    for e in await db.company_cash.find({"user_id": user_id}, {"_id": 0}).to_list(None):
        add(e["id"], e["date"], e["currency"], e["amount_cents"] * (1 if e["direction"] == "in" else -1), "cash_" + e["direction"], e["note"], e["created_at"])
    closings = await db.company_closings.find({"user_id": user_id}, {"_id": 0}).to_list(None)
    blocked = sum(c["status"] != "posted" for c in closings)
    profit_cents = sum(cents(c["net_profit"]) for c in closings if c["status"] == "posted")
    return {"balances": [{k: cash(v) if k != "currency" else v for k, v in b.items()} for b in balances.values()],
            "closed_profit_usd": None if blocked else cash(profit_cents), "book_balance_usd": None if blocked else cash(balances["USD"]["cash_balance"] + profit_cents),
            "blocked_closings": blocked, "people_count": len(people), "latest_close_at": max((c["updated_at"] for c in closings), default=None),
            "ledger": sorted(ledger, key=lambda e: (e["date"], e["created_at"]), reverse=True)}