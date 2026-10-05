import os
import uuid
from decimal import Decimal

import pytest
import requests


# Transactions search + payout reference feature regression coverage
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")
ADMIN_EMAIL = "admin@amzsuite.com"
ADMIN_PASSWORD = "admin123"
OTHER_EMAIL = "test_3a991703@example.com"
OTHER_PASSWORD = "testpass123"


@pytest.fixture(scope="session")
def base_url():
    if not BASE_URL:
        pytest.skip("REACT_APP_BACKEND_URL not set")
    return BASE_URL.rstrip("/")


@pytest.fixture
def admin_session(base_url):
    session = requests.Session()
    login = session.post(
        f"{base_url}/api/auth/login",
        json={"email": ADMIN_EMAIL, "password": ADMIN_PASSWORD},
        timeout=20,
    )
    assert login.status_code == 200
    token = login.json().get("token")
    assert isinstance(token, str) and token
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture
def other_user_session(base_url):
    session = requests.Session()
    login = session.post(
        f"{base_url}/api/auth/login",
        json={"email": OTHER_EMAIL, "password": OTHER_PASSWORD},
        timeout=20,
    )
    if login.status_code != 200:
        pytest.skip("Other isolation user login failed")
    token = login.json().get("token")
    if not token:
        pytest.skip("Other isolation user token missing")
    session.headers.update({"Authorization": f"Bearer {token}"})
    return session


@pytest.fixture
def isolated_store(admin_session, base_url):
    payload = {
        "name": f"TEST_FILTER_{uuid.uuid4().hex[:8]}",
        "marketplaces": ["US", "CA"],
        "default_currency": "USD",
    }
    created = admin_session.post(f"{base_url}/api/stores", json=payload, timeout=20)
    assert created.status_code == 200
    store = created.json()
    assert store["name"].startswith("TEST_FILTER_")
    yield store
    admin_session.delete(f"{base_url}/api/stores/{store['id']}", timeout=20)


def _tx(store_id, **overrides):
    payload = {
        "store_id": store_id,
        "marketplace": "US",
        "type": "income",
        "category": "Order payments",
        "amount": 100,
        "currency": "USD",
        "date": "2026-01-10",
        "description": "",
        "order_id": f"ORD-{uuid.uuid4().hex[:6]}",
        "payment_reference": "",
        "product_cost": 0,
        "shipping_cost": 0,
        "extra_cost": 0,
        "product_cost_recovery": 0,
        "shipping_cost_recovery": 0,
    }
    payload.update(overrides)
    return payload


def _create_tx(session, base_url, payload):
    response = session.post(f"{base_url}/api/transactions", json=payload, timeout=20)
    assert response.status_code == 200
    return response.json()


def _search(session, base_url, **params):
    response = session.get(f"{base_url}/api/transactions/search", params=params, timeout=20)
    return response


def _order_net_and_margin(rows):
    revenue = Decimal("0")
    expenses = Decimal("0")
    recoveries = Decimal("0")
    for row in rows:
        amount = Decimal(str(row["amount_usd"]))
        if row["type"] == "income":
            revenue += amount
            expenses += Decimal(str(row["usd_costs"].get("product_cost", 0)))
            expenses += Decimal(str(row["usd_costs"].get("shipping_cost", 0)))
            expenses += Decimal(str(row["usd_costs"].get("extra_cost", 0)))
        else:
            expenses += amount
        if row["category"] == "Refunds":
            recoveries += Decimal(str(row["usd_costs"].get("product_cost_recovery", 0)))
            recoveries += Decimal(str(row["usd_costs"].get("shipping_cost_recovery", 0)))
    net = revenue - (expenses - recoveries)
    margin = (net / revenue * Decimal("100")) if revenue > 0 else None
    return net, margin


def test_search_order_id_literal_trim_and_case_insensitive(admin_session, base_url, isolated_store):
    created = _create_tx(
        admin_session,
        base_url,
        _tx(isolated_store["id"], order_id="ORD-ABC.123", amount=50, date="2026-01-10"),
    )

    res = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        search="  abc.123  ",
        page=1,
        page_size=20,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert any(row["id"] == created["id"] for row in data["items"])


