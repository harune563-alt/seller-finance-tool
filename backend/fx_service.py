"""Historical USD quotes. The public service receives only currency and date."""
import asyncio
import os
from datetime import date, datetime, timezone
from decimal import Decimal
import httpx
from pydantic import BaseModel
from pymongo.errors import DuplicateKeyError

SUPPORTED = {"USD", "CAD", "MXN", "GBP", "EUR", "AUD", "JPY", "AED", "SAR", "TRY", "SEK", "PLN"}
_locks = [asyncio.Lock() for _ in range(64)]


class FxError(Exception):
    pass


class FxQuote(BaseModel):
    base: str
    quote: str = "USD"
    rate: str
    requested_date: str
    rate_date: str
    source: str
    fetched_at: str


async def get_rate(db, currency, requested_date):
    try:
        requested = date.fromisoformat(requested_date)
    except (ValueError, TypeError):
        raise FxError("Geçerli bir işlem tarihi seçin")
    if requested > datetime.now(timezone.utc).date():
        raise FxError("Gelecek tarih için yayımlanmış kur yok")
    if currency not in SUPPORTED:
        raise FxError("Bu para birimi için otomatik kur desteklenmiyor")
    if currency == "USD":
        return FxQuote(base="USD", rate="1", requested_date=requested_date, rate_date=requested_date,
                       source="identity", fetched_at=datetime.now(timezone.utc).isoformat()).model_dump()
    key = {"base": currency, "quote": "USD", "requested_date": requested_date, "source": "frankfurter-v2"}
    async with _locks[hash((currency, requested_date)) % len(_locks)]:
        cached = await db.fx_rates.find_one(key, {"_id": 0})
        if cached:
            return FxQuote(**cached).model_dump()
        try:
            async with httpx.AsyncClient(timeout=float(os.environ["FX_TIMEOUT_SECONDS"])) as client:
                for attempt in range(3):
                    try:
                        response = await client.get(os.environ["FRANKFURTER_BASE_URL"].rstrip("/") + "/rates",
                                                    params={"date": requested_date, "base": currency, "quotes": "USD"})
                        if response.status_code in (429, 500, 502, 503, 504) and attempt < 2:
                            await asyncio.sleep(0.25 * (2 ** attempt))
                            continue
                        response.raise_for_status()
                        rows = response.json()
                        break
                    except httpx.TransportError:
                        if attempt == 2:
                            raise
                        await asyncio.sleep(0.25 * (2 ** attempt))
            row = next(r for r in rows if r.get("base") == currency and r.get("quote") == "USD")
            rate = Decimal(str(row["rate"]))
            rate_date = date.fromisoformat(row["date"])
            if not rate.is_finite() or rate <= 0 or rate_date > requested or (requested - rate_date).days > 10:
                raise ValueError("Invalid historical quote")
        except (httpx.HTTPError, ValueError, KeyError, TypeError, StopIteration, ArithmeticError) as exc:
            raise FxError(f"{currency}/USD kuru {requested_date} için alınamadı. Lütfen tekrar deneyin.") from exc
        doc = {**key, "rate": str(rate), "rate_date": rate_date.isoformat(), "fetched_at": datetime.now(timezone.utc).isoformat()}
        try:
            await db.fx_rates.insert_one(dict(doc))
        except DuplicateKeyError:
            doc = await db.fx_rates.find_one(key, {"_id": 0})
        return FxQuote(**doc).model_dump()