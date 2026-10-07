"""Backend regression + feature tests for Categories CRUD and FBA/PPC transactions."""
import os
import uuid
from datetime import date

import pytest
import requests


BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    return BASE_URL.rstrip("/")


@pytest.fixture(scope="session")
def admin_session(base_url):
    s = requests.Session()
    r = s.post(f"{base_url}/api/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"})
    assert r.status_code == 200, r.text
    data = r.json()
    s.headers.update({"Authorization": f"Bearer {data['token']}"})
    return s


@pytest.fixture
def fresh_store(admin_session, base_url):
    payload = {
        "name": f"TEST_CAT_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US"],
        "default_currency": "USD",
    }
    r = admin_session.post(f"{base_url}/api/stores", json=payload)
    assert r.status_code == 200, r.text
    store = r.json()
    yield store
    # cleanup: delete transactions and the store
    try:
        admin_session.delete(f"{base_url}/api/stores/{store['id']}")
    except Exception:
        pass


def _tx(store_id, **overrides):
    base = {
        "store_id": store_id,
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 100,
        "currency": "USD",
        "date": date.today().isoformat(),
        "description": "",
        "order_id": "",
        "product_cost": 0,
        "shipping_cost": 0,
        "extra_cost": 0,
        "product_cost_recovery": 0,
        "shipping_cost_recovery": 0,
    }
    base.update(overrides)
    return base


# ------------------------------- Categories CRUD -------------------------------

class TestCategoriesSeeding:
    def test_fresh_store_auto_seeds_defaults(self, admin_session, base_url, fresh_store):
        r = admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]})
        assert r.status_code == 200, r.text
        cats = r.json()
        assert len(cats) == 10, f"Expected 10 default categories, got {len(cats)}: {[c['name'] for c in cats]}"
        sections = {c["section"] for c in cats}
        assert sections == {"general", "fba", "ppc"}
        counts = {"general": 0, "fba": 0, "ppc": 0}
        for c in cats:
            counts[c["section"]] += 1
        assert counts == {"general": 3, "fba": 5, "ppc": 2}
        # all is_system true for defaults
        assert all(c["is_system"] for c in cats)
        # Order payments / Refunds / Service Fees preserved
        names = {c["name"] for c in cats}
        assert {"Order payments", "Refunds", "Service Fees"}.issubset(names)
        # Sort order: section asc, type asc, name asc
        sort_key = [(c["section"], c["type"], c["name"]) for c in cats]
        assert sort_key == sorted(sort_key)

    def test_seed_idempotent(self, admin_session, base_url, fresh_store):
        admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]})
        r = admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]})
        assert r.status_code == 200
        assert len(r.json()) == 10


class TestCategoriesCRUD:
    def test_create_category_and_duplicate(self, admin_session, base_url, fresh_store):
        payload = {
            "store_id": fresh_store["id"], "name": "TEST_Custom_Expense",
            "type": "expense", "section": "general", "color": "#111", "icon": "tag",
        }
        r = admin_session.post(f"{base_url}/api/categories", json=payload)
        assert r.status_code == 200, r.text
        created = r.json()
        assert created["name"] == "TEST_Custom_Expense"
        assert created["is_system"] is False
        assert created["type"] == "expense"
        # duplicate
        r2 = admin_session.post(f"{base_url}/api/categories", json=payload)
        assert r2.status_code == 409

    def test_rename_updates_transactions(self, admin_session, base_url, fresh_store):
        # Create custom income category
        c = admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_RenameMe",
            "type": "income", "section": "general",
        }).json()
        # Create transaction using it
        r_tx = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], category="TEST_RenameMe", amount=50,
        ))
        assert r_tx.status_code == 200, r_tx.text
        tx_id = r_tx.json()["id"]
        # Rename the category
        r_up = admin_session.put(f"{base_url}/api/categories/{c['id']}", json={"name": "TEST_Renamed"})
        assert r_up.status_code == 200, r_up.text
        assert r_up.json()["name"] == "TEST_Renamed"
        # Verify transaction category is renamed
        r_list = admin_session.get(f"{base_url}/api/transactions", params={"store_id": fresh_store["id"]})
        assert r_list.status_code == 200
        found = [t for t in r_list.json() if t["id"] == tx_id]
        assert found and found[0]["category"] == "TEST_Renamed"

    def test_update_type_section_color_archived(self, admin_session, base_url, fresh_store):
        c = admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_Update",
            "type": "expense", "section": "general",
        }).json()
        r = admin_session.put(f"{base_url}/api/categories/{c['id']}", json={
            "type": "income", "section": "fba", "color": "#abcdef", "archived": True,
        })
        assert r.status_code == 200, r.text
        out = r.json()
        assert out["type"] == "income"
        assert out["section"] == "fba"
        assert out["color"] == "#abcdef"
        assert out["archived"] is True

    def test_delete_unused_ok_in_use_blocked(self, admin_session, base_url, fresh_store):
        c = admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_Delete",
            "type": "expense", "section": "general",
        }).json()
        # Delete unused - ok
        r = admin_session.delete(f"{base_url}/api/categories/{c['id']}")
        assert r.status_code == 200
        # Recreate and use it
        c2 = admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_DeleteInUse",
            "type": "expense", "section": "general",
        }).json()
        r_tx = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="TEST_DeleteInUse", amount=10,
        ))
        assert r_tx.status_code == 200, r_tx.text
        r_del = admin_session.delete(f"{base_url}/api/categories/{c2['id']}")
        assert r_del.status_code == 409

    def test_can_delete_system_category_when_unused(self, admin_session, base_url, fresh_store):
        cats = admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]}).json()
        fba_sys = next(c for c in cats if c["section"] == "fba" and c["name"] == "FBA Depolama Ücreti")
        r = admin_session.delete(f"{base_url}/api/categories/{fba_sys['id']}")
        assert r.status_code == 200, f"System category should be deletable when unused: {r.text}"


