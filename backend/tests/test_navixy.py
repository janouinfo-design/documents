"""Backend tests for LogiTrak Navixy integration (Iteration 2)."""
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    return s


# ----- Navixy status -----
def test_navixy_status_connected(session):
    r = session.get(f"{API}/navixy/status", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert data.get("configured") is True
    assert data.get("connected") is True, f"Navixy not connected: {data}"
    assert "trackers_count" in data
    assert data["trackers_count"] >= 1
    assert "imported_count" in data
    assert "account" in data
    print(f"Navixy status: trackers={data['trackers_count']} imported={data['imported_count']} account={data['account']}")


# ----- Sync -----
def test_navixy_sync_imports_fleet(session):
    r = session.post(f"{API}/navixy/sync", timeout=90)
    assert r.status_code == 200, r.text
    data = r.json()
    for k in ("synced", "created", "updated", "removed_demo"):
        assert k in data
    assert data["synced"] >= 1
    print(f"Sync result: {data}")

    # After sync, list all vehicles - all should be source=navixy
    rv = session.get(f"{API}/vehicles", timeout=30)
    assert rv.status_code == 200
    vehicles = rv.json()
    assert len(vehicles) >= 1
    non_navixy = [v for v in vehicles if v.get("source") != "navixy"]
    # exclude any TEST_ vehicles created earlier - but in this test there shouldn't be any
    non_navixy_real = [v for v in non_navixy if not v.get("plaque", "").startswith("TEST")]
    assert len(non_navixy_real) == 0, f"Found non-navixy vehicles after sync: {[v.get('plaque') for v in non_navixy_real]}"

    # Each should have navixy_tracker_id
    for v in vehicles:
        if v.get("source") == "navixy":
            assert v.get("navixy_tracker_id") is not None, f"Missing navixy_tracker_id on {v.get('plaque')}"

    # At least several should have kilometrage > 0
    with_km = [v for v in vehicles if (v.get("kilometrage") or 0) > 0]
    assert len(with_km) >= 1, "Expected at least one vehicle with kilometrage>0 from odometer"
    print(f"Vehicles with odometer>0: {len(with_km)}/{len(vehicles)}")


# ----- Live -----
def test_vehicle_live_for_navixy_vehicle(session):
    rv = session.get(f"{API}/vehicles", timeout=30)
    vehicles = [v for v in rv.json() if v.get("navixy_tracker_id")]
    assert vehicles, "No navixy-linked vehicles found"
    vid = vehicles[0]["id"]
    r = session.get(f"{API}/vehicles/{vid}/live", timeout=45)
    assert r.status_code == 200, r.text
    data = r.json()
    expected_keys = {"tracker_id", "connection_status", "movement_status", "lat", "lng",
                     "odometer_km", "gsm_network", "battery_level", "last_update"}
    assert expected_keys.issubset(set(data.keys())), f"Missing keys: {expected_keys - set(data.keys())}"
    assert data["tracker_id"] == vehicles[0]["navixy_tracker_id"]
    print(f"Live data ok for {vehicles[0].get('plaque')}: conn={data['connection_status']} mvt={data['movement_status']} odo={data['odometer_km']}")


def test_vehicle_live_for_manual_vehicle_returns_400(session):
    # Create manual vehicle
    payload = {
        "plaque": "TEST NAV 001",
        "marque": "Manual",
        "modele": "NoTracker",
        "annee": 2024,
    }
    rc = session.post(f"{API}/vehicles", json=payload, timeout=30)
    assert rc.status_code == 200
    vid = rc.json()["id"]
    try:
        r = session.get(f"{API}/vehicles/{vid}/live", timeout=30)
        assert r.status_code == 400, f"Expected 400, got {r.status_code}: {r.text}"
        body = r.json()
        # detail mentions non lié
        detail = body.get("detail", "")
        assert "Navixy" in detail or "tracker" in detail.lower()
    finally:
        session.delete(f"{API}/vehicles/{vid}", timeout=30)


# ----- Regression: PUT recalcs metrics -----
def test_put_vehicle_recomputes_metrics(session):
    rv = session.get(f"{API}/vehicles", timeout=30)
    vehicles = rv.json()
    assert vehicles
    vid = vehicles[0]["id"]
    upd = {"assurance": {"compagnie": "TEST Assur", "date_echeance": "2027-06-01", "prime_annuelle": 1234}}
    r = session.put(f"{API}/vehicles/{vid}", json=upd, timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    assert "metrics" in data
    assert data["metrics"]["assurance"]["level"] in {"ok", "warning", "critical", "expired", "unknown"}
    assert data["assurance"]["prime_annuelle"] == 1234


# ----- Regression: documents add + list -----
def test_documents_add_and_list(session):
    import io
    rv = session.get(f"{API}/vehicles", timeout=30)
    vid = rv.json()[0]["id"]
    files = {"file": ("nav_test.txt", io.BytesIO(b"navixy doc"), "text/plain")}
    data = {"folder": "Assurance"}
    r = session.post(f"{API}/vehicles/{vid}/documents", files=files, data=data, timeout=60)
    assert r.status_code == 200, r.text
    doc_id = r.json()["id"]
    r2 = session.get(f"{API}/vehicles/{vid}/documents", timeout=30)
    assert r2.status_code == 200
    assert any(d["id"] == doc_id for d in r2.json())
    session.delete(f"{API}/documents/{doc_id}", timeout=30)


# ----- Regression: dashboard + timeline still work -----
def test_dashboard_still_ok(session):
    r = session.get(f"{API}/dashboard", timeout=30)
    assert r.status_code == 200
    d = r.json()
    assert d["total_vehicles"] >= 1


def test_timeline_still_ok(session):
    r = session.get(f"{API}/timeline", timeout=30)
    assert r.status_code == 200
    assert isinstance(r.json(), list)
