import os

import requests


# Cleanup helper for temporary UI stores created in this iteration
BASE_URL = os.environ.get("REACT_APP_BACKEND_URL")


def test_cleanup_temp_filter_stores():
    if not BASE_URL:
        return
    base = BASE_URL.rstrip("/")
    session = requests.Session()
    login = session.post(f"{base}/api/auth/login", json={"email": "admin@amzsuite.com", "password": "admin123"}, timeout=20)
    assert login.status_code == 200
    token = login.json().get("token")
    assert token
    session.headers.update({"Authorization": f"Bearer {token}"})

    stores = session.get(f"{base}/api/stores", timeout=20)
    assert stores.status_code == 200
    for store in stores.json():
        if (store.get("name") or "").startswith("TEST_FILTER_UI_"):
            session.delete(f"{base}/api/stores/{store['id']}", timeout=20)
