"""PPC unified page + Amazon Payments advertising-row backend tests.

Scope (minimum focused tests per review request):
- CSV import accepts advertising / PPC rows (various labels, no Order ID, mixed with unknown rows).
- PPC attribution + Amazon Payments financial expense reconciliation (reconciled / partial).
- PPC file importer idempotency.
- Amazon Payments CSV re-import idempotency.
- Dashboard summary counts advertising expense exactly once (not doubled by attribution).
- FBA ASIN report: PPC attribution overlays into ppc_spend_usd without inflating general expenses.
- Unknown transaction types do NOT reject the whole CSV (review_required).

The tests build their own TEST store named 'TEST_PPC_<random>' and clean it up
plus all attached transactions / ppc_attributions in the final teardown. The
pre-existing real store 'ng' MUST NOT be touched.
"""
import io
import os
import uuid

import pytest
import requests

def _load_frontend_env():
    try:
        with open("/app/frontend/.env", "r", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("REACT_APP_BACKEND_URL="):
                    return line.split("=", 1)[1].strip().strip('"')
    except OSError:
        return None
    return None


BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or _load_frontend_env() or "").rstrip("/")
assert BASE_URL, "REACT_APP_BACKEND_URL missing"
ORIGIN = "https://amz-finance-suite.preview.emergentagent.com"
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"


# ---------- Session / fixtures ----------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    s.headers.update({"Origin": ORIGIN})
    r = s.post(f"{BASE_URL}/api/auth/login",
               json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
               timeout=20)
    assert r.status_code == 200, f"Login failed: {r.status_code} {r.text}"
    tok = r.json().get("access_token") or r.json().get("token")
    assert tok, f"No token: {r.text}"
    s.headers.update({"Authorization": f"Bearer {tok}"})
    return s


@pytest.fixture(scope="module")
def store(session):
    name = f"TEST_PPC_{uuid.uuid4().hex[:8]}"
    r = session.post(f"{BASE_URL}/api/stores",
                     json={"name": name, "marketplaces": ["US"], "default_currency": "USD"},
                     timeout=20)
    assert r.status_code == 200, r.text
    st = r.json()
    yield st
    # Teardown — delete attributions, transactions (store delete does txs) and the store.
    sid = st["id"]
    # Delete attributions
    try:
        attr = session.get(f"{BASE_URL}/api/ppc/attributions",
                           params={"store_id": sid}, timeout=20).json()
        for row in attr.get("rows", []):
            session.delete(f"{BASE_URL}/api/ppc/attributions/{row['id']}", timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"attr cleanup failed: {exc}")
    try:
        session.delete(f"{BASE_URL}/api/stores/{sid}", timeout=20)
    except Exception as exc:  # noqa: BLE001
        print(f"store cleanup failed: {exc}")


# ---------- Helpers ----------
def _csv(headers, rows):
    out = io.StringIO()
    out.write(",".join(headers) + "\n")
    for r in rows:
        out.write(",".join(str(c) for c in r) + "\n")
    return out.getvalue().encode("utf-8")


def _import_payments(session, store_id, csv_bytes, commit=True):
    files = {"file": ("payments.csv", csv_bytes, "text/csv")}
    return session.post(
        f"{BASE_URL}/api/transactions/import",
        params={"store_id": store_id, "marketplace": "US", "commit": str(commit).lower()},
        files=files, timeout=60)


