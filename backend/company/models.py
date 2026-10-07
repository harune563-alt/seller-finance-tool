from datetime import date as calendar_date, datetime, timezone
from decimal import Decimal
from typing import Any, Literal, Optional
from uuid import UUID
from pydantic import BaseModel, Field, field_validator, model_validator

Currency = Literal["USD", "TRY"]

class PersonIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    role: Literal["partner", "investor", "contact"] = "partner"
    note: str = Field(default="", max_length=500)

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value):
        if not value.strip(): raise ValueError("İsim boş olamaz")
        return value.strip()

class PersonOut(PersonIn):
    id: str
    created_at: str

class AmountIn(BaseModel):
    request_id: UUID
    amount: Decimal = Field(gt=0, le=10000000000, max_digits=14, decimal_places=2)
    date: str
    note: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        result = calendar_date.fromisoformat(value)
        if result > datetime.now(timezone.utc).date(): raise ValueError("İşlem tarihi gelecekte olamaz")
        return result.isoformat()

class CapitalIn(AmountIn):
    person_id: str
    store_id: str
    currency: Currency
    direction: Literal["contribution", "withdrawal"] = "contribution"

class DebtIn(AmountIn):
    person_id: str
    store_id: Optional[str] = None
    direction: Literal["payable", "receivable"]
    currency: Currency
    due_date: Optional[str] = None
    cash_effect: bool = False

    @model_validator(mode="after")
    def valid_due_date(self):
        if self.due_date:
            self.due_date = calendar_date.fromisoformat(self.due_date).isoformat()
            if self.due_date < self.date: raise ValueError("Vade işlem tarihinden önce olamaz")
        return self

class CashIn(AmountIn):
    currency: Currency
    direction: Literal["in", "out"]

class CapitalUpdateIn(BaseModel):
    amount: Decimal = Field(gt=0, le=10000000000, max_digits=14, decimal_places=2)
    date: str
    note: str = Field(default="", max_length=500)
    person_id: str
    store_id: str
    currency: Currency
    direction: Literal["contribution", "withdrawal"] = "contribution"

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        result = calendar_date.fromisoformat(value)
        if result > datetime.now(timezone.utc).date(): raise ValueError("İşlem tarihi gelecekte olamaz")
        return result.isoformat()


class CashUpdateIn(BaseModel):
    amount: Decimal = Field(gt=0, le=10000000000, max_digits=14, decimal_places=2)
    date: str
    note: str = Field(default="", max_length=500)
    currency: Currency
    direction: Literal["in", "out"]

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        result = calendar_date.fromisoformat(value)
        if result > datetime.now(timezone.utc).date(): raise ValueError("İşlem tarihi gelecekte olamaz")
        return result.isoformat()


class DebtUpdateIn(BaseModel):
    amount: Decimal = Field(gt=0, le=10000000000, max_digits=14, decimal_places=2)
    date: str
    note: str = Field(default="", max_length=500)
    person_id: str
    store_id: Optional[str] = None
    direction: Literal["payable", "receivable"]
    currency: Currency
    due_date: Optional[str] = None
    cash_effect: bool = False

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        result = calendar_date.fromisoformat(value)
        if result > datetime.now(timezone.utc).date(): raise ValueError("İşlem tarihi gelecekte olamaz")
        return result.isoformat()

    @model_validator(mode="after")
    def valid_due_date(self):
        if self.due_date:
            self.due_date = calendar_date.fromisoformat(self.due_date).isoformat()
            if self.due_date < self.date: raise ValueError("Vade işlem tarihinden önce olamaz")
        return self


class PaymentUpdateIn(BaseModel):
    amount: Decimal = Field(gt=0, le=10000000000, max_digits=14, decimal_places=2)
    date: str
    note: str = Field(default="", max_length=500)

    @field_validator("date")
    @classmethod
    def valid_date(cls, value):
        result = calendar_date.fromisoformat(value)
        if result > datetime.now(timezone.utc).date(): raise ValueError("İşlem tarihi gelecekte olamaz")
        return result.isoformat()


