from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import json
import csv
import uuid
import logging
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta, date as calendar_date
from typing import Any, List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File, Query
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict, field_validator
from pymongo import UpdateOne
from finance import COST_FIELDS, RECOVERY_FIELDS, CATEGORIES, money, summarize
from amazon_csv import parse_amazon_csv
from auth_security import check_login_limit, record_login_failure
from starlette.responses import JSONResponse
from proxy_origin import OriginAliasMiddleware
from fx_service import FxQuote, FxError, get_rate
from usd_ledger import attach_usd, enrich_records, summary_usd, FIELDS as USD_COST_FIELDS
from ledger_search import search_history
from company.routes import company_router
from company.common import initialize_indexes as initialize_company_indexes
from reporting import report_router

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

mongo_url = os.environ['MONGO_URL']
client = AsyncIOMotorClient(mongo_url)
db = client[os.environ['DB_NAME']]

JWT_SECRET = os.environ['JWT_SECRET']
JWT_ALGO = "HS256"
CORS_ORIGINS = [origin.strip().rstrip("/") for origin in os.environ["CORS_ORIGINS"].split(",") if origin.strip()]
CORS_ORIGIN_ALIASES = json.loads(os.environ["CORS_ORIGIN_ALIASES"])
if not CORS_ORIGINS or "*" in CORS_ORIGINS:
    raise RuntimeError("CORS_ORIGINS must contain explicit trusted origins")
if any(target not in CORS_ORIGINS for target in CORS_ORIGIN_ALIASES.values()):
    raise RuntimeError("Origin aliases must map to an explicitly trusted origin")

MARKETPLACES = {
    "US": {"name": "United States", "currency": "USD", "symbol": "$", "flag": "🇺🇸"},
    "CA": {"name": "Canada", "currency": "CAD", "symbol": "CA$", "flag": "🇨🇦"},
    "MX": {"name": "Mexico", "currency": "MXN", "symbol": "MX$", "flag": "🇲🇽"},
    "UK": {"name": "United Kingdom", "currency": "GBP", "symbol": "£", "flag": "🇬🇧"},
    "DE": {"name": "Germany", "currency": "EUR", "symbol": "€", "flag": "🇩🇪"},
    "FR": {"name": "France", "currency": "EUR", "symbol": "€", "flag": "🇫🇷"},
    "IT": {"name": "Italy", "currency": "EUR", "symbol": "€", "flag": "🇮🇹"},
    "ES": {"name": "Spain", "currency": "EUR", "symbol": "€", "flag": "🇪🇸"},
    "NL": {"name": "Netherlands", "currency": "EUR", "symbol": "€", "flag": "🇳🇱"},
    "SE": {"name": "Sweden", "currency": "SEK", "symbol": "kr", "flag": "🇸🇪"},
    "PL": {"name": "Poland", "currency": "PLN", "symbol": "zł", "flag": "🇵🇱"},
    "AU": {"name": "Australia", "currency": "AUD", "symbol": "A$", "flag": "🇦🇺"},
    "JP": {"name": "Japan", "currency": "JPY", "symbol": "¥", "flag": "🇯🇵"},
    "AE": {"name": "UAE", "currency": "AED", "symbol": "د.إ", "flag": "🇦🇪"},
    "SA": {"name": "Saudi Arabia", "currency": "SAR", "symbol": "﷼", "flag": "🇸🇦"},
    "TR": {"name": "Turkey", "currency": "TRY", "symbol": "₺", "flag": "🇹🇷"},
}

# ---------------------------------------------------------------------------
# Password + JWT helpers
# ---------------------------------------------------------------------------
def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")

def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("utf-8"))
    except Exception:
        return False

def create_access_token(user_id: str, email: str) -> str:
    payload = {
        "sub": user_id, "email": email, "type": "access",
        "exp": datetime.now(timezone.utc) + timedelta(days=7),
    }
    return jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGO)

async def get_current_user(request: Request) -> dict:
    token = request.cookies.get("access_token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            token = auth[7:]
    if not token:
        raise HTTPException(status_code=401, detail="Not authenticated")
    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGO])
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token expired")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Invalid token")
    user = await db.users.find_one({"id": payload["sub"]}, {"password_hash": 0, "_id": 0})
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return user

# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------
class RegisterIn(BaseModel):
    email: EmailStr
    password: str
    name: Optional[str] = None

