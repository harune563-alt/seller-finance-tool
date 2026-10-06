import os
import secrets
import uuid
from typing import Literal, Optional
from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request, Query
from pydantic import BaseModel, ValidationError
from pymongo.errors import DuplicateKeyError
from company.models import (PersonIn, PersonOut, CapitalIn, CapitalOut, DebtIn, DebtOut, AmountIn, CashIn,
                            CompanyOverview, LedgerEntry, ClosingOut, JobOut, JobAccepted)
from company.common import cash, cents, names, now, owned
from company.capital import post_capital, capital_summary
from company.treasury import create_debt, settle_debt, debt_output, company_overview
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

    @router.get("/capital", response_model=CapitalOut)
    async def capital(store_id: str, user=Depends(get_user)):
        return CapitalOut(**await capital_summary(db, user["id"], store_id))

    @router.post("/capital", response_model=CapitalOut)
    async def add_capital(data: CapitalIn, user=Depends(get_user)):
        await post_capital(db, user["id"], data)
        return CapitalOut(**await capital_summary(db, user["id"], data.store_id))

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

    @router.post("/debts/{debt_id}/payments", response_model=DebtOut)
    async def pay_debt(debt_id: str, data: AmountIn, user=Depends(get_user)):
        return DebtOut(**await settle_debt(db, user["id"], debt_id, data))

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

    @router.get("/closings", response_model=list[ClosingOut])
    async def closings(user=Depends(get_user)):
        return [ClosingOut(**d) for d in await db.company_closings.find({"user_id": user["id"]}, {"_id": 0}).sort([("period", -1), ("store_name", 1)]).to_list(None)]

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