import os
import secrets
import uuid
from typing import Literal, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query
from pydantic import BaseModel, ValidationError
from pymongo.errors import DuplicateKeyError
from company.models import (PersonIn, PersonOut, CapitalIn, CapitalUpdateIn, CapitalOut, DebtIn, DebtUpdateIn, DebtOut,
                            AmountIn, CashIn, CashUpdateIn, PaymentUpdateIn, CompanyOverview, LedgerEntry, ClosingOut,
                            ClosingUpdateIn, BulkIdsIn, JobOut, JobAccepted)
from company.common import cash, cents, names, now, owned
from company.capital import post_capital, capital_summary, update_capital_entry, delete_capital_entry
from company.treasury import create_debt, settle_debt, update_debt, update_debt_payment, delete_debt_payment, debt_output, company_overview
from company.closings import queue_close

class CronEnvelope(BaseModel):
    event: Literal["schedule.triggered"]
    run_id: Optional[str] = None
    schedule_id: Optional[str] = None
    dispatch_time: Optional[str] = None
    job_id: Optional[str] = None
    data: None = None

def company_router(db, get_user):
    router = APIRouter(prefix="/company", tags=["company"])

    @router.get("/people", response_model=list[PersonOut])
    async def people(user=Depends(get_user)):
        return await db.company_people.find({"user_id": user["id"]}, {"_id": 0}).sort("name", 1).to_list(None)

    @router.post("/people", response_model=PersonOut)
    async def add_person(data: PersonIn, user=Depends(get_user)):
        doc = {**data.model_dump(), "id": str(uuid.uuid4()), "user_id": user["id"], "created_at": now()}
        await db.company_people.insert_one(dict(doc))
        return PersonOut(**doc)

    @router.patch("/people/{person_id}", response_model=PersonOut)
    async def edit_person(person_id: str, data: PersonIn, user=Depends(get_user)):
        doc = await db.company_people.find_one_and_update({"id": person_id, "user_id": user["id"]}, {"$set": data.model_dump()}, return_document=True, projection={"_id": 0})
        if not doc: raise HTTPException(404, "Kişi bulunamadı")
        return PersonOut(**doc)

    @router.delete("/people/{person_id}")
    async def delete_person(person_id: str, user=Depends(get_user)):
        if await db.company_capital.find_one({"user_id": user["id"], "entries.0": {"$exists": True}, "person_id": person_id}) or await db.company_debts.find_one({"user_id": user["id"], "person_id": person_id}):
            raise HTTPException(409, "Finansal geçmişi olan kişi silinemez")
        result = await db.company_people.delete_one({"id": person_id, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Kişi bulunamadı")
        return {"ok": True}

    @router.post("/people/bulk-delete")
    async def bulk_delete_people(data: BulkIdsIn, user=Depends(get_user)):
        ids = list(dict.fromkeys(data.ids))
        blocked = await db.company_people.find_one({"user_id": user["id"], "id": {"$in": ids}, "$or": [{"id": {"$in": await db.company_capital.distinct("person_id", {"user_id": user["id"], "entries.0": {"$exists": True}})}}, {"id": {"$in": await db.company_debts.distinct("person_id", {"user_id": user["id"]})}}]}, {"_id": 0, "id": 1})
        if blocked: raise HTTPException(409, "Finansal geçmişi olan kişi silinemez")
        result = await db.company_people.delete_many({"id": {"$in": ids}, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Silinecek kişi bulunamadı")
        return {"ok": True, "deleted": result.deleted_count}

    @router.get("/capital", response_model=CapitalOut)
    async def capital(store_id: str, user=Depends(get_user)):
        return CapitalOut(**await capital_summary(db, user["id"], store_id))

    @router.post("/capital", response_model=CapitalOut)
    async def add_capital(data: CapitalIn, user=Depends(get_user)):
        await post_capital(db, user["id"], data)
        return CapitalOut(**await capital_summary(db, user["id"], data.store_id))

    @router.put("/capital/{entry_id}", response_model=CapitalOut)
    async def edit_capital(entry_id: str, data: CapitalUpdateIn, user=Depends(get_user)):
        store_id = await update_capital_entry(db, user["id"], entry_id, data)
        return CapitalOut(**await capital_summary(db, user["id"], store_id))

    @router.delete("/capital/{entry_id}")
    async def remove_capital(entry_id: str, user=Depends(get_user)):
        store_id = await delete_capital_entry(db, user["id"], entry_id)
        return {"ok": True, "store_id": store_id}

    @router.post("/capital/bulk-delete")
    async def bulk_delete_capital(data: BulkIdsIn, user=Depends(get_user)):
        deleted = 0
        for entry_id in dict.fromkeys(data.ids):
            try:
                await delete_capital_entry(db, user["id"], entry_id)
                deleted += 1
            except HTTPException as exc:
                if exc.status_code != 404: raise
        if not deleted: raise HTTPException(404, "Silinecek sermaye kaydı bulunamadı")
        return {"ok": True, "deleted": deleted}

    @router.get("/debts", response_model=list[DebtOut])
    async def debts(currency: Optional[Literal["USD", "TRY"]] = None, direction: Optional[Literal["payable", "receivable"]] = None, user=Depends(get_user)):
        query = {"user_id": user["id"]}
        if currency: query["currency"] = currency
        if direction: query["direction"] = direction
        docs = await db.company_debts.find(query, {"_id": 0}).sort("date", -1).to_list(None)
        person_names, store_names = await names(db, user["id"])
        return [DebtOut(**debt_output(d, person_names, store_names)) for d in docs]

    @router.post("/debts", response_model=DebtOut)
    async def add_debt(data: DebtIn, user=Depends(get_user)):
        return DebtOut(**await create_debt(db, user["id"], data))

    @router.put("/debts/{debt_id}", response_model=DebtOut)
    async def edit_debt(debt_id: str, data: DebtUpdateIn, user=Depends(get_user)):
        return DebtOut(**await update_debt(db, user["id"], debt_id, data))

    @router.delete("/debts/{debt_id}")
    async def remove_debt(debt_id: str, user=Depends(get_user)):
        result = await db.company_debts.delete_one({"id": debt_id, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Borç/alacak bulunamadı")
        return {"ok": True}

    @router.post("/debts/bulk-delete")
    async def bulk_delete_debts(data: BulkIdsIn, user=Depends(get_user)):
        result = await db.company_debts.delete_many({"id": {"$in": list(dict.fromkeys(data.ids))}, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Silinecek borç/alacak bulunamadı")
        return {"ok": True, "deleted": result.deleted_count}

    @router.post("/debts/{debt_id}/payments", response_model=DebtOut)
    async def pay_debt(debt_id: str, data: AmountIn, user=Depends(get_user)):
        return DebtOut(**await settle_debt(db, user["id"], debt_id, data))

    @router.put("/debts/{debt_id}/payments/{payment_id}", response_model=DebtOut)
    async def edit_debt_payment(debt_id: str, payment_id: str, data: PaymentUpdateIn, user=Depends(get_user)):
        return DebtOut(**await update_debt_payment(db, user["id"], debt_id, payment_id, data))

    @router.delete("/debts/{debt_id}/payments/{payment_id}", response_model=DebtOut)
    async def remove_debt_payment(debt_id: str, payment_id: str, user=Depends(get_user)):
        return DebtOut(**await delete_debt_payment(db, user["id"], debt_id, payment_id))

    @router.get("/overview", response_model=CompanyOverview)
    async def overview(user=Depends(get_user)):
        return CompanyOverview(**await company_overview(db, user["id"]))

    @router.post("/cash", response_model=LedgerEntry)
    async def add_cash(data: CashIn, user=Depends(get_user)):
        doc = {**data.model_dump(mode="json", exclude={"amount", "request_id"}), "id": str(data.request_id), "user_id": user["id"], "amount_cents": cents(data.amount), "created_at": now()}
        try: await db.company_cash.insert_one(dict(doc))
        except DuplicateKeyError:
            previous = await owned(db, "company_cash", doc["id"], user["id"])
            if any(previous.get(k) != doc.get(k) for k in ("direction", "currency", "amount_cents", "date", "note")):
                raise HTTPException(409, "Aynı işlem anahtarı farklı bir hareket için kullanılamaz")
            doc = previous
        return LedgerEntry(**{**doc, "amount": cash(doc["amount_cents"]) * (1 if doc["direction"] == "in" else -1), "kind": "cash_" + doc["direction"]})

    @router.put("/cash/{cash_id}", response_model=LedgerEntry)
    async def edit_cash(cash_id: str, data: CashUpdateIn, user=Depends(get_user)):
        doc = await db.company_cash.find_one_and_update({"id": cash_id, "user_id": user["id"]}, {"$set": {**data.model_dump(mode="json", exclude={"amount"}), "amount_cents": cents(data.amount)}}, return_document=True, projection={"_id": 0})
        if not doc: raise HTTPException(404, "Kasa hareketi bulunamadı")
        return LedgerEntry(**{**doc, "amount": cash(doc["amount_cents"]) * (1 if doc["direction"] == "in" else -1), "kind": "cash_" + doc["direction"]})

    @router.delete("/cash/{cash_id}")
    async def remove_cash(cash_id: str, user=Depends(get_user)):
        result = await db.company_cash.delete_one({"id": cash_id, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Kasa hareketi bulunamadı")
        return {"ok": True}

    @router.post("/cash/bulk-delete")
    async def bulk_delete_cash(data: BulkIdsIn, user=Depends(get_user)):
        result = await db.company_cash.delete_many({"id": {"$in": list(dict.fromkeys(data.ids))}, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Silinecek kasa hareketi bulunamadı")
        return {"ok": True, "deleted": result.deleted_count}

    @router.get("/closings", response_model=list[ClosingOut])
    async def closings(user=Depends(get_user)):
        return [ClosingOut(**d) for d in await db.company_closings.find({"user_id": user["id"]}, {"_id": 0}).sort([("period", -1), ("store_name", 1)]).to_list(None)]

    @router.put("/closings/{closing_id}", response_model=ClosingOut)
    async def edit_closing(closing_id: str, data: ClosingUpdateIn, user=Depends(get_user)):
        changes = {key: value for key, value in data.model_dump().items() if value is not None}
        if not changes: raise HTTPException(400, "Güncellenecek alan seçin")
        if "net_profit" not in changes and ("revenue" in changes or "expenses" in changes):
            changes["net_profit"] = round(changes.get("revenue", 0) - changes.get("expenses", 0), 2)
        doc = await db.company_closings.find_one_and_update({"id": closing_id, "user_id": user["id"]}, {"$set": {**changes, "updated_at": now()}}, return_document=True, projection={"_id": 0})
        if not doc: raise HTTPException(404, "Kapanış kaydı bulunamadı")
        return ClosingOut(**doc)

    @router.delete("/closings/{closing_id}")
    async def remove_closing(closing_id: str, user=Depends(get_user)):
        result = await db.company_closings.delete_one({"id": closing_id, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Kapanış kaydı bulunamadı")
        return {"ok": True}

    @router.post("/closings/bulk-delete")
    async def bulk_delete_closings(data: BulkIdsIn, user=Depends(get_user)):
        result = await db.company_closings.delete_many({"id": {"$in": list(dict.fromkeys(data.ids))}, "user_id": user["id"]})
        if result.deleted_count == 0: raise HTTPException(404, "Silinecek kapanış kaydı bulunamadı")
        return {"ok": True, "deleted": result.deleted_count}

    @router.post("/closings/run", response_model=JobAccepted, status_code=202)
    async def close_now(background_tasks: BackgroundTasks, user=Depends(get_user)):
        return await queue_close(db, background_tasks, "manual:" + str(uuid.uuid4()), user["id"])

    @router.get("/jobs", response_model=list[JobOut])
    async def jobs(user=Depends(get_user)):
        return [JobOut(**d) for d in await db.company_jobs.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", -1).to_list(10)]

    @router.post("/cron/monthly-close", response_model=JobAccepted, status_code=202)
    async def scheduled_close(request: Request, background_tasks: BackgroundTasks):
        # Cron endpoints must ack 2xx immediately; enqueue/background the actual work.
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        if scheme.lower() != "bearer" or not supplied or not secrets.compare_digest(supplied.encode(), os.environ["WEBHOOK_CRON_SECRET"].encode()):
            raise HTTPException(401, "Unauthorized")
        try:
            envelope = CronEnvelope.model_validate(await request.json())
        except (ValueError, ValidationError):
            raise HTTPException(400, "Geçersiz zamanlama bildirimi")
        run_id = request.headers.get("x-webhook-id") or envelope.run_id
        if not run_id or len(run_id) > 200: raise HTTPException(400, "Geçerli run_id gerekli")
        return await queue_close(db, background_tasks, "cron:" + run_id)
    return router