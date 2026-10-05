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
from typing import List, Optional, Literal

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


class SummaryOut(CostsIn):
    revenue: float
    expenses: float
    net_profit: float
    margin: float
    amazon_balance: float
    payouts_received: float
    transaction_count: int
    currency: str
    available_currencies: List[str]
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
    r = await db.stores.delete_one({"id": store_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "Mağaza bulunamadı")
    await db.transactions.delete_many({"store_id": store_id, "user_id": user["id"]})
    return {"ok": True}

# ------------------ Transactions ------------------
@api.post("/transactions", response_model=TransactionOut)
async def create_transaction(data: TransactionIn, user=Depends(get_current_user)):
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
    if data.category != "Refunds" and any(getattr(data, key) for key in RECOVERY_FIELDS):
        raise HTTPException(400, "Geri kazanımlar yalnızca Refunds kaydına eklenebilir")
    tid = str(uuid.uuid4())
    doc = {
        "id": tid, "user_id": user["id"], **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
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
    if currency: q["currency"] = currency
    if start_date or end_date:
        q["date"] = {}
        if start_date: q["date"]["$gte"] = start_date
        if end_date: q["date"]["$lte"] = end_date
    docs = await db.transactions.find(q, {"_id": 0, "user_id": 0}).sort("date", -1).to_list(limit)
    return [TransactionOut(**d) for d in docs]


@api.patch("/transactions/{tx_id}/costs", response_model=TransactionOut)
async def update_transaction_costs(tx_id: str, data: CostsIn, user=Depends(get_current_user)):
    existing = await db.transactions.find_one({"id": tx_id, "user_id": user["id"]}, {"_id": 0})
    if not existing or (existing["type"] != "income" and existing["category"] != "Refunds"):
        raise HTTPException(404, "Gelir veya iade kaydı bulunamadı")
    if existing["type"] != "income" and any(getattr(data, key) for key in COST_FIELDS):
        raise HTTPException(400, "İade kaydına yeni ürün/kargo maliyeti eklenemez")
    if existing["category"] != "Refunds" and any(getattr(data, key) for key in RECOVERY_FIELDS):
        raise HTTPException(400, "Geri kazanımlar yalnızca Refunds kaydına eklenebilir")
    doc = await db.transactions.find_one_and_update(
        {"id": tx_id, "user_id": user["id"]},
        {"$set": data.model_dump()}, return_document=True, projection={"_id": 0, "user_id": 0},
    )
    if not doc:
        raise HTTPException(404, "İşlem bulunamadı")
    return TransactionOut(**doc)

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
    store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0}) if store_id else None
    default = MARKETPLACES.get(marketplace, {}).get("currency") or (store or {}).get("default_currency")
    chosen = currency or (default if default in available else (available[0] if available else default))
    chosen = chosen or "USD"
    if chosen not in {mp["currency"] for mp in MARKETPLACES.values()}:
        raise HTTPException(400, "Geçersiz para birimi")
    q["currency"] = chosen
    txs = await db.transactions.find(q, {"_id": 0, "user_id": 0}).to_list(None)
    return SummaryOut(**summarize(txs), currency=chosen, available_currencies=sorted(set(available + [chosen])))

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
        doc.update(scope, id=str(uuid.uuid4()), created_at=datetime.now(timezone.utc).isoformat())
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
    await db.users.create_index("email", unique=True)
    await db.login_attempts.create_index("identifier", unique=True)
    await db.login_attempts.create_index("expires_at", expireAfterSeconds=0)
    await db.stores.create_index("user_id")
    await db.transactions.create_index([("user_id", 1), ("date", -1)])
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
