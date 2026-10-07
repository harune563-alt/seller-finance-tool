"""Store-scoped custom transaction categories (income / expense) with FBA & PPC sections."""
import uuid
from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator

CategoryType = Literal["income", "expense"]
CategorySection = Literal["general", "fba", "ppc"]

# Default categories seeded per store on first access. These mirror the legacy
# hardcoded set so existing transactions keep working, with FBA / PPC additions.
DEFAULT_CATEGORIES = [
    # General (legacy)
    {"name": "Order payments", "type": "income", "section": "general", "color": "#059669", "icon": "shopping-cart", "is_system": True},
    {"name": "Refunds", "type": "expense", "section": "general", "color": "#f97316", "icon": "undo", "is_system": True},
    {"name": "Service Fees", "type": "expense", "section": "general", "color": "#64748b", "icon": "receipt", "is_system": True},
    # FBA
    {"name": "FBA Satış", "type": "income", "section": "fba", "color": "#0ea5e9", "icon": "package", "is_system": True},
    {"name": "FBA Depolama Ücreti", "type": "expense", "section": "fba", "color": "#f59e0b", "icon": "warehouse", "is_system": True},
    {"name": "FBA İşlem Ücreti", "type": "expense", "section": "fba", "color": "#ef4444", "icon": "box", "is_system": True},
    {"name": "FBA Uzun Vadeli Depolama", "type": "expense", "section": "fba", "color": "#dc2626", "icon": "archive", "is_system": True},
    {"name": "FBA İade / Removal", "type": "expense", "section": "fba", "color": "#7c3aed", "icon": "truck", "is_system": True},
    # PPC
    {"name": "PPC Reklam Harcaması", "type": "expense", "section": "ppc", "color": "#be185d", "icon": "megaphone", "is_system": True},
    {"name": "PPC Satışları (Attributed)", "type": "income", "section": "ppc", "color": "#16a34a", "icon": "trending-up", "is_system": True},
]


class CategoryIn(BaseModel):
    store_id: str
    name: str = Field(min_length=1, max_length=80)
    type: CategoryType
    section: CategorySection = "general"
    color: str = Field(default="#64748b", max_length=20)
    icon: str = Field(default="tag", max_length=40)
    archived: bool = False

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("İsim boş olamaz")
        return value


class CategoryOut(CategoryIn):
    id: str
    is_system: bool = False
    created_at: str


class CategoryPatchIn(BaseModel):
    name: Optional[str] = Field(default=None, min_length=1, max_length=80)
    type: Optional[CategoryType] = None
    section: Optional[CategorySection] = None
    color: Optional[str] = Field(default=None, max_length=20)
    icon: Optional[str] = Field(default=None, max_length=40)
    archived: Optional[bool] = None

    @field_validator("name")
    @classmethod
    def strip_name(cls, value):
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("İsim boş olamaz")
        return value


def _to_out(doc: dict) -> CategoryOut:
    return CategoryOut(**{k: doc.get(k) for k in CategoryOut.model_fields})


async def ensure_seeded(db, user_id: str, store_id: str) -> None:
    """Insert default categories for this store if none exist yet."""
    exists = await db.transaction_categories.find_one({"user_id": user_id, "store_id": store_id}, {"_id": 1})
    if exists:
        return
    now = datetime.now(timezone.utc).isoformat()
    docs = [
        {
            "id": str(uuid.uuid4()), "user_id": user_id, "store_id": store_id,
            "archived": False, "created_at": now, **template,
        }
        for template in DEFAULT_CATEGORIES
    ]
    if docs:
        await db.transaction_categories.insert_many(docs)


async def resolve_category(db, user_id: str, store_id: str, name: str) -> Optional[dict]:
    """Return the category document for a (store, name) pair or None."""
    return await db.transaction_categories.find_one(
        {"user_id": user_id, "store_id": store_id, "name": name}, {"_id": 0}
    )


def category_router(db, get_current_user) -> APIRouter:
    router = APIRouter(prefix="/categories", tags=["categories"])

    async def _owned_store(user, store_id: str):
        store = await db.stores.find_one({"id": store_id, "user_id": user["id"]}, {"_id": 0, "id": 1})
        if not store:
            raise HTTPException(404, "Mağaza bulunamadı")

    @router.get("", response_model=List[CategoryOut])
    async def list_categories(store_id: str, include_archived: bool = True, user=Depends(get_current_user)):
        await _owned_store(user, store_id)
        await ensure_seeded(db, user["id"], store_id)
        q = {"user_id": user["id"], "store_id": store_id}
        if not include_archived:
            q["archived"] = False
        docs = await db.transaction_categories.find(q, {"_id": 0}).sort([("section", 1), ("type", 1), ("name", 1)]).to_list(500)
        return [_to_out(d) for d in docs]

    @router.post("", response_model=CategoryOut)
    async def create_category(data: CategoryIn, user=Depends(get_current_user)):
        await _owned_store(user, data.store_id)
        await ensure_seeded(db, user["id"], data.store_id)
        existing = await resolve_category(db, user["id"], data.store_id, data.name)
        if existing:
            raise HTTPException(409, "Bu isimde bir kategori zaten var")
        doc = {
            "id": str(uuid.uuid4()), "user_id": user["id"], "is_system": False,
            "created_at": datetime.now(timezone.utc).isoformat(), **data.model_dump(),
        }
        await db.transaction_categories.insert_one(doc)
        return _to_out(doc)

    @router.put("/{category_id}", response_model=CategoryOut)
    async def update_category(category_id: str, data: CategoryPatchIn, user=Depends(get_current_user)):
        current = await db.transaction_categories.find_one(
            {"id": category_id, "user_id": user["id"]}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Kategori bulunamadı")
        updates = {k: v for k, v in data.model_dump(exclude_unset=True).items() if v is not None or k == "archived"}
        if not updates:
            raise HTTPException(422, "Güncellenecek alan belirtilmedi")
        if "name" in updates and updates["name"] != current["name"]:
            dup = await resolve_category(db, user["id"], current["store_id"], updates["name"])
            if dup:
                raise HTTPException(409, "Bu isimde bir kategori zaten var")
            # Rename all transactions using the old name so historic data stays linked.
            await db.transactions.update_many(
                {"user_id": user["id"], "store_id": current["store_id"], "category": current["name"]},
                {"$set": {"category": updates["name"]}},
            )
        doc = await db.transaction_categories.find_one_and_update(
            {"id": category_id, "user_id": user["id"]},
            {"$set": updates}, return_document=True, projection={"_id": 0},
        )
        return _to_out(doc)

    @router.delete("/{category_id}")
    async def delete_category(category_id: str, user=Depends(get_current_user)):
        current = await db.transaction_categories.find_one(
            {"id": category_id, "user_id": user["id"]}, {"_id": 0}
        )
        if not current:
            raise HTTPException(404, "Kategori bulunamadı")
        in_use = await db.transactions.find_one(
            {"user_id": user["id"], "store_id": current["store_id"], "category": current["name"]},
            {"_id": 1},
        )
        if in_use:
            raise HTTPException(409, "Bu kategoriyi kullanan işlemler var; önce arşivleyin veya işlemleri taşıyın")
        await db.transaction_categories.delete_one({"id": category_id, "user_id": user["id"]})
        return {"ok": True}

    return router


async def initialize_category_indexes(db):
    await db.transaction_categories.create_index(
        [("user_id", 1), ("store_id", 1), ("name", 1)], unique=True
    )
    await db.transaction_categories.create_index([("user_id", 1), ("store_id", 1), ("section", 1)])
