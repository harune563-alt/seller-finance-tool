"""Amazon Payments CSV parsing — alias-based semantic header mapping.

The parser is intentionally lenient about shape: columns may be removed,
reordered, or augmented with custom columns, and only the semantic financial
fields are required. Reconciliation / fingerprinting still live in
reconciliation.py and are header-independent.

Public contract (unchanged for callers of parse_amazon_csv except an added
optional ``column_mapping`` argument and an added diagnostics dict in the
return tuple):

    accepted, rejected, diagnostics = parse_amazon_csv(content, marketplace, currency, column_mapping=None)

Raises:
    CsvMappingRequired: auto-detection failed; the frontend must offer the
        manual mapping step. ``exc.diagnostics`` describes the exact state so
        the UI can show headers, auto-mapping, missing fields, custom columns.
    ValueError: the file is syntactically unreadable (encoding, csv dialect).
"""
import csv
import hashlib
import io
import re
from collections import Counter
from datetime import datetime
from decimal import Decimal, InvalidOperation
from finance import money

# Category aliases accepted inside the Type/Transaction type cell.
ALIASES = {
    "order": "Order payments",
    "order payment": "Order payments",
    "order payments": "Order payments",
    "orderpayment": "Order payments",
    "orderpayments": "Order payments",
    "refund": "Refunds",
    "refunds": "Refunds",
    "service fee": "Service Fees",
    "service fees": "Service Fees",
    "servicefee": "Service Fees",
    "servicefees": "Service Fees",
}

# Normalized header candidates per semantic field. normalize_header() strips
# whitespace, underscores and hyphens so every alias listed in the spec maps.
FIELD_ALIASES = {
    "transaction_date": {
        "date", "datetime", "posteddate", "postingdate",
        "transactiondate", "transactiondatetime",
    },
    "transaction_type": {
        "type", "transactiontype", "eventtype",
    },
    "amount": {
        "total", "amount", "netamount", "nettotal", "totalamount",
        "transactionamount",
    },
    "order_id": {
        "orderid", "amazonorderid", "sellerorderid", "merchantorderid",
    },
    "sku": {"sku", "sellersku", "merchantsku"},
    "quantity": {"quantity", "qty"},
    # Non-user-mappable but still auto-detected.
    "currency": {"currency"},
    "marketplace": {"marketplace"},
    "description": {"description", "details"},
    "amazon_txn_id": {"transactionid", "txnid"},
}

# Fields the UI exposes in the manual mapping step.
MAPPABLE_FIELDS = ["transaction_date", "transaction_type", "amount",
                   "order_id", "sku", "quantity"]

# Required even without any specific transaction type.
GLOBALLY_REQUIRED = ("transaction_date", "transaction_type", "amount")

# Categories that still require Order ID per the existing accounting rule.
ORDER_ID_REQUIRED_CATEGORIES = {"Order payments", "Refunds"}


class CsvMappingRequired(Exception):
    """Signal that auto-detection failed and the UI should present manual mapping."""

    def __init__(self, message, diagnostics):
        super().__init__(message)
        self.diagnostics = diagnostics


def _collapse(value):
    """Trim, drop BOM/NBSP/zero-width, collapse runs of whitespace."""
    text = str(value or "").replace("\ufeff", "").replace("\u00a0", " ")
    text = re.sub(r"[\u200b\u200c\u200d\u2028\u2029]", "", text)
    return " ".join(text.split()).strip()


def normalize(value):
    """Lowercase, collapsed whitespace, underscores to spaces. Used for category text."""
    return " ".join(_collapse(value).lower().replace("_", " ").split())


def normalize_header(value):
    """Match key: lowercase, remove whitespace, underscore, hyphen, slash, dot."""
    text = _collapse(value).lower()
    return re.sub(r"[\s_\-/\.]+", "", text)


_AMOUNT_WITH_CURRENCY = re.compile(
    r"^(?:total|amount|nettotal|netamount|totalamount|transactionamount)\(.{3}\)$"
)