def test_orders_refund_date_filter_returns_whole_order_preserving_children(admin_session, base_url, isolated_store):
    order_id = f"TEST-ORDER-{uuid.uuid4().hex[:5]}"
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=order_id, date="2026-01-10", amount=100, product_cost=20))
    _create_tx(
        admin_session,
        base_url,
        _tx(
            isolated_store["id"],
            order_id=order_id,
            type="expense",
            category="Refunds",
            date="2026-02-10",
            amount=30,
            product_cost_recovery=5,
            product_cost=0,
            shipping_cost=0,
            extra_cost=0,
        ),
    )
    _create_tx(
        admin_session,
        base_url,
        _tx(
            isolated_store["id"],
            order_id=order_id,
            type="expense",
            category="Service Fees",
            date="2026-03-10",
            amount=10,
            product_cost=0,
            shipping_cost=0,
            extra_cost=0,
        ),
    )

    res = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        category="Refunds",
        start_date="2026-02-10",
        end_date="2026-02-10",
        page=1,
        page_size=20,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 3
    dates = sorted([item["date"] for item in data["items"]])
    assert dates == ["2026-01-10", "2026-02-10", "2026-03-10"]

    net, margin = _order_net_and_margin(data["items"])
    assert net == Decimal("45")
    assert margin is not None and round(float(margin), 2) == 45.0


def test_orders_require_same_child_for_date_and_category(admin_session, base_url, isolated_store):
    order_id = f"TEST-ORDER-{uuid.uuid4().hex[:5]}"
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=order_id, date="2026-01-10", amount=100))
    _create_tx(
        admin_session,
        base_url,
        _tx(
            isolated_store["id"],
            order_id=order_id,
            type="expense",
            category="Refunds",
            date="2026-02-10",
            amount=30,
            product_cost=0,
            shipping_cost=0,
            extra_cost=0,
        ),
    )

    res = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        category="Refunds",
        start_date="2026-01-10",
        end_date="2026-01-10",
        page=1,
        page_size=20,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_blank_order_ids_stay_separate_groups(admin_session, base_url, isolated_store):
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id="", amount=11))
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id="   ", amount=22, date="2026-01-11"))

    res = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        page=1,
        page_size=20,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert len(data["items"]) == 2


def test_same_order_id_not_combined_across_store_marketplace_currency(admin_session, base_url, isolated_store):
    same_order = f"SAME-{uuid.uuid4().hex[:5]}"

    # Store A / US / USD
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=same_order, marketplace="US", currency="USD", amount=40))

    # Store A / CA / CAD
    _create_tx(
        admin_session,
        base_url,
        _tx(
            isolated_store["id"],
            order_id=same_order,
            marketplace="CA",
            currency="CAD",
            amount=40,
        ),
    )

    # Store B / US / USD
    second_store = admin_session.post(
        f"{base_url}/api/stores",
        json={"name": f"TEST_FILTER_{uuid.uuid4().hex[:8]}", "marketplaces": ["US"], "default_currency": "USD"},
        timeout=20,
    )
    assert second_store.status_code == 200
    second_id = second_store.json()["id"]
    try:
        _create_tx(admin_session, base_url, _tx(second_id, order_id=same_order, marketplace="US", currency="USD", amount=55))

        # Query isolated store, US/USD only; must not pull CA or second store records.
        res = _search(
            admin_session,
            base_url,
            store_id=isolated_store["id"],
            marketplace="US",
            currency="USD",
            view="orders",
            search=same_order,
            page=1,
            page_size=20,
        )
        assert res.status_code == 200
        data = res.json()
        assert data["total"] == 1
        assert len(data["items"]) == 1
        assert data["items"][0]["store_id"] == isolated_store["id"]
        assert data["items"][0]["marketplace"] == "US"
        assert data["items"][0]["currency"] == "USD"
    finally:
        admin_session.delete(f"{base_url}/api/stores/{second_id}", timeout=20)


def test_group_pagination_counts_groups_not_children(admin_session, base_url, isolated_store):
    order_group = f"TEST-GRP-{uuid.uuid4().hex[:4]}"
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=order_group, date="2026-04-01"))
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=order_group, type="expense", category="Refunds", amount=10, date="2026-04-02", product_cost=0, shipping_cost=0, extra_cost=0))
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=order_group, type="expense", category="Service Fees", amount=5, date="2026-04-03", product_cost=0, shipping_cost=0, extra_cost=0))
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=f"TEST-SECOND-{uuid.uuid4().hex[:4]}", date="2026-03-01", amount=20))

    res = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        page=1,
        page_size=1,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 2
    assert data["total_pages"] == 2
    assert len(data["items"]) == 3


def test_outcome_filter_applies_before_group_pagination(admin_session, base_url, isolated_store):
    profitable = f"PROFIT-{uuid.uuid4().hex[:5]}"
    losing = f"LOSS-{uuid.uuid4().hex[:5]}"
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=profitable, amount=100, product_cost=10, date="2026-05-10"))
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=losing, amount=50, product_cost=0, date="2026-05-09"))
    _create_tx(admin_session, base_url, _tx(isolated_store["id"], order_id=losing, type="expense", category="Service Fees", amount=70, date="2026-05-11", product_cost=0, shipping_cost=0, extra_cost=0))

    res = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        outcome="profit",
        page=1,
        page_size=1,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["order_id"] == profitable


