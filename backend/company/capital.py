from decimal import Decimal
from fastapi import HTTPException
from pymongo.errors import DuplicateKeyError
from fx_service import get_rate, FxError
from company.common import cash, cents, names, now, owned

async def post_capital(db, user_id, data):
    await owned(db, "stores", data.store_id, user_id)
    await owned(db, "company_people", data.person_id, user_id)
    scope = {"user_id": user_id, "store_id": data.store_id, "person_id": data.person_id, "currency": data.currency}
    entry_id, amount = str(data.request_id), cents(data.amount)
    try:
        await db.company_capital.update_one(scope, {"$setOnInsert": {**scope, "native_cents": 0, "basis_cents": 0, "version": 0, "entries": []}}, upsert=True)
    except DuplicateKeyError:
        pass
    quote = None
    for _ in range(10):
        account = await db.company_capital.find_one(scope, {"_id": 0})
        previous = next((e for e in account["entries"] if e["id"] == entry_id), None)
        if previous:
            if previous["amount_cents"] != amount or previous["direction"] != data.direction or previous["date"] != data.date or previous["note"] != data.note:
                raise HTTPException(409, "Aynı işlem anahtarı farklı bir kayıt için kullanılamaz")
            return
        if data.direction == "withdrawal":
            if account["native_cents"] < amount:
                raise HTTPException(422, "İade tutarı kişinin bu mağaza ve para birimindeki net sermayesini aşamaz")
            chronological = account["entries"] + [{"date": data.date, "created_at": now(), "direction": "withdrawal", "amount_cents": amount}]
            running = 0
            for movement in sorted(chronological, key=lambda e: (e["date"], e["created_at"])):
                running += movement["amount_cents"] * (1 if movement["direction"] == "contribution" else -1)
                if running < 0: raise HTTPException(422, "Sermaye iadesinin tarihinde yeterli yatırılmış sermaye yok")
            basis = account["basis_cents"] if amount == account["native_cents"] else cents(Decimal(amount) / 100 * Decimal(account["basis_cents"]) / Decimal(account["native_cents"]))
            sign, method = -1, "historical_average_cost"
        else:
            if quote is None:
                try: quote = await get_rate(db, data.currency, data.date)
                except FxError as exc: raise HTTPException(422, str(exc))
            basis = cents(data.amount * Decimal(quote["rate"]))
            if basis < 1: raise HTTPException(422, "USD sermaye karşılığı en az 0.01 olmalıdır")
            sign, method = 1, "historical_fx"
        entry = {"id": entry_id, "direction": data.direction, "amount_cents": amount, "basis_cents": basis,
                 "date": data.date, "note": data.note, "created_at": now(), "basis_method": method, "fx": quote}
        result = await db.company_capital.update_one({**scope, "version": account["version"], "entries.id": {"$ne": entry_id}},
            {"$inc": {"version": 1, "native_cents": sign * amount, "basis_cents": sign * basis}, "$push": {"entries": entry}})
        if result.modified_count: return
    raise HTTPException(409, "Sermaye kaydı eşzamanlı değişti. Tekrar deneyin.")

async def capital_summary(db, user_id, store_id):
    await owned(db, "stores", store_id, user_id)
    people, _ = await names(db, user_id)
    accounts = await db.company_capital.find({"user_id": user_id, "store_id": store_id, "entries.0": {"$exists": True}}, {"_id": 0}).to_list(None)
    partners, entries = {}, []
    total = sum(a["basis_cents"] for a in accounts)
    for a in accounts:
        person = people.get(a["person_id"], {})
        item = partners.setdefault(a["person_id"], {"person_id": a["person_id"], "person_name": person.get("name", "—"), "role": person.get("role", "contact"), "basis": 0, "balances": {"USD": 0, "TRY": 0}})
        item["basis"] += a["basis_cents"]
        item["balances"][a["currency"]] = cash(a["native_cents"])
        for e in a["entries"]:
            entries.append({**e, "store_id": store_id, "person_id": a["person_id"], "person_name": item["person_name"], "currency": a["currency"], "amount": cash(e["amount_cents"]), "usd_basis": cash(e["basis_cents"])})
    ownership = [{**p, "net_capital_usd": cash(p["basis"]), "share_percent": round(p["basis"] / total * 100, 4) if total else 0} for p in partners.values()]
    return {"store_id": store_id, "total_usd": cash(total), "ownership": sorted(ownership, key=lambda p: -p["net_capital_usd"]), "entries": sorted(entries, key=lambda e: (e["date"], e["created_at"]), reverse=True)}