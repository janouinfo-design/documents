"""Backend tests for LogiTrak Gestion Administrative de Flotte."""
import io
import os
import time
import pytest
import requests

BASE_URL = os.environ.get("REACT_APP_BACKEND_URL", "https://fleet-admin-hub-7.preview.emergentagent.com").rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    return s


# ----- Dashboard -----
def test_dashboard_kpis(session):
    r = session.get(f"{API}/dashboard", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    expected_keys = {
        "total_vehicles", "leasing_expired", "leasing_soon", "assurance_renew",
        "controle_upcoming", "documents_missing", "cout_leasing_mensuel",
        "cout_assurance_annuel", "vehicles_conformes"
    }
    assert expected_keys.issubset(set(data.keys())), f"Missing keys: {expected_keys - set(data.keys())}"
    assert data["total_vehicles"] >= 6
    assert isinstance(data["cout_leasing_mensuel"], (int, float))
    assert isinstance(data["cout_assurance_annuel"], (int, float))
    # After Navixy auto-sync, demo vehicles are removed; Navixy fleet has no leasing/assurance data
    assert data["cout_leasing_mensuel"] >= 0
    assert data["cout_assurance_annuel"] >= 0


# ----- Vehicles list -----
def test_list_vehicles_with_metrics(session):
    r = session.get(f"{API}/vehicles", timeout=30)
    assert r.status_code == 200
    vehicles = r.json()
    assert isinstance(vehicles, list)
    assert len(vehicles) >= 6
    v = vehicles[0]
    for key in ("id", "plaque", "marque", "modele", "metrics"):
        assert key in v
    m = v["metrics"]
    assert "leasing" in m and "assurance" in m and "controle" in m
    assert "overall" in m and "compliant" in m
    assert m["leasing"]["level"] in {"ok", "warning", "critical", "expired", "unknown"}


def test_get_vehicle_detail(session):
    r = session.get(f"{API}/vehicles", timeout=30)
    vid = r.json()[0]["id"]
    r2 = session.get(f"{API}/vehicles/{vid}", timeout=30)
    assert r2.status_code == 200
    v = r2.json()
    assert v["id"] == vid
    m = v["metrics"]["leasing"]
    assert "months_remaining" in m
    assert "percent_used" in m
    assert "cost_remaining" in m


def test_get_vehicle_404(session):
    r = session.get(f"{API}/vehicles/does-not-exist", timeout=30)
    assert r.status_code == 404


# ----- Vehicle CRUD -----
def test_create_update_delete_vehicle(session):
    payload = {
        "plaque": "TEST 999 000",
        "marque": "TestMarque",
        "modele": "TestModele",
        "annee": 2024,
        "kilometrage": 1000,
        "leasing": {
            "societe": "TestLeasing", "date_debut": "2024-01-01",
            "date_fin": "2027-01-01", "mensualite_chf": 1000, "duree_mois": 36
        },
        "assurance": {"compagnie": "TestIns", "date_echeance": "2026-06-01", "prime_annuelle": 1200},
        "carte_grise": {"date_mise_circulation": "2024-01-15", "poids_total": 3500, "nombre_places": 3},
        "controle_technique": {"date_prochain": "2027-03-01", "centre": "Test centre", "resultat": "Conforme"}
    }
    r = session.post(f"{API}/vehicles", json=payload, timeout=30)
    assert r.status_code == 200, r.text
    v = r.json()
    assert v["plaque"] == payload["plaque"]
    assert "metrics" in v
    vid = v["id"]

    # Update leasing - send full leasing object
    upd = {"leasing": {**payload["leasing"], "mensualite_chf": 1500}}
    r2 = session.put(f"{API}/vehicles/{vid}", json=upd, timeout=30)
    assert r2.status_code == 200
    assert r2.json()["leasing"]["mensualite_chf"] == 1500
    assert "metrics" in r2.json()

    # Get to verify persistence
    r3 = session.get(f"{API}/vehicles/{vid}", timeout=30)
    assert r3.status_code == 200
    assert r3.json()["leasing"]["mensualite_chf"] == 1500

    # Delete
    r4 = session.delete(f"{API}/vehicles/{vid}", timeout=30)
    assert r4.status_code == 200
    r5 = session.get(f"{API}/vehicles/{vid}", timeout=30)
    assert r5.status_code == 404


# ----- Upload / serve round-trip -----
def test_upload_and_serve_roundtrip(session):
    content = b"hello logitrak file storage test"
    files = {"file": ("test.txt", io.BytesIO(content), "text/plain")}
    data = {"vehicle_id": "misc"}
    r = session.post(f"{API}/upload", files=files, data=data, timeout=60)
    assert r.status_code == 200, r.text
    body = r.json()
    assert "path" in body
    path = body["path"]
    # Serve
    r2 = session.get(f"{API}/files/{path}", timeout=60)
    assert r2.status_code == 200
    assert r2.content == content


# ----- Documents -----
def test_add_list_delete_document(session):
    vehicles = session.get(f"{API}/vehicles", timeout=30).json()
    vid = vehicles[0]["id"]
    files = {"file": ("contract.txt", io.BytesIO(b"contract data"), "text/plain")}
    data = {"folder": "Leasing"}
    r = session.post(f"{API}/vehicles/{vid}/documents", files=files, data=data, timeout=60)
    assert r.status_code == 200, r.text
    doc = r.json()
    assert doc["folder"] == "Leasing"
    doc_id = doc["id"]

    # List
    r2 = session.get(f"{API}/vehicles/{vid}/documents", timeout=30)
    assert r2.status_code == 200
    assert any(d["id"] == doc_id for d in r2.json())

    # Soft-delete
    r3 = session.delete(f"{API}/documents/{doc_id}", timeout=30)
    assert r3.status_code == 200
    r4 = session.get(f"{API}/vehicles/{vid}/documents", timeout=30)
    assert all(d["id"] != doc_id for d in r4.json())


# ----- Inspections -----
def test_create_list_delete_inspection(session):
    vehicles = session.get(f"{API}/vehicles", timeout=30).json()
    vid = vehicles[0]["id"]
    payload = {
        "date": "2026-01-10",
        "responsable": "Test responsable",
        "kilometrage": 12345,
        "commentaire": "Test inspection",
        "photos": [{"angle": "avant", "url": "https://example.com/x.jpg", "kind": "image"}]
    }
    r = session.post(f"{API}/vehicles/{vid}/inspections", json=payload, timeout=30)
    assert r.status_code == 200
    ins = r.json()
    assert ins["responsable"] == "Test responsable"
    ins_id = ins["id"]

    r2 = session.get(f"{API}/vehicles/{vid}/inspections", timeout=30)
    assert r2.status_code == 200
    assert any(i["id"] == ins_id for i in r2.json())

    r3 = session.delete(f"{API}/inspections/{ins_id}", timeout=30)
    assert r3.status_code == 200


# ----- Timeline -----
def test_timeline(session):
    r = session.get(f"{API}/timeline", timeout=30)
    assert r.status_code == 200
    events = r.json()
    assert isinstance(events, list)
    assert len(events) > 0
    e = events[0]
    for k in ("vehicle_id", "plaque", "type", "label", "date", "days_remaining", "level"):
        assert k in e
    # sorted by date ascending
    dates = [e["date"] for e in events]
    assert dates == sorted(dates)
