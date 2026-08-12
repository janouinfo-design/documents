"""Iteration 3 tests: deadline alerts engine + OCR carte grise (GPT-4o)."""
import io
import os
import pytest
import requests
from PIL import Image, ImageDraw, ImageFont

BASE_URL = os.environ["REACT_APP_BACKEND_URL"].rstrip("/")
API = f"{BASE_URL}/api"


@pytest.fixture(scope="module")
def session():
    return requests.Session()


def _build_carte_grise_image() -> bytes:
    """Generate a synthetic but realistic-looking Swiss carte grise as PNG."""
    img = Image.new("RGB", (900, 560), (245, 240, 220))
    d = ImageDraw.Draw(img)
    # background features so it's not a flat color
    for y in range(0, 560, 20):
        d.line([(0, y), (900, y)], fill=(235, 230, 210), width=1)
    d.rectangle([20, 20, 880, 540], outline=(80, 60, 30), width=3)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 28)
        font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 30)
        small = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 20)
    except Exception:
        title_font = font = small = ImageFont.load_default()
    d.text((40, 40), "CONFEDERATION SUISSE", fill=(20, 20, 20), font=title_font)
    d.text((40, 78), "Permis de circulation / Carte grise", fill=(20, 20, 20), font=small)
    d.line([(40, 110), (860, 110)], fill=(80, 60, 30), width=2)

    rows = [
        ("Plaque d'immatriculation :", "GE 123 456"),
        ("VIN / No de chassis :", "WDB9066331234567"),
        ("Mise en circulation :", "15.03.2021"),
        ("Poids total (kg) :", "3500"),
        ("Nombre de places :", "3"),
        ("Marque :", "Mercedes-Benz"),
        ("Modele :", "Sprinter 316"),
    ]
    y = 140
    for label, value in rows:
        d.text((50, y), label, fill=(40, 40, 40), font=small)
        d.text((420, y - 4), value, fill=(0, 0, 0), font=font)
        y += 52

    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


# ---------- Alerts engine ----------
def test_alerts_list_structure(session):
    r = session.get(f"{API}/alerts", timeout=30)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("items", "stats", "email_enabled", "recipients"):
        assert key in data
    assert isinstance(data["items"], list)
    assert data["email_enabled"] is False
    assert isinstance(data["recipients"], list)
    s = data["stats"]
    for key in ("total", "expired", "critical", "warning"):
        assert key in s and isinstance(s[key], int)
    assert s["total"] == len(data["items"])
    # The seed/Navixy fleet should produce a couple of due-soon items
    assert s["total"] >= 1
    # Each item has the expected fields
    for it in data["items"]:
        assert it["level"] in ("expired", "critical", "warning")
        assert it["type"] in ("leasing", "assurance", "controle")
        assert it.get("plaque")
        assert it.get("due_date")


def test_alerts_run_and_idempotence(session):
    # First run
    r1 = session.post(f"{API}/alerts/run", timeout=60)
    assert r1.status_code == 200, r1.text
    d1 = r1.json()
    for key in ("created", "emails_sent", "digest_status", "upcoming", "email_enabled"):
        assert key in d1
    assert d1["email_enabled"] is False
    # Email is mocked - nothing should ever be "sent"
    assert d1["emails_sent"] == 0
    assert d1["digest_status"] in ("mocked", "skipped")

    # Second run - must not duplicate threshold alerts nor today's digest
    r2 = session.post(f"{API}/alerts/run", timeout=60)
    assert r2.status_code == 200, r2.text
    d2 = r2.json()
    assert d2["created"] == 0, f"Re-run created duplicates: {d2}"
    assert d2["digest_status"] == "skipped", f"Digest duplicated: {d2}"


def test_alerts_log(session):
    # Ensure the engine has run
    session.post(f"{API}/alerts/run", timeout=60)
    r = session.get(f"{API}/alerts/log", timeout=30)
    assert r.status_code == 200
    log = r.json()
    assert isinstance(log, list)
    assert len(log) >= 1
    kinds = {e.get("kind") for e in log}
    # threshold entries should exist; digest only if any upcoming
    assert "threshold" in kinds or "digest" in kinds
    for entry in log:
        # everything should be marked as mocked (no provider configured)
        if entry.get("kind") in ("threshold", "digest"):
            assert entry.get("status") == "mocked", entry


# ---------- OCR carte grise ----------
@pytest.mark.skip(reason="Endpoint /carte-grise/ocr remplacé par /documents/scan — couvert par test_docscan.py")
def test_ocr_carte_grise_extracts_plate_and_vin(session):
    vehicles = session.get(f"{API}/vehicles", timeout=30).json()
    assert vehicles, "No vehicles available for OCR test"
    vid = vehicles[0]["id"]

    img_bytes = _build_carte_grise_image()
    files = {"file": ("carte_grise.png", io.BytesIO(img_bytes), "image/png")}
    r = session.post(f"{API}/vehicles/{vid}/carte-grise/ocr", files=files, timeout=120)
    assert r.status_code == 200, r.text
    data = r.json()
    for key in ("plaque", "vin", "date_mise_circulation", "poids_total", "nombre_places"):
        assert key in data
    plate = (data["plaque"] or "").upper().replace(" ", "")
    vin = (data["vin"] or "").upper().replace(" ", "")
    # At minimum the model should read the plate and the VIN per spec
    assert "GE123456" in plate, f"Plate not extracted, got {data['plaque']!r}"
    assert vin == "WDB9066331234567", f"VIN not extracted exactly, got {data['vin']!r}"
    # Bonus: validate other fields softly (model may sometimes miss)
    if data.get("date_mise_circulation"):
        assert data["date_mise_circulation"] == "2021-03-15"
    if data.get("poids_total"):
        assert data["poids_total"] == 3500
    if data.get("nombre_places"):
        assert data["nombre_places"] == 3