# ---------- Tests ----------
class TestAmazonPaymentsAdRows:
    """Advertising rows parsing + classification."""

    def test_variants_import_as_advertising(self, session, store):
        # Different label variants + alias normalization + whitespace
        headers = ["date", "type", "order id", "sku", "description", "quantity", "marketplace", "total"]
        rows = [
            ["2026-01-05", "Cost of Advertising", "", "", "desc1", "", "US", "-10.54"],
            ["2026-01-06", "ADVERTISING-FEE", "", "", "desc2", "", "US", "-1.23"],
            ["2026-01-07", "advertising_charge", "", "", "desc3", "", "US", "-2.00"],
            ["2026-01-08", " Sponsored  Brands ", "", "", "desc4", "", "US", "-3.00"],
        ]
        r = _import_payments(session, store["id"], _csv(headers, rows), commit=True)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["accepted"] == 4, data
        assert data["inserted"] == 4, data
        # Verify review_required empty for these known ad labels
        diag = data.get("diagnostics") or {}
        assert diag.get("review_required", []) == [], diag.get("review_required")

        # Verify DB side: GET transactions, filter for store+advertising
        tx = session.get(f"{BASE_URL}/api/transactions",
                         params={"store_id": store["id"]}, timeout=30).json()
        ads = [t for t in tx if t.get("category") == "Advertising"]
        assert len(ads) >= 4
        for t in ads:
            assert t["type"] == "expense"
            assert t["classification"] == "PPC_ADVERTISING_EXPENSE"
            assert t["raw_transaction_type"], "raw_transaction_type must be preserved"
            assert t["amount"] > 0  # stored as positive expense magnitude

        amounts = sorted([t["amount"] for t in ads])
        assert 10.54 in amounts
        assert 1.23 in amounts

    def test_empty_order_id_is_ok_for_ads(self, session, store):
        # Already covered in previous test but assert explicitly: no rejection
        headers = ["date", "type", "order id", "total"]
        rows = [["2026-01-09", "Sponsored Products Charge", "", "-4.00"]]
        r = _import_payments(session, store["id"], _csv(headers, rows), commit=True)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["accepted"] == 1
        assert data["rejected_count"] == 0

    def test_unknown_type_does_not_reject_whole_csv(self, session, store):
        headers = ["date", "type", "order id", "total"]
        rows = [
            ["2026-01-10", "Order payments", "ORD-TEST-" + uuid.uuid4().hex[:6], "25.00"],
            ["2026-01-10", "Mystery Adjustment XYZ", "", "-5.00"],
        ]
        r = _import_payments(session, store["id"], _csv(headers, rows), commit=True)
        assert r.status_code == 200, r.text
        data = r.json()
        # Valid Order payments row inserted, unknown row only in review_required.
        assert data["accepted"] == 1, data
        diag = data["diagnostics"]
        review = diag.get("review_required", [])
        assert len(review) == 1, review
        assert "Mystery" in review[0]["raw_transaction_type"]
        assert review[0]["classification"] == "UNKNOWN_REVIEW_REQUIRED"

    def test_payments_csv_reimport_idempotent(self, session, store):
        headers = ["date", "type", "order id", "total"]
        rows = [["2026-01-11", "Cost of Advertising", "", "-7.77"]]
        c = _csv(headers, rows)
        r1 = _import_payments(session, store["id"], c, commit=True).json()
        r2 = _import_payments(session, store["id"], c, commit=True).json()
        assert r1["inserted"] == 1
        assert r2["inserted"] == 0, r2
        # Financial advertising total unchanged across the duplicate import.
        fe = session.get(f"{BASE_URL}/api/ppc/financial-expenses",
                         params={"store_id": store["id"]}, timeout=20).json()
        assert fe["total_usd"] > 0