class LoginIn(BaseModel):
    email: EmailStr
    password: str

class StoreIn(BaseModel):
    name: str
    marketplaces: List[str] = Field(default_factory=lambda: ["US"])
    default_currency: str = "USD"

class StoreOut(BaseModel):
    id: str
    name: str
    marketplaces: List[str]
    default_currency: str
    created_at: str

TxType = Literal["income", "expense", "payout"]

class CostsIn(BaseModel):
    product_cost: float = Field(default=0, ge=0, le=1000000000000, allow_inf_nan=False)
    shipping_cost: float = Field(default=0, ge=0, le=1000000000000, allow_inf_nan=False)
    extra_cost: float = Field(default=0, ge=0, le=1000000000000, allow_inf_nan=False)
    product_cost_recovery: float = Field(default=0, ge=0, le=1000000000000, allow_inf_nan=False)
    shipping_cost_recovery: float = Field(default=0, ge=0, le=1000000000000, allow_inf_nan=False)

    @field_validator("product_cost", "shipping_cost", "extra_cost", "product_cost_recovery", "shipping_cost_recovery")
    @classmethod
    def round_cost(cls, value):
        return float(money(value))


class TransactionIn(CostsIn):
    model_config = ConfigDict(extra="ignore")
    store_id: str
    marketplace: str
    type: TxType
    category: str
    amount: float = Field(gt=0, le=1000000000000, allow_inf_nan=False)
    currency: str
    date: str  # ISO date (YYYY-MM-DD)
    description: Optional[str] = ""
    order_id: Optional[str] = ""
    payment_reference: str = Field(default="", max_length=200)

    @field_validator("payment_reference", mode="before")
    @classmethod
    def normalize_payment_reference(cls, value):
        return value.strip() if isinstance(value, str) else value or ""

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        return calendar_date.fromisoformat(value).isoformat()

    @field_validator("amount")
    @classmethod
    def round_amount(cls, value):
        return float(money(value))

class TransactionOut(TransactionIn):
    amount: float = Field(allow_inf_nan=False)
    id: str
    created_at: str
    source: str = "manual"
    cost_currency: str
    fx: Optional[FxQuote] = None
    amount_usd: Optional[float] = None
    usd_costs: dict[str, float] = Field(default_factory=dict)
    fx_status: str
    fx_error: Optional[str] = None


class SummaryBucket(BaseModel):
    revenue: float
    expenses: float
    net: float


class MarketplaceBucket(SummaryBucket):
    marketplace: str


class TrendBucket(SummaryBucket):
    month: str


class CategoryBucket(BaseModel):
    category: str
    amount: float


class NativeBalance(BaseModel):
    currency: str
    amazon_balance: float
    payouts_received: float


class SummaryOut(CostsIn):
    revenue: Optional[float]
    expenses: Optional[float]
    net_profit: Optional[float]
    margin: Optional[float]
    transaction_count: int
    currency: str
    source_currency: str
    available_currencies: List[str]
    native_balances: List[NativeBalance]
    incomplete_count: int
    fx_errors: List[str]
    by_marketplace: List[MarketplaceBucket]
    by_category: List[CategoryBucket]
    trend: List[TrendBucket]


class ImportIssue(BaseModel):
    line: int
    reason: str


class ImportOut(BaseModel):
    accepted: int
    duplicates: int
    inserted: int
    rejected_count: int
    issues: List[ImportIssue]
    preview: List[TransactionOut]
    committed: bool


class HistoryOut(BaseModel):
    items: List[TransactionOut]
    total: int
    page: int
    page_size: int
    total_pages: int


class PaymentReferenceIn(BaseModel):
    payment_reference: str = Field(max_length=200)

    @field_validator("payment_reference")
    @classmethod
    def trim_reference(cls, value):
        return value.strip()


class BulkDeleteIn(BaseModel):
    ids: List[str] = Field(min_length=1, max_length=100)


class BulkChangesIn(BulkDeleteIn):
    changes: dict[str, Any] = Field(min_length=1, max_length=20)


# ---------------------------------------------------------------------------
# App & Router
# ---------------------------------------------------------------------------
app = FastAPI(title="Amazon Seller Finance Suite")
api = APIRouter(prefix="/api")