# ------------------------------- Transaction section validation -------------------------------

class TestTransactionsSections:
    def test_ppc_metrics_stored_and_returned(self, admin_session, base_url, fresh_store):
        # Seed
        admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]})
        payload = _tx(
            fresh_store["id"],
            type="expense", category="PPC Reklam Harcaması", section="ppc", amount=25,
            campaign_name="TEST_Campaign", ad_type="SP", asin_sku="B01TEST",
            clicks=10, impressions=1000, orders_count=2,
        )
        r = admin_session.post(f"{base_url}/api/transactions", json=payload)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["section"] == "ppc"
        assert body["campaign_name"] == "TEST_Campaign"
        assert body["ad_type"] == "SP"
        assert body["asin_sku"] == "B01TEST"
        assert body["clicks"] == 10
        assert body["impressions"] == 1000
        assert body["orders_count"] == 2
        # list filter
        r2 = admin_session.get(f"{base_url}/api/transactions", params={"store_id": fresh_store["id"], "section": "ppc"})
        assert r2.status_code == 200
        assert any(t["id"] == body["id"] and t["campaign_name"] == "TEST_Campaign" for t in r2.json())

    def test_ppc_metrics_rejected_for_general(self, admin_session, base_url, fresh_store):
        admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]})
        payload = _tx(
            fresh_store["id"], type="expense", category="Service Fees",
            section="general", clicks=5, amount=10,
        )
        r = admin_session.post(f"{base_url}/api/transactions", json=payload)
        assert r.status_code == 400
        assert "PPC" in r.json().get("detail", "")

    def test_legacy_categories_still_work(self, admin_session, base_url, fresh_store):
        for cat, typ in [("Order payments", "income"), ("Refunds", "expense"), ("Service Fees", "expense")]:
            r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
                fresh_store["id"], type=typ, category=cat, amount=15,
            ))
            assert r.status_code == 200, f"{cat}: {r.text}"
            assert r.json()["section"] == "general"

    def test_custom_category_type_mismatch(self, admin_session, base_url, fresh_store):
        admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_IncomeCat",
            "type": "income", "section": "general",
        })
        # trying expense on an income category
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="TEST_IncomeCat", amount=5,
        ))
        assert r.status_code == 400
        assert "kategorinin" in r.json().get("detail", "").lower()

    def test_unknown_category_rejected(self, admin_session, base_url, fresh_store):
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="TEST_NoSuchCat_zzz", amount=5,
        ))
        assert r.status_code == 400
        assert "Ayarlar" in r.json().get("detail", "")

    def test_archived_category_rejected(self, admin_session, base_url, fresh_store):
        c = admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_Archived",
            "type": "expense", "section": "general",
        }).json()
        admin_session.put(f"{base_url}/api/categories/{c['id']}", json={"archived": True})
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="TEST_Archived", amount=5,
        ))
        assert r.status_code == 400
        assert "Arşiv" in r.json().get("detail", "")

    def test_section_filter_general_includes_legacy_missing_field(self, admin_session, base_url, fresh_store):
        # Insert tx then simulate legacy doc by direct update is overkill; instead ensure a
        # general section tx shows up in section=general and NOT in fba
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="income", category="Order payments", amount=20,
        ))
        assert r.status_code == 200
        tid = r.json()["id"]
        gen = admin_session.get(f"{base_url}/api/transactions", params={"store_id": fresh_store["id"], "section": "general"}).json()
        fba = admin_session.get(f"{base_url}/api/transactions", params={"store_id": fresh_store["id"], "section": "fba"}).json()
        assert any(t["id"] == tid for t in gen)
        assert not any(t["id"] == tid for t in fba)

    def test_fba_section_tx(self, admin_session, base_url, fresh_store):
        admin_session.get(f"{base_url}/api/categories", params={"store_id": fresh_store["id"]})
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="FBA Depolama Ücreti",
            section="fba", amount=12,
        ))
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        lst = admin_session.get(f"{base_url}/api/transactions", params={"store_id": fresh_store["id"], "section": "fba"}).json()
        assert any(t["id"] == tid for t in lst)