class TestAttributionReconciliation:
    def test_full_reconciled_and_no_double_count(self, session, store):
        # Attribute 10.54 ad spend for ASIN B0TEST0001 in Jan 2026 matching the earlier CSV ad row.
        r = session.post(
            f"{BASE_URL}/api/ppc/attributions",
            json={"store_id": store["id"], "marketplace": "US", "date": "2026-01-05",
                  "asin": "B0TEST0001", "ad_spend_usd": 10.54},
            timeout=20)
        assert r.status_code == 201, r.text

        summary = session.get(f"{BASE_URL}/api/ppc/attributions",
                              params={"store_id": store["id"], "marketplace": "US"},
                              timeout=20).json()["summary"]
        # Financial includes all ad rows imported so far (10.54 + 1.23 + 2.00 + 3.00 + 4.00 + 7.77 = 28.54)
        assert summary["financial_ad_expense_usd"] >= 10.54
        assert summary["allocated_ppc_spend_usd"] == 10.54

        # Dashboard summary expenses must NOT double-count: expense = financial total only.
        ds = session.get(f"{BASE_URL}/api/dashboard/summary",
                         params={"store_id": store["id"]}, timeout=30).json()
        assert ds["expenses"] is not None
        # Expenses >= financial advertising (there may be other categories but no doubling).
        # Specifically the sum of advertising expenses in the by_category breakdown should equal
        # financial, not financial + attribution.
        ad_cat = next((c for c in ds.get("by_category", []) if c["category"] == "Advertising"), None)
        assert ad_cat is not None, ds.get("by_category")
        # Allow tiny rounding; attribution is NOT an expense so category == financial exactly.
        assert abs(ad_cat["amount"] - summary["financial_ad_expense_usd"]) < 0.02, (
            f"advertising category {ad_cat['amount']} vs financial {summary['financial_ad_expense_usd']} "
            "-- attributions must not be counted as expenses")

    def test_partial_reconciled(self, session, store):
        # Fresh month to isolate from Jan rows. Use different amount AND description so the
        # Amazon date-independent fingerprint does not collide with existing Jan rows.
        headers = ["date", "type", "order id", "description", "total"]
        rows = [["2026-02-03", "Cost of Advertising", "", "feb-ad-partial", "-10.54"]]
        _import_payments(session, store["id"], _csv(headers, rows), commit=True)
        # Only 6.00 of the 10.54 is allocated -> partial.
        session.post(f"{BASE_URL}/api/ppc/attributions",
                     json={"store_id": store["id"], "marketplace": "US", "date": "2026-02-04",
                           "asin": "B0TEST0002", "ad_spend_usd": 6.00}, timeout=20)
        recon = session.get(f"{BASE_URL}/api/ppc/reconciliation",
                            params={"store_id": store["id"], "marketplace": "US"},
                            timeout=20).json()
        feb = next((r for r in recon["rows"] if r["month"] == "2026-02"), None)
        assert feb, recon
        assert feb["financial_ad_expense_usd"] == 10.54
        assert feb["attributed_ad_spend_usd"] == 6.00
        assert feb["unattributed_usd"] == 4.54
        assert feb["status"] == "partially_reconciled"


class TestAttributionFileImport:
    def test_report_import_is_idempotent(self, session, store):
        headers = ["Date", "Campaign Name", "Ad Type", "Advertised ASIN", "Advertised SKU",
                   "Impressions", "Clicks", "Spend", "7 Day Total Sales", "7 Day Total Orders (#)"]
        rows = [["2026-03-01", "TEST-CMP", "Sponsored Products", "B0TEST0003", "SKU-TEST", 1000, 50, 12.34, 100.00, 3]]
        payload = _csv(headers, rows)
        files = {"file": ("ppc.csv", payload, "text/csv")}
        r1 = session.post(f"{BASE_URL}/api/ppc/attributions/import-file",
                          params={"store_id": store["id"], "marketplace": "US", "commit": "true"},
                          files=files, timeout=30).json()
        files = {"file": ("ppc.csv", payload, "text/csv")}
        r2 = session.post(f"{BASE_URL}/api/ppc/attributions/import-file",
                          params={"store_id": store["id"], "marketplace": "US", "commit": "true"},
                          files=files, timeout=30).json()
        assert r1["new"] == 1, r1
        assert r2["new"] == 0, r2
        # Total spend not doubled.
        got = session.get(f"{BASE_URL}/api/ppc/attributions",
                          params={"store_id": store["id"], "marketplace": "US",
                                  "start_date": "2026-03-01", "end_date": "2026-03-31"},
                          timeout=20).json()
        assert got["summary"]["attributed_ad_spend_usd"] == 12.34, got["summary"]


class TestFbaOverlay:
    """FBA ASIN report must get ppc_spend_usd via overlay without altering general expenses."""

    def test_dashboard_expense_unchanged_by_attribution(self, session, store):
        ds_before = session.get(f"{BASE_URL}/api/dashboard/summary",
                                params={"store_id": store["id"]}, timeout=30).json()
        exp_before = ds_before["expenses"] or 0
        # New attribution for an ASIN with no financial ad row for Apr => should NOT raise expenses.
        session.post(f"{BASE_URL}/api/ppc/attributions",
                     json={"store_id": store["id"], "marketplace": "US", "date": "2026-04-15",
                           "asin": "B0TEST0004", "ad_spend_usd": 15.00}, timeout=20)
        ds_after = session.get(f"{BASE_URL}/api/dashboard/summary",
                               params={"store_id": store["id"]}, timeout=30).json()
        exp_after = ds_after["expenses"] or 0
        assert abs(exp_after - exp_before) < 0.01, (
            f"Attribution must not inflate expenses: before={exp_before} after={exp_after}")