class ClosingUpdateIn(BaseModel):
    revenue: Optional[float] = Field(default=None, allow_inf_nan=False)
    expenses: Optional[float] = Field(default=None, allow_inf_nan=False)
    net_profit: Optional[float] = Field(default=None, allow_inf_nan=False)


class BulkIdsIn(BaseModel):
    ids: list[str] = Field(min_length=1, max_length=100)


class BulkChangesIn(BulkIdsIn):
    changes: dict[str, Any] = Field(min_length=1, max_length=20)


class PaymentOut(BaseModel):
    id: str
    amount: float
    date: str
    note: str
    created_at: str

class DebtOut(BaseModel):
    id: str
    person_id: str
    person_name: str
    store_id: Optional[str] = None
    store_name: Optional[str] = None
    direction: str
    currency: str
    principal: float
    remaining: float
    date: str
    due_date: Optional[str] = None
    cash_effect: bool
    note: str
    status: str
    payments: list[PaymentOut]


CashEffect = Literal["none", "in", "out"]
CashStatus = Literal["pending", "completed"]

class CurrentEntryIn(AmountIn):
    person_id: str
    store_id: Optional[str] = None
    direction: Literal["payable", "receivable"]
    currency: Currency
    due_date: Optional[str] = None
    cash_effect: CashEffect = "none"
    cash_status: CashStatus = "pending"

    @model_validator(mode="after")
    def valid_due_date(self):
        if self.due_date:
            self.due_date = calendar_date.fromisoformat(self.due_date).isoformat()
            if self.due_date < self.date:
                raise ValueError("Vade işlem tarihinden önce olamaz")
        return self

class CurrentEntryOut(BaseModel):
    id: str
    person_id: str
    person_name: str
    store_id: Optional[str] = None
    store_name: Optional[str] = None
    direction: str
    currency: str
    amount: float
    date: str
    due_date: Optional[str] = None
    note: str
    cash_effect: str
    cash_status: str
    due_status: str
    balance_after: float
    created_at: str

class CurrentAccountSummary(BaseModel):
    person_id: str
    person_name: str
    currency: str
    total_payable: float
    total_receivable: float
    net_balance: float
    entry_count: int

class CurrentAccountOut(BaseModel):
    summaries: list[CurrentAccountSummary]
    entries: list[CurrentEntryOut]

class CapitalEntryOut(BaseModel):
    id: str
    store_id: str
    person_id: str
    person_name: str
    direction: str
    amount: float
    currency: str
    usd_basis: float
    date: str
    note: str
    created_at: str
    basis_method: str

class OwnershipOut(BaseModel):
    person_id: str
    person_name: str
    role: str
    net_capital_usd: float
    share_percent: float
    balances: dict[str, float]

class CapitalOut(BaseModel):
    store_id: str
    total_usd: float
    ownership: list[OwnershipOut]
    entries: list[CapitalEntryOut]

class LedgerEntry(BaseModel):
    id: str
    date: str
    currency: str
    amount: float
    kind: str
    note: str
    person_name: str = ""
    store_name: str = ""
    created_at: str
    source: Optional[str] = None

class CashBalance(BaseModel):
    currency: str
    cash_balance: float
    payables: float
    receivables: float
    capital: float

class CompanyOverview(BaseModel):
    balances: list[CashBalance]
    closed_profit_usd: Optional[float]
    book_balance_usd: Optional[float]
    blocked_closings: int
    people_count: int
    latest_close_at: Optional[str] = None
    ledger: list[LedgerEntry]

class ClosingOut(BaseModel):
    id: str
    store_id: str
    store_name: str
    period: str
    revenue: Optional[float]
    expenses: Optional[float]
    net_profit: Optional[float]
    status: str
    error: str = ""
    revision: int
    updated_at: str

class JobOut(BaseModel):
    run_id: str
    status: str
    created_at: str
    updated_at: str
    processed: int = 0
    error: str = ""

class JobAccepted(BaseModel):
    accepted: bool = True
    duplicate: bool = False
    run_id: str