# ------------------ Auth ------------------
@api.post("/auth/register")
async def register(data: RegisterIn, response: Response):
    email = data.email.lower()
    if await db.users.find_one({"email": email}):
        raise HTTPException(status_code=400, detail="Bu e-posta zaten kayıtlı")
    uid = str(uuid.uuid4())
    user = {
        "id": uid, "email": email, "name": data.name or email.split("@")[0],
        "password_hash": hash_password(data.password),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.users.insert_one(user)
    token = create_access_token(uid, email)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return {"id": uid, "email": email, "name": user["name"], "token": token}

@api.post("/auth/login")
async def login(data: LoginIn, response: Response, request: Request):
    email = data.email.lower()
    identifier = f"account:{email}"
    await check_login_limit(db, identifier)
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        await record_login_failure(db, identifier)
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı")
    await db.login_attempts.delete_one({"identifier": identifier})
    token = create_access_token(user["id"], email)
    response.set_cookie("access_token", token, httponly=True, secure=True, samesite="none", max_age=604800, path="/")
    return {"id": user["id"], "email": email, "name": user.get("name", ""), "token": token}

@api.post("/auth/logout")
async def logout(response: Response, _user=Depends(get_current_user)):
    response.delete_cookie("access_token", path="/")
    return {"ok": True}

@api.get("/auth/me")
async def me(user=Depends(get_current_user)):
    return {"id": user["id"], "email": user["email"], "name": user.get("name", "")}

# ------------------ Marketplaces ------------------
@api.get("/marketplaces")
async def list_marketplaces():
    return [{"code": c, **info} for c, info in MARKETPLACES.items()]


@api.get("/fx/to-usd", response_model=FxQuote)
async def fx_to_usd(currency: str, date: str, user=Depends(get_current_user)):
    try:
        return FxQuote(**await get_rate(db, currency, date))
    except FxError as exc:
        raise HTTPException(422, str(exc))

# ------------------ Stores ------------------
@api.post("/stores", response_model=StoreOut)
async def create_store(data: StoreIn, user=Depends(get_current_user)):
    sid = str(uuid.uuid4())
    doc = {
        "id": sid, "user_id": user["id"], "name": data.name,
        "marketplaces": data.marketplaces, "default_currency": data.default_currency,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.stores.insert_one(doc)
    return StoreOut(**{k: doc[k] for k in StoreOut.model_fields})

@api.get("/stores", response_model=List[StoreOut])
async def list_stores(user=Depends(get_current_user)):
    docs = await db.stores.find({"user_id": user["id"]}, {"_id": 0}).sort("created_at", 1).to_list(500)
    return [StoreOut(**{k: d.get(k) for k in StoreOut.model_fields}) for d in docs]

@api.put("/stores/{store_id}", response_model=StoreOut)
async def update_store(store_id: str, data: StoreIn, user=Depends(get_current_user)):
    res = await db.stores.find_one_and_update(
        {"id": store_id, "user_id": user["id"]},
        {"$set": {"name": data.name, "marketplaces": data.marketplaces, "default_currency": data.default_currency}},
        return_document=True,
    )
    if not res:
        raise HTTPException(404, "Mağaza bulunamadı")
    return StoreOut(**{k: res.get(k) for k in StoreOut.model_fields})

@api.delete("/stores/{store_id}")
async def delete_store(store_id: str, user=Depends(get_current_user)):
    scope = {"store_id": store_id, "user_id": user["id"]}
    capital = await db.company_capital.find_one({**scope, "entries.0": {"$exists": True}}, {"_id": 0, "store_id": 1})
    debt = await db.company_debts.find_one(scope, {"_id": 0, "id": 1})
    closing = await db.company_closings.find_one(scope, {"_id": 0, "id": 1})
    if capital or debt or closing:
        raise HTTPException(409, "Sermaye, borç veya kapanış geçmişi olan mağaza silinemez; şirket kayıtları korunmalıdır")
    r = await db.stores.delete_one({"id": store_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Mağaza bulunamadı")
    await db.transactions.delete_many({"store_id": store_id, "user_id": user["id"]})
    return {"ok": True}

@api.post("/stores/bulk-delete")
async def bulk_delete_stores(data: BulkDeleteIn, user=Depends(get_current_user)):
    ids = list(dict.fromkeys(data.ids))
    blocked = await db.company_capital.find_one({"user_id": user["id"], "store_id": {"$in": ids}, "entries.0": {"$exists": True}}) or await db.company_debts.find_one({"user_id": user["id"], "store_id": {"$in": ids}}) or await db.company_closings.find_one({"user_id": user["id"], "store_id": {"$in": ids}})
    if blocked:
        raise HTTPException(409, "Sermaye, borç veya kapanış geçmişi olan seçili mağazalar silinemez")
    result = await db.stores.delete_many({"id": {"$in": ids}, "user_id": user["id"]})
    if result.deleted_count == 0: raise HTTPException(404, "Silinecek mağaza bulunamadı")
    await db.transactions.delete_many({"store_id": {"$in": ids}, "user_id": user["id"]})
    return {"ok": True, "deleted": result.deleted_count}

@api.post("/stores/bulk-update")
async def bulk_update_stores(data: BulkChangesIn, user=Depends(get_current_user)):
    allowed = {"name", "marketplaces", "default_currency"}
    unknown = set(data.changes) - allowed
    if unknown: raise HTTPException(422, f"Toplu mağaza güncellemesinde desteklenmeyen alan: {sorted(unknown)[0]}")
    ids = list(dict.fromkeys(data.ids))
    docs = await db.stores.find({"id": {"$in": ids}, "user_id": user["id"]}, {"_id": 0}).to_list(len(ids))
    if len(docs) != len(ids): raise HTTPException(404, "Seçilen mağazalardan biri bulunamadı")
    for doc in docs:
        merged = {"name": doc["name"], "marketplaces": doc["marketplaces"], "default_currency": doc["default_currency"]}
        merged.update(data.changes)
        validated = StoreIn(**merged)
        await db.stores.update_one({"id": doc["id"], "user_id": user["id"]}, {"$set": validated.model_dump()})
    return {"ok": True, "updated": len(ids), "ids": ids}


async def validate_transaction(data: TransactionIn, user):
    store = await db.stores.find_one({"id": data.store_id, "user_id": user["id"]}, {"_id": 0})
    if not store:
        raise HTTPException(400, "Geçersiz mağaza")
    if data.marketplace not in store["marketplaces"] or data.marketplace not in MARKETPLACES:
        raise HTTPException(400, "Bu pazar yeri seçili mağazaya ait değil")
    if data.currency != MARKETPLACES[data.marketplace]["currency"]:
        raise HTTPException(400, "Para birimi pazar yeriyle uyuşmuyor")
    if data.amount <= 0:
        raise HTTPException(400, "Tutar en az 0.01 olmalıdır")
    if data.type == "payout":
        if data.category not in ("Oluşturuldu", "İşleniyor", "Bankada"):
            raise HTTPException(400, "Geçersiz ödeme durumu")
    elif CATEGORIES.get(data.category) != data.type:
        raise HTTPException(400, "Order payments gelir; Refunds ve Service Fees gider olarak kaydedilir")
    if data.type != "income" and any(getattr(data, key) for key in COST_FIELDS):
        raise HTTPException(400, "Maliyetler yalnızca gelir kaydına eklenebilir")
    if data.type != "payout" and data.payment_reference:
        raise HTTPException(400, "Ödeme referansı yalnızca Amazon ödemelerine eklenebilir")
    if data.category != "Refunds" and any(getattr(data, key) for key in RECOVERY_FIELDS):
        raise HTTPException(400, "Geri kazanımlar yalnızca Refunds kaydına eklenebilir")


@api.post("/transactions", response_model=TransactionOut)
async def create_transaction(data: TransactionIn, user=Depends(get_current_user)):
    await validate_transaction(data, user)
    tid = str(uuid.uuid4())
    doc = {
        "id": tid, "user_id": user["id"], **data.model_dump(),
        "cost_currency": "USD",
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        doc = await attach_usd(db, doc)
    except FxError as exc:
        raise HTTPException(422, str(exc))
    await db.transactions.insert_one(doc)
    return TransactionOut(**{k: v for k, v in doc.items() if k not in ("_id", "user_id")})

@api.get("/transactions", response_model=List[TransactionOut])
async def list_transactions(
    user=Depends(get_current_user),
    store_id: Optional[str] = None,
    marketplace: Optional[str] = None,
    type: Optional[str] = None,
    currency: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = Query(500, ge=1, le=10000),
):
    q = {"user_id": user["id"]}
    if store_id: q["store_id"] = store_id
    if marketplace and marketplace != "ALL": q["marketplace"] = marketplace
    if type: q["type"] = type
    else: q["type"] = {"$in": ["income", "expense", "payout"]}
    if currency and currency != "ALL": q["currency"] = currency
    if start_date or end_date:
        q["date"] = {}
        if start_date: q["date"]["$gte"] = start_date
        if end_date: q["date"]["$lte"] = end_date
    docs = await db.transactions.find(q, {"_id": 0}).sort("date", -1).to_list(limit)
    enriched = await enrich_records(db, docs)
    return [TransactionOut(**d) for d in enriched]


@api.get("/transactions/search", response_model=HistoryOut)
async def search_transactions(
    user=Depends(get_current_user), store_id: str = Query(...),
    marketplace: Optional[str] = None, currency: Optional[str] = None,
    view: Literal["orders", "payouts"] = "orders", search: str = Query("", max_length=200),
    category: Optional[str] = None, start_date: Optional[calendar_date] = None, end_date: Optional[calendar_date] = None,
    outcome: Literal["all", "profit", "loss"] = "all", page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(422, "Başlangıç tarihi bitiş tarihinden sonra olamaz")
    scope = {"user_id": user["id"], "store_id": store_id}
    if marketplace and marketplace != "ALL": scope["marketplace"] = marketplace
    if currency and currency != "ALL": scope["currency"] = currency
    # Existing legacy category names remain searchable; the UI shows current categories.
    if category and len(category) > 200:
        raise HTTPException(422, "Geçersiz işlem türü")
    result = await search_history(db, scope, view, search, category, start_date.isoformat() if start_date else None,
                                  end_date.isoformat() if end_date else None, outcome, page, page_size)
    return HistoryOut(**{**result, "items": [TransactionOut(**row) for row in result["items"]]})


@api.put("/transactions/{tx_id}", response_model=TransactionOut)
async def update_transaction(tx_id: str, data: TransactionIn, user=Depends(get_current_user)):
    existing = await db.transactions.find_one({"id": tx_id, "user_id": user["id"]}, {"_id": 0})
    if not existing:
        raise HTTPException(404, "İşlem bulunamadı")
    await validate_transaction(data, user)
    candidate = {
        "id": tx_id, "user_id": user["id"], **data.model_dump(),
        "cost_currency": "USD", "created_at": existing.get("created_at", datetime.now(timezone.utc).isoformat()),
    }
    try:
        enriched = await attach_usd(db, candidate)
    except FxError as exc:
        raise HTTPException(422, str(exc))
    changes = {key: value for key, value in enriched.items() if key not in ("id", "user_id", "created_at", "_id")}
    doc = await db.transactions.find_one_and_update(
        {"id": tx_id, "user_id": user["id"]}, {"$set": changes}, return_document=True, projection={"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "İşlem bulunamadı")
    return TransactionOut(**doc)


@api.post("/transactions/bulk-delete")
async def bulk_delete_transactions(data: BulkDeleteIn, user=Depends(get_current_user)):
    ids = list(dict.fromkeys(data.ids))
    result = await db.transactions.delete_many({"id": {"$in": ids}, "user_id": user["id"]})
    if result.deleted_count == 0:
        raise HTTPException(404, "Silinecek işlem bulunamadı")
    return {"ok": True, "deleted": result.deleted_count}


@api.post("/transactions/bulk-update")
async def bulk_update_transactions(data: BulkChangesIn, user=Depends(get_current_user)):
    allowed = set(TransactionIn.model_fields)
    unknown = set(data.changes) - allowed
    if unknown: raise HTTPException(422, f"Toplu işlem güncellemesinde desteklenmeyen alan: {sorted(unknown)[0]}")
    ids = list(dict.fromkeys(data.ids))
    docs = await db.transactions.find({"id": {"$in": ids}, "user_id": user["id"]}, {"_id": 0}).to_list(len(ids))
    if len(docs) != len(ids): raise HTTPException(404, "Seçilen işlemlerden biri bulunamadı")
    recalculated = {"store_id", "marketplace", "type", "category", "amount", "currency", "date", *COST_FIELDS, *RECOVERY_FIELDS}
    prepared = []
    for existing in docs:
        base = {key: existing.get(key) for key in TransactionIn.model_fields}
        for key in (*COST_FIELDS, *RECOVERY_FIELDS): base[key] = existing.get(key, 0)
        for key in ("description", "order_id", "payment_reference"): base[key] = existing.get(key, "")
        base.update(data.changes)
        merged = TransactionIn(**base)
        await validate_transaction(merged, user)
        candidate = {"id": existing["id"], "user_id": user["id"], **merged.model_dump(), "cost_currency": existing.get("cost_currency", "USD"), "created_at": existing.get("created_at", datetime.now(timezone.utc).isoformat())}
        if recalculated.intersection(data.changes):
            candidate["fx"] = None
            candidate.pop("amount_usd", None)
            candidate.pop("usd_costs", None)
            if any(key in data.changes for key in (*COST_FIELDS, *RECOVERY_FIELDS)): candidate["cost_currency"] = "USD"
        try:
            prepared.append(await attach_usd(db, candidate))
        except FxError as exc:
            raise HTTPException(422, str(exc))
    for document in prepared:
        changes = {key: value for key, value in document.items() if key not in ("id", "user_id", "created_at", "_id")}
        await db.transactions.update_one({"id": document["id"], "user_id": user["id"]}, {"$set": changes})
    return {"ok": True, "updated": len(prepared), "ids": ids}


@api.patch("/payouts/{tx_id}/reference", response_model=TransactionOut)
async def update_payment_reference(tx_id: str, data: PaymentReferenceIn, user=Depends(get_current_user)):
    doc = await db.transactions.find_one_and_update(
        {"id": tx_id, "user_id": user["id"], "type": "payout"}, {"$set": data.model_dump()},
        return_document=True, projection={"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "Ödeme kaydı bulunamadı")
    return TransactionOut(**await attach_usd(db, doc))


@api.patch("/transactions/{tx_id}/costs", response_model=TransactionOut)
async def update_transaction_costs(tx_id: str, data: CostsIn, user=Depends(get_current_user)):
    existing = await db.transactions.find_one({"id": tx_id, "user_id": user["id"]}, {"_id": 0})
    if not existing or (existing["type"] != "income" and existing["category"] != "Refunds"):
        raise HTTPException(404, "Gelir veya iade kaydı bulunamadı")
    if existing["type"] != "income" and any(getattr(data, key) for key in COST_FIELDS):
        raise HTTPException(400, "İade kaydına yeni ürün/kargo maliyeti eklenemez")
    if existing["category"] != "Refunds" and any(getattr(data, key) for key in RECOVERY_FIELDS):
        raise HTTPException(400, "Geri kazanımlar yalnızca Refunds kaydına eklenebilir")
    try:
        existing = await attach_usd(db, existing, persist=True)
    except FxError as exc:
        raise HTTPException(422, str(exc))
    changes = {**data.model_dump(), "cost_currency": "USD", "usd_costs": data.model_dump()}
    if existing.get("cost_currency") != "USD" and not existing.get("original_costs"):
        changes["original_costs"] = {"currency": existing["cost_currency"], **{key: existing.get(key, 0) for key in USD_COST_FIELDS}}
    doc = await db.transactions.find_one_and_update(
        {"id": tx_id, "user_id": user["id"]},
        {"$set": changes}, return_document=True, projection={"_id": 0},
    )
    if not doc:
        raise HTTPException(404, "İşlem bulunamadı")
    return TransactionOut(**await attach_usd(db, doc))

@api.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str, user=Depends(get_current_user)):
    r = await db.transactions.delete_one({"id": tx_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "İşlem bulunamadı")
    return {"ok": True}

# ------------------ Dashboard ------------------
@api.get("/dashboard/summary", response_model=SummaryOut)
async def dashboard_summary(
    user=Depends(get_current_user),
    store_id: Optional[str] = None,
    marketplace: Optional[str] = None,
    currency: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
):
    q = {"user_id": user["id"]}
    if store_id: q["store_id"] = store_id
    if marketplace and marketplace != "ALL": q["marketplace"] = marketplace
    if start_date or end_date:
        q["date"] = {}
        if start_date: q["date"]["$gte"] = start_date
        if end_date: q["date"]["$lte"] = end_date

    if start_date and end_date and start_date > end_date:
        raise HTTPException(400, "Başlangıç tarihi bitişten sonra olamaz")
    available = sorted(await db.transactions.distinct("currency", q))
    chosen = currency or "ALL"
    if chosen != "ALL" and chosen not in {mp["currency"] for mp in MARKETPLACES.values()}:
        raise HTTPException(400, "Geçersiz para birimi")
    if chosen != "ALL":
        q["currency"] = chosen
    txs = await db.transactions.find(q, {"_id": 0}).to_list(None)
    enriched = await enrich_records(db, txs)
    return SummaryOut(**summary_usd(enriched), currency="USD", source_currency=chosen, available_currencies=available)

# ------------------ CSV Import ------------------
@api.post("/transactions/import", response_model=ImportOut)
async def import_csv(
    file: UploadFile = File(...),
    store_id: str = Query(...),
    marketplace: str = Query(...),
    commit: bool = False,
    user=Depends(get_current_user),
):
    store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0})
    if not store:
        raise HTTPException(400, "Mağaza bulunamadı")

    if marketplace not in store["marketplaces"] or marketplace not in MARKETPLACES:
        raise HTTPException(400, "Geçerli bir pazar yeri seçin")
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(400, "CSV dosyası seçin")
    content = await file.read(5 * 1024 * 1024 + 1)
    await file.close()
    if len(content) > 5 * 1024 * 1024:
        raise HTTPException(413, "Dosya en fazla 5 MB olabilir")
    try:
        docs, issues = parse_amazon_csv(content, marketplace, MARKETPLACES[marketplace]["currency"])
    except (ValueError, UnicodeError, csv.Error) as exc:
        raise HTTPException(400, f"CSV okunamadı: {exc}")
    scope = {"user_id": user["id"], "store_id": store_id}
    fingerprints = [d["source_fingerprint"] for d in docs]
    existing = set(await db.transactions.distinct("source_fingerprint", {**scope, "source_fingerprint": {"$in": fingerprints}}))
    for doc in docs:
        doc.update(scope, id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat(), cost_currency="USD")
    try:
        docs = await enrich_records(db, docs, persist=False, strict=True)
    except FxError as exc:
        raise HTTPException(422, str(exc))
    inserted = 0
    if commit and docs:
        result = await db.transactions.bulk_write([
            UpdateOne({**scope, "source_fingerprint": d["source_fingerprint"]}, {"$setOnInsert": d}, upsert=True) for d in docs
        ], ordered=False)
        inserted = result.upserted_count
    return ImportOut(accepted=len(docs), duplicates=len(docs) - inserted if commit else sum(d["source_fingerprint"] in existing for d in docs),
                     inserted=inserted, rejected_count=len(issues), issues=issues[:100],
                     preview=[TransactionOut(**d) for d in docs[:20]], committed=commit)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
api.include_router(company_router(db, get_current_user))
api.include_router(report_router(db, get_current_user))
app.include_router(api)

@app.middleware("http")
async def check_cookie_origin(request: Request, call_next):
    origin = request.headers.get("origin")
    if request.method in {"POST", "PUT", "PATCH", "DELETE"} and request.cookies.get("access_token") and origin and origin not in CORS_ORIGINS:
        return JSONResponse(status_code=403, content={"detail": "İzin verilmeyen istek kaynağı"})
    return await call_next(request)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=CORS_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(OriginAliasMiddleware, aliases=CORS_ORIGIN_ALIASES)

@app.on_event("startup")
async def startup():
    await initialize_company_indexes(db)
    await db.users.create_index("email", unique=True)
    await db.fx_rates.create_index([("source", 1), ("base", 1), ("quote", 1), ("requested_date", 1)], unique=True)
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.stores.create_index("user_id")
    await db.transactions.create_index([("user_id", 1), ("date", -1)])
    await db.transactions.create_index([("user_id", 1), ("store_id", 1), ("type", 1), ("date", -1)])
    await db.transactions.create_index([("user_id", 1), ("store_id", 1), ("source_fingerprint", 1)], unique=True,
                                       partialFilterExpression={"source_fingerprint": {"$type": "string"}})

    # seed admin
    admin_email = os.environ.get("ADMIN_EMAIL", "admin@amzsuite.com").lower()
    admin_password = os.environ.get("ADMIN_PASSWORD", "admin123")
    existing = await db.users.find_one({"email": admin_email})
    if not existing:
        uid = str(uuid.uuid4())
        await db.users.insert_one({
            "id": uid, "email": admin_email, "name": "Admin",
            "password_hash": hash_password(admin_password),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        logger.info(f"Admin user seeded: {admin_email}")
    elif not verify_password(admin_password, existing["password_hash"]):
        await db.users.update_one(
            {"email": admin_email},
            {"$set": {"password_hash": hash_password(admin_password)}}
        )

@app.on_event("shutdown")
async def shutdown():
    client.close()
