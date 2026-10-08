"""Transient CSV parsing. Total is already net of fees within an Amazon row."""
import csv
import hashlib
import io
import json
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from finance import money

ALIASES = {"order": "Order payments", "order payment": "Order payments", "order payments": "Order payments",
           "refund": "Refunds", "refunds": "Refunds", "service fee": "Service Fees", "service fees": "Service Fees"}


def normalize(value):
    return " ".join(str(value or "").lstrip("\ufeff").strip().lower().replace("_", " ").split())


def parse_amount(raw, decimal_comma=False):
    value = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    value = re.sub(r"(?:USD|CAD|MXN|GBP|EUR|AUD|JPY|TRY|SEK|PLN|AED|SAR|CA\$|MX\$|A\$|US\$|[$£€₺¥])", "", value, flags=re.I)
    if value.startswith("(") and value.endswith(")"):
        value = "-" + value[1:-1]
    if "," in value and "." in value:
        value = value.replace(".", "").replace(",", ".") if value.rfind(",") > value.rfind(".") else value.replace(",", "")
    elif "," in value:
        value = value.replace(",", ".") if decimal_comma or re.search(r",\d{1,2}$", value) else value.replace(",", "")
    result = Decimal(value)
    if not result.is_finite() or abs(result) > Decimal("1000000000000"):
        raise ValueError("Geçersiz tutar")
    return money(result)


def parse_date(raw, marketplace):
    value = raw.strip()
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", value):
        return datetime.strptime(value[:10], "%Y-%m-%d").date().isoformat()
    # Ignore clock and named timezone, retaining the report's local calendar date.
    value = re.sub(r"\s+\d{1,2}:\d{2}.*$", "", value).strip()
    formats = ["%b %d, %Y", "%b %d %Y", "%d %b %Y", "%d-%b-%Y", "%B %d, %Y", "%d %B %Y", "%d.%m.%Y"]
    formats += ["%m/%d/%Y", "%m/%d/%y"] if marketplace == "US" else ["%d/%m/%Y", "%d/%m/%y"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Tarih okunamadı; ISO tarih veya pazarın tarih biçimi gerekli")


def parse_amazon_csv(content, marketplace, currency):
    text = content.decode("utf-8-sig")
    lines = text.splitlines()
    header_index = None
    delimiter = ","
    for index, line in enumerate(lines[:50]):
        for sep in (",", ";", "\t"):
            headers = [normalize(h) for h in next(csv.reader([line], delimiter=sep))]
            if any(h in headers for h in ("date/time", "date", "posted date")) and any(h in headers for h in ("type", "transaction type", "category")):
                if any(h in ("total", "amount") or h.startswith("total (") for h in headers):
                    header_index, delimiter = index, sep
                    break
        if header_index is not None:
            break
    if header_index is None:
        raise ValueError("CSV başlıkları bulunamadı: date/time (veya Date), type (veya Transaction type), total (veya amount).")
    reader = csv.DictReader(io.StringIO("\n".join(lines[header_index:])), delimiter=delimiter)
    reader.fieldnames = [normalize(h) for h in reader.fieldnames]
    amount_header = next(h for h in reader.fieldnames if h in ("total", "amount") or h.startswith("total ("))
    currency_match = re.search(r"\(([a-z]{3})\)", amount_header)
    accepted, rejected = [], []
    occurrences = Counter()
    for row in reader:
        line_number = header_index + reader.line_num
        if not any(row.values()):
            continue
        try:
            if None in row:
                raise ValueError("Sütun sayısı başlıkla uyuşmuyor")
            category = ALIASES.get(normalize(row.get("type") or row.get("transaction type") or row.get("category")))
            if not category:
                raise ValueError("Desteklenmeyen işlem türü: " + str(row.get("type") or row.get("transaction type") or row.get("category") or "boş"))
            row_currency = (row.get("currency") or (currency_match[1] if currency_match else currency)).strip().upper()
            if row_currency != currency:
                raise ValueError(f"Para birimi {row_currency}; seçili pazar {currency}")
            row_mp = (row.get("marketplace") or "").strip().upper()
            if row_mp and len(row_mp) == 2 and row_mp != marketplace:
                raise ValueError("Satırın pazar yeri seçiminizle uyuşmuyor")
            amount = parse_amount(row.get(amount_header, ""), delimiter == ";")
            # Generic amount CSVs allow positive expense magnitudes. Amazon totals are signed.
            expense = category != "Order payments"
            normalized_amount = abs(amount) if expense and amount_header == "amount" else -amount if expense else amount
            doc = {"marketplace": marketplace, "currency": currency, "category": category,
                   "type": "expense" if expense else "income", "amount": float(normalized_amount),
                   "date": parse_date(row.get("date/time") or row.get("date") or row.get("posted date") or "", marketplace),
                   "order_id": row.get("order id") or "", "description": row.get("description") or "",
                   "product_cost": 0, "shipping_cost": 0, "extra_cost": 0,
                   # Optional stable identifiers used only by reconciliation (additive).
                   "sku": (row.get("sku") or "").strip(),
                   "quantity": (row.get("quantity") or "").strip(),
                   "amazon_txn_id": (row.get("transaction id") or row.get("txn id") or "").strip(),
                   "source": "amazon_payments_csv"}
            # All original row fields identify a row, including hidden SKU, without storing it.
            identity = json.dumps(row, sort_keys=True, ensure_ascii=False)
            occurrences[identity] += 1
            doc["source_fingerprint"] = hashlib.sha256(f"{marketplace}|{identity}|{occurrences[identity]}".encode()).hexdigest()
            accepted.append(doc)
        except (ValueError, InvalidOperation) as exc:
            rejected.append({"line": line_number, "reason": str(exc) or "Geçersiz tutar"})
        if len(accepted) + len(rejected) > 10000:
            raise ValueError("En fazla 10.000 satırlık CSV yükleyin")
    return accepted, rejected