from dotenv import load_dotenv
from pathlib import Path

ROOT_DIR = Path(__file__).parent
load_dotenv(ROOT_DIR / '.env')

import os
import io
import csv
import uuid
import logging
import bcrypt
import jwt
import pandas as pd
from datetime import datetime, timezone, timedelta
from typing import List, Optional, Literal

from fastapi import FastAPI, APIRouter, HTTPException, Depends, Request, Response, UploadFile, File
from starlette.middleware.cors import CORSMiddleware
from motor.motor_asyncio import AsyncIOMotorClient
from pydantic import BaseModel, Field, EmailStr, ConfigDict

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

class TransactionIn(BaseModel):
    model_config = ConfigDict(extra="ignore")
    store_id: str
    marketplace: str
    type: TxType
    category: str
    amount: float
    currency: str
    date: str  # ISO date (YYYY-MM-DD)
    description: Optional[str] = ""
    order_id: Optional[str] = ""
    sku: Optional[str] = ""

class TransactionOut(TransactionIn):
    id: str
    created_at: str

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
async def login(data: LoginIn, response: Response):
    email = data.email.lower()
    user = await db.users.find_one({"email": email})
    if not user or not verify_password(data.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="E-posta veya şifre hatalı")
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
    store = await db.stores.find_one({"id": data.store_id, "user_id": user["id"]})
    if not store:
        raise HTTPException(400, "Geçersiz mağaza")
    tid = str(uuid.uuid4())
    doc = {
        "id": tid, "user_id": user["id"], **data.model_dump(),
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    await db.transactions.insert_one(doc)
    doc.pop("user_id", None)
    return TransactionOut(**doc)

@api.get("/transactions", response_model=List[TransactionOut])
async def list_transactions(
    user=Depends(get_current_user),
    store_id: Optional[str] = None,
    marketplace: Optional[str] = None,
    type: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 500,
):
    q = {"user_id": user["id"]}
    if store_id: q["store_id"] = store_id
    if marketplace and marketplace != "ALL": q["marketplace"] = marketplace
    if type: q["type"] = type
    if start_date or end_date:
        q["date"] = {}
        if start_date: q["date"]["$gte"] = start_date
        if end_date: q["date"]["$lte"] = end_date
    docs = await db.transactions.find(q, {"_id": 0, "user_id": 0}).sort("date", -1).to_list(limit)
    return [TransactionOut(**d) for d in docs]

@api.delete("/transactions/{tx_id}")
async def delete_transaction(tx_id: str, user=Depends(get_current_user)):
    r = await db.transactions.delete_one({"id": tx_id, "user_id": user["id"]})
    if r.deleted_count == 0:
        raise HTTPException(404, "İşlem bulunamadı")
    return {"ok": True}

# ------------------ Dashboard ------------------
@api.get("/dashboard/summary")
async def dashboard_summary(
    user=Depends(get_current_user),
    store_id: Optional[str] = None,
    marketplace: Optional[str] = None,
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

    txs = await db.transactions.find(q, {"_id": 0, "user_id": 0}).to_list(10000)

    revenue = sum(t["amount"] for t in txs if t["type"] == "income")
    expenses = sum(t["amount"] for t in txs if t["type"] == "expense")
    payouts = sum(t["amount"] for t in txs if t["type"] == "payout")
    net_profit = revenue - expenses
    margin = (net_profit / revenue * 100) if revenue > 0 else 0.0
    # amazon balance = (revenue - expenses) - payouts_received (what's still pending on Amazon)
    amazon_balance = (revenue - expenses) - payouts

    # by marketplace
    by_mp = {}
    for t in txs:
        mp = t["marketplace"]
        if mp not in by_mp:
            by_mp[mp] = {"revenue": 0, "expenses": 0, "net": 0}
        if t["type"] == "income":
            by_mp[mp]["revenue"] += t["amount"]
        elif t["type"] == "expense":
            by_mp[mp]["expenses"] += t["amount"]
    for mp in by_mp:
        by_mp[mp]["net"] = by_mp[mp]["revenue"] - by_mp[mp]["expenses"]

    # by category (expenses)
    by_cat = {}
    for t in txs:
        if t["type"] == "expense":
            by_cat[t["category"]] = by_cat.get(t["category"], 0) + t["amount"]

    # trend by month
    trend = {}
    for t in txs:
        month = t["date"][:7] if t.get("date") else ""
        if not month: continue
        if month not in trend:
            trend[month] = {"month": month, "revenue": 0, "expenses": 0, "net": 0}
        if t["type"] == "income":
            trend[month]["revenue"] += t["amount"]
        elif t["type"] == "expense":
            trend[month]["expenses"] += t["amount"]
    trend_list = sorted(trend.values(), key=lambda x: x["month"])
    for row in trend_list:
        row["net"] = row["revenue"] - row["expenses"]

    return {
        "revenue": round(revenue, 2),
        "expenses": round(expenses, 2),
        "net_profit": round(net_profit, 2),
        "margin": round(margin, 2),
        "amazon_balance": round(amazon_balance, 2),
        "payouts_received": round(payouts, 2),
        "transaction_count": len(txs),
        "by_marketplace": [{"marketplace": k, **v} for k, v in by_mp.items()],
        "by_category": [{"category": k, "amount": round(v, 2)} for k, v in by_cat.items()],
        "trend": trend_list,
    }

# ------------------ CSV Import ------------------
@api.post("/transactions/import")
async def import_csv(
    file: UploadFile = File(...),
    store_id: str = "",
    type: str = "income",
    user=Depends(get_current_user),
):
    if type not in ("income", "expense", "payout"):
        raise HTTPException(400, "Geçersiz tür")
    store = await db.stores.find_one({"id": store_id, "user_id": user["id"]})
    if not store:
        raise HTTPException(400, "Mağaza bulunamadı")

    content = await file.read()
    try:
        df = pd.read_csv(io.BytesIO(content))
    except Exception:
        try:
            df = pd.read_csv(io.BytesIO(content), sep=";")
        except Exception as e:
            raise HTTPException(400, f"CSV okunamadı: {e}")

    df.columns = [c.strip().lower() for c in df.columns]
    required = {"date", "amount"}
    if not required.issubset(set(df.columns)):
        raise HTTPException(400, "CSV en az 'date' ve 'amount' sütunlarını içermelidir")

    inserted = 0
    docs = []
    for _, row in df.iterrows():
        try:
            amount = float(row.get("amount", 0))
        except Exception:
            continue
        mp = str(row.get("marketplace", store.get("marketplaces", ["US"])[0])).upper()
        if mp not in MARKETPLACES:
            mp = store.get("marketplaces", ["US"])[0]
        docs.append({
            "id": str(uuid.uuid4()), "user_id": user["id"], "store_id": store_id,
            "marketplace": mp, "type": type,
            "category": str(row.get("category", "Diğer")),
            "amount": amount,
            "currency": str(row.get("currency", MARKETPLACES[mp]["currency"])).upper(),
            "date": str(row.get("date"))[:10],
            "description": str(row.get("description", "")),
            "order_id": str(row.get("order_id", "")),
            "sku": str(row.get("sku", "")),
            "created_at": datetime.now(timezone.utc).isoformat(),
        })
        inserted += 1
    if docs:
        await db.transactions.insert_many(docs)
    return {"inserted": inserted}

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app.include_router(api)

app.add_middleware(
    CORSMiddleware,
    allow_credentials=True,
    allow_origins=os.environ.get('CORS_ORIGINS', '*').split(','),
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup():
    await db.users.create_index("email", unique=True)
    await db.stores.create_index("user_id")
    await db.transactions.create_index([("user_id", 1), ("date", -1)])

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