def test_search_rejects_inverted_or_malformed_dates(admin_session, base_url, isolated_store):
    inverted = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        start_date="2026-05-31",
        end_date="2026-05-01",
    )
    assert inverted.status_code == 422

    malformed = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="orders",
        start_date="bad-date",
    )
    assert malformed.status_code == 422


def test_payout_reference_create_trim_search_and_income_reject(admin_session, base_url, isolated_store):
    payout = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(
            isolated_store["id"],
            type="payout",
            category="Oluşturuldu",
            order_id="",
            amount=88,
            date="2026-06-01",
            description="legacy NOTE zebra",
            payment_reference="  TRANSFER-ABC123  ",
        ),
        timeout=20,
    )
    assert payout.status_code == 200
    payout_data = payout.json()
    assert payout_data["payment_reference"] == "TRANSFER-ABC123"

    income_bad = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(
            isolated_store["id"],
            type="income",
            category="Order payments",
            amount=10,
            payment_reference="NOT-ALLOWED",
        ),
        timeout=20,
    )
    assert income_bad.status_code == 400

    by_reference = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="payouts",
        search="abc123",
    )
    assert by_reference.status_code == 200
    assert by_reference.json()["total"] == 1

    by_note = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="payouts",
        search="note zebra",
    )
    assert by_note.status_code == 200
    assert by_note.json()["total"] == 1


def test_patch_payout_reference_edit_clear_and_ownership_rules(admin_session, other_user_session, base_url, isolated_store):
    payout = _create_tx(
        admin_session,
        base_url,
        _tx(
            isolated_store["id"],
            type="payout",
            category="Bankada",
            order_id="",
            amount=101,
            date="2026-07-02",
            description="keep me",
            payment_reference="INIT-REF",
        ),
    )
    original = {k: payout[k] for k in ["amount", "date", "category", "currency", "marketplace", "description"]}

    updated = admin_session.patch(
        f"{base_url}/api/payouts/{payout['id']}/reference",
        json={"payment_reference": "  NEW-REF  "},
        timeout=20,
    )
    assert updated.status_code == 200
    data = updated.json()
    assert data["payment_reference"] == "NEW-REF"
    for key, value in original.items():
        assert data[key] == value

    cleared = admin_session.patch(
        f"{base_url}/api/payouts/{payout['id']}/reference",
        json={"payment_reference": "   "},
        timeout=20,
    )
    assert cleared.status_code == 200
    assert cleared.json()["payment_reference"] == ""

    other_user = other_user_session.patch(
        f"{base_url}/api/payouts/{payout['id']}/reference",
        json={"payment_reference": "SHOULD-FAIL"},
        timeout=20,
    )
    assert other_user.status_code == 404

    income = _create_tx(admin_session, base_url, _tx(isolated_store["id"], amount=77, order_id=f"INC-{uuid.uuid4().hex[:4]}"))
    wrong_type = admin_session.patch(
        f"{base_url}/api/payouts/{income['id']}/reference",
        json={"payment_reference": "NOPE"},
        timeout=20,
    )
    assert wrong_type.status_code == 404


def test_payout_reference_max_length_and_payout_pagination(admin_session, base_url, isolated_store):
    too_long = "R" * 201
    invalid = admin_session.post(
        f"{base_url}/api/transactions",
        json=_tx(
            isolated_store["id"],
            type="payout",
            category="İşleniyor",
            order_id="",
            amount=10,
            payment_reference=too_long,
        ),
        timeout=20,
    )
    assert invalid.status_code == 422

    for i in range(25):
        day = (i % 28) + 1
        _create_tx(
            admin_session,
            base_url,
            _tx(
                isolated_store["id"],
                type="payout",
                category="Oluşturuldu",
                order_id="",
                amount=5 + i,
                date=f"2026-08-{day:02d}",
                description=f"legacy-batch-{i}",
                payment_reference=f"BATCH-{i}",
            ),
        )

    page3 = _search(
        admin_session,
        base_url,
        store_id=isolated_store["id"],
        marketplace="US",
        currency="USD",
        view="payouts",
        page=3,
        page_size=10,
    )
    assert page3.status_code == 200
    data = page3.json()
    assert data["total"] == 25
    assert data["total_pages"] == 3
    assert data["page"] == 3
    assert len(data["items"]) == 5