def parse_amount(raw, decimal_comma=False):
    value = str(raw).strip().replace("\u00a0", "").replace(" ", "")
    value = re.sub(
        r"(?:USD|CAD|MXN|GBP|EUR|AUD|JPY|TRY|SEK|PLN|AED|SAR|CA\$|MX\$|A\$|US\$|[$£€₺¥])",
        "", value, flags=re.I,
    )
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
    value = _collapse(raw)
    if re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", value):
        return datetime.strptime(value[:10], "%Y-%m-%d").date().isoformat()
    # Ignore clock and named timezone, retaining the report's local calendar date.
    value = re.sub(r"\s+\d{1,2}:\d{2}.*$", "", value).strip()
    formats = ["%b %d, %Y", "%b %d %Y", "%d %b %Y", "%d-%b-%Y",
               "%B %d, %Y", "%d %B %Y", "%d.%m.%Y"]
    formats += ["%m/%d/%Y", "%m/%d/%y"] if marketplace == "US" else ["%d/%m/%Y", "%d/%m/%y"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError("Tarih okunamadı; ISO tarih veya pazarın tarih biçimi gerekli")


def _candidate_map(headers):
    """{normalized_key -> original_header} keeping the first occurrence."""
    result = {}
    for header in headers:
        key = normalize_header(header)
        if key and key not in result:
            result[key] = header
    return result


def _match_field(candidates, field, override_header=None):
    """Return the original header for `field` or None.

    `override_header` wins if the user manually mapped it, regardless of alias
    membership. We still require it to actually exist in the detected headers.
    """
    if override_header:
        key = normalize_header(override_header)
        if key in candidates:
            return candidates[key]
    for key, original in candidates.items():
        if key in FIELD_ALIASES.get(field, ()):
            return original
    if field == "amount":
        for key, original in candidates.items():
            if _AMOUNT_WITH_CURRENCY.match(key):
                return original
    return None


def _try_split(line, delimiter):
    try:
        return next(csv.reader([line], delimiter=delimiter))
    except StopIteration:
        return None


def _resolve_headers(lines, overrides):
    """Scan the first 50 lines for a header row that gives at least date+amount.

    Transaction type can still be filled from the override map, so we accept a
    header row where date + amount or date + type can be resolved.
    """
    for index, line in enumerate(lines[:50]):
        for delimiter in (",", ";", "\t"):
            cells = _try_split(line, delimiter)
            if not cells or sum(1 for c in cells if _collapse(c)) < 2:
                continue
            candidates = _candidate_map(cells)
            date = _match_field(candidates, "transaction_date", overrides.get("transaction_date"))
            amount = _match_field(candidates, "amount", overrides.get("amount"))
            type_ = _match_field(candidates, "transaction_type", overrides.get("transaction_type"))
            if date and (amount or type_):
                return index, delimiter, candidates, cells
    return None


def _best_guess_headers(lines):
    """Only for diagnostics when nothing resolves: pick the row with most header-like cells."""
    best, best_delim = [], ","
    for line in lines[:50]:
        for delimiter in (",", ";", "\t"):
            cells = _try_split(line, delimiter) or []
            cleaned = [c for c in cells if _collapse(c)]
            if len(cleaned) > len(best):
                best, best_delim = cells, delimiter
    return best, best_delim


def _build_diagnostics(headers, overrides, auto_detected=None, missing_required=None):
    """Describe the parser's view of the file for the UI's mapping step."""
    auto_detected = auto_detected or {}
    overrides = {k: v for k, v in (overrides or {}).items() if v}
    used = {header for header in auto_detected.values() if header}
    known_keys = {alias for aliases in FIELD_ALIASES.values() for alias in aliases}

    unknown_custom = []
    ignored_optional = []
    for header in headers or []:
        if not _collapse(header) or header in used:
            continue
        key = normalize_header(header)
        if key in known_keys or _AMOUNT_WITH_CURRENCY.match(key):
            ignored_optional.append(header)
        else:
            unknown_custom.append(header)

    return {
        "detected_headers": list(headers or []),
        "auto_mapping": {k: v for k, v in auto_detected.items() if v},
        "overrides_applied": overrides,
        "ignored_optional_columns": ignored_optional,
        "unknown_custom_columns": unknown_custom,
        "missing_required_fields": list(missing_required or []),
        "mappable_fields": list(MAPPABLE_FIELDS),
    }


def parse_amazon_csv(content, marketplace, currency, column_mapping=None):
    overrides = {k: v for k, v in (column_mapping or {}).items() if v}
    text = content.decode("utf-8-sig")
    lines = text.splitlines()

    resolved = _resolve_headers(lines, overrides)
    if resolved is None:
        best, _ = _best_guess_headers(lines)
        raise CsvMappingRequired(
            "Amazon CSV başlıkları otomatik tespit edilemedi. Lütfen alanları manuel eşleyin.",
            _build_diagnostics(best, overrides,
                               auto_detected={},
                               missing_required=list(GLOBALLY_REQUIRED)),
        )
    header_index, delimiter, candidates, original_headers = resolved

    auto = {}
    for field in FIELD_ALIASES:
        auto[field] = _match_field(candidates, field, overrides.get(field))

    missing_required = [f for f in GLOBALLY_REQUIRED if not auto[f]]
    if missing_required:
        raise CsvMappingRequired(
            "Zorunlu alan(lar) tespit edilemedi: " + ", ".join(missing_required)
            + ". Lütfen manuel eşleyin.",
            _build_diagnostics(original_headers, overrides,
                               auto_detected=auto,
                               missing_required=missing_required),
        )

    amount_header = auto["amount"]
    amount_header_norm = normalize_header(amount_header)
    currency_match = re.search(r"\(\s*([a-zA-Z]{3})\s*\)", amount_header or "")
    uses_signed_amount = amount_header_norm in {"total"} or _AMOUNT_WITH_CURRENCY.match(amount_header_norm)

    accepted, rejected = [], []
    occurrences = Counter()
    reader = csv.reader(io.StringIO("\n".join(lines[header_index + 1:])), delimiter=delimiter)

    column_count = len(original_headers)
    index_map = {header: idx for idx, header in enumerate(original_headers)}

    for row_offset, raw_row in enumerate(reader, start=1):
        line_number = header_index + 1 + row_offset
        if not raw_row or not any(_collapse(cell) for cell in raw_row):
            continue
        # Pad missing cells to None; silently drop extra trailing cells.
        values = list(raw_row[:column_count]) + [""] * (column_count - len(raw_row))

        def cell(header):
            idx = index_map.get(header) if header else None
            return values[idx] if idx is not None and idx < len(values) else ""

        try:
            type_raw = _collapse(cell(auto["transaction_type"]))
            if not type_raw:
                raise ValueError("İşlem türü boş")
            category = ALIASES.get(normalize(type_raw))
            if not category:
                raise ValueError("Desteklenmeyen işlem türü: " + type_raw)

            row_currency = (cell(auto["currency"]) or "").strip().upper() or (
                currency_match[1].upper() if currency_match else currency
            )
            if row_currency != currency:
                raise ValueError("Para birimi " + row_currency + "; seçili pazar " + currency)

            row_mp = (cell(auto["marketplace"]) or "").strip().upper()
            if row_mp and len(row_mp) == 2 and row_mp != marketplace:
                raise ValueError("Satırın pazar yeri seçiminizle uyuşmuyor")

            amount_raw = cell(amount_header)
            if not _collapse(amount_raw):
                raise ValueError("Tutar boş")
            amount = parse_amount(amount_raw, delimiter == ";")

            expense = category != "Order payments"
            # When the file uses an unsigned amount column (not Total/… (CCY)), apply
            # the sign ourselves for expenses; "total (…)" rows are already signed.
            if expense and not uses_signed_amount:
                normalized_amount = abs(amount)
            elif expense:
                normalized_amount = -amount
            else:
                normalized_amount = amount

            order_id = (cell(auto["order_id"]) or "").strip()
            if category in ORDER_ID_REQUIRED_CATEGORIES and not order_id:
                raise ValueError(category + " kaydı için Order ID gereklidir")

            doc = {
                "marketplace": marketplace, "currency": currency, "category": category,
                "type": "expense" if expense else "income",
                "amount": float(normalized_amount),
                "date": parse_date(cell(auto["transaction_date"]), marketplace),
                "order_id": order_id,
                "description": _collapse(cell(auto["description"])),
                "product_cost": 0, "shipping_cost": 0, "extra_cost": 0,
                "sku": _collapse(cell(auto["sku"])),
                "quantity": _collapse(cell(auto["quantity"])),
                "amazon_txn_id": _collapse(cell(auto["amazon_txn_id"])),
                "source": "amazon_payments_csv",
            }

            # Stable semantic identity: survives column reorder, extra custom
            # columns, header renames and removed optional cells. Date is
            # deliberately excluded here, matching reconciliation.event_fingerprint.
            identity = "|".join([
                marketplace, order_id, category,
                doc["sku"], doc["quantity"],
                str(money(normalized_amount)), currency,
                " ".join(doc["description"].split()).lower(),
            ])
            occurrences[identity] += 1
            doc["source_fingerprint"] = hashlib.sha256(
                ("amz-v2|" + identity + "|" + str(occurrences[identity])).encode("utf-8")
            ).hexdigest()
            accepted.append(doc)
        except (ValueError, InvalidOperation) as exc:
            rejected.append({"line": line_number, "reason": str(exc) or "Geçersiz tutar"})
        if len(accepted) + len(rejected) > 10000:
            raise ValueError("En fazla 10.000 satırlık CSV yükleyin")

    diagnostics = _build_diagnostics(original_headers, overrides, auto_detected=auto)
    return accepted, rejected, diagnostics