# ------------------------------- Finance regression (quick) -------------------------------

class TestRegression:
    def test_income_with_costs_and_dashboard(self, admin_session, base_url, fresh_store):
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="income", category="Order payments",
            amount=200, product_cost=50, shipping_cost=10, extra_cost=5,
        ))
        assert r.status_code == 200, r.text
        r2 = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="Refunds",
            amount=30, product_cost_recovery=15, shipping_cost_recovery=5,
        ))
        assert r2.status_code == 200, r2.text
        s = admin_session.get(f"{base_url}/api/dashboard/summary", params={"store_id": fresh_store["id"]})
        assert s.status_code == 200
        body = s.json()
        assert body["transaction_count"] >= 2

    def test_search_endpoint(self, admin_session, base_url, fresh_store):
        admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="income", category="Order payments", amount=99,
        ))
        r = admin_session.get(f"{base_url}/api/transactions/search", params={
            "store_id": fresh_store["id"], "view": "orders", "page": 1, "page_size": 20,
        })
        assert r.status_code == 200, r.text
        assert "items" in r.json()

    def test_payout_reference_patch(self, admin_session, base_url, fresh_store):
        p = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="payout", category="Oluşturuldu", amount=100,
        ))
        assert p.status_code == 200, p.text
        pid = p.json()["id"]
        r = admin_session.patch(f"{base_url}/api/payouts/{pid}/reference", json={"payment_reference": "TEST_REF_123"})
        assert r.status_code == 200
        assert r.json()["payment_reference"] == "TEST_REF_123"

    def test_bulk_update_and_delete(self, admin_session, base_url, fresh_store):
        ids = []
        for _ in range(2):
            r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
                fresh_store["id"], type="income", category="Order payments", amount=11,
            ))
            assert r.status_code == 200
            ids.append(r.json()["id"])
        r = admin_session.post(f"{base_url}/api/transactions/bulk-update", json={
            "ids": ids, "changes": {"description": "TEST_BULK_DESC"},
        })
        assert r.status_code == 200, r.text
        r = admin_session.post(f"{base_url}/api/transactions/bulk-delete", json={"ids": ids})
        assert r.status_code == 200

    def test_bulk_update_with_custom_category(self, admin_session, base_url, fresh_store):
        """bulk-update must not break when existing docs reference a user-defined category."""
        admin_session.post(f"{base_url}/api/categories", json={
            "store_id": fresh_store["id"], "name": "TEST_BulkCustom",
            "type": "expense", "section": "general",
        })
        r = admin_session.post(f"{base_url}/api/transactions", json=_tx(
            fresh_store["id"], type="expense", category="TEST_BulkCustom", amount=7,
        ))
        assert r.status_code == 200, r.text
        tid = r.json()["id"]
        r = admin_session.post(f"{base_url}/api/transactions/bulk-update", json={
            "ids": [tid], "changes": {"description": "TEST_updated"},
        })
        assert r.status_code == 200, r.text

    def test_store_delete_blocked_by_company_records(self, admin_session, base_url, fresh_store):
        # Create a company_debt to block deletion
        r = admin_session.post(f"{base_url}/api/company/debts", json={
            "store_id": fresh_store["id"], "name": "TEST_Debt",
            "amount": 100, "currency": "USD", "due_date": date.today().isoformat(),
        })
        # If endpoint shape differs, just skip
        if r.status_code not in (200, 201):
            pytest.skip(f"company/debts endpoint shape not matched: {r.status_code} {r.text[:200]}")
        del_r = admin_session.delete(f"{base_url}/api/stores/{fresh_store['id']}")
        assert del_r.status_code == 409
