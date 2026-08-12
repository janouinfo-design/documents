"""Tests for iteration 6:
- SwissCarInfo technical enrichment (unconfigured mode + apply endpoint + CAN guard)
- Document scan with as_pdf=1 assembly + JPEG regression
"""
import io
import os
import time
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from PIL import Image, ImageDraw
from pymongo import MongoClient

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")

backend_env = dotenv_values("/app/backend/.env")
MONGO_URL = backend_env.get("MONGO_URL") or os.environ.get("MONGO_URL")
DB_NAME = backend_env.get("DB_NAME") or os.environ.get("DB_NAME")

VEHICLE_ID = "d1099b53-a118-42d8-adfc-3d1b9e1fdcb0"  # BE 579928 per spec


# --------------------------- fixtures ---------------------------
@pytest.fixture(scope="module")
def api():
    s = requests.Session()
    s.headers.update({"Accept": "application/json"})
    return s


@pytest.fixture(scope="module")
def mongo():
    client = MongoClient(MONGO_URL)
    yield client[DB_NAME]
    client.close()


@pytest.fixture(scope="module")
def original_vehicle(api):
    r = api.get(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}")
    assert r.status_code == 200, r.text
    return r.json()


# --------------------------- 1. technical-data/status ---------------------------
class TestTechnicalDataStatus:
    def test_status_astra(self, api):
        r = api.get(f"{BASE_URL}/api/technical-data/status")
        assert r.status_code == 200
        d = r.json()
        assert isinstance(d["configured"], bool)
        assert d["provider"] == ("astra" if d["configured"] else None)


# --------------------------- 2. enrich-technical sans homologation ---------------------------
class TestEnrichTechnicalWithoutHomologation:
    def test_returns_explicit_french_error(self, api, mongo, original_vehicle):
        # Sans n° d'homologation NI VIN : 422 (plaque seule indisponible) ; 503 si données non importées.
        orig_h = original_vehicle.get("numero_homologation")
        orig_v = original_vehicle.get("vin")
        mongo.vehicles.update_one({"id": VEHICLE_ID},
                                  {"$set": {"numero_homologation": "", "vin": ""}})
        try:
            r = api.post(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/enrich-technical")
            assert r.status_code in (422, 503)
            detail = r.json().get("detail", "")
            assert "homologation" in detail.lower() or "astra" in detail.lower()
        finally:
            mongo.vehicles.update_one({"id": VEHICLE_ID},
                                      {"$set": {"numero_homologation": orig_h or "",
                                                "vin": orig_v or ""}})

    def test_returns_404_for_unknown_vehicle(self, api):
        r = api.post(f"{BASE_URL}/api/vehicles/does-not-exist-xyz/enrich-technical")
        assert r.status_code == 404


# --------------------------- 3. enrich-technical/apply ---------------------------
class TestEnrichApply:
    def test_apply_creates_field_meta_and_audit(self, api, mongo, original_vehicle):
        original_conso = original_vehicle.get("conso_officielle_l_100km")
        original_norme = original_vehicle.get("conso_officielle_norme")
        try:
            payload = {
                "fields": {"conso_officielle_l_100km": 6.5,
                           "conso_officielle_norme": "WLTP"},
                "matched_by": "homologation",
                "retrieved_at": "2026-06-20T10:00:00+00:00",
                "provider": "astra_tas",
            }
            r = api.post(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/enrich-technical/apply",
                         json=payload)
            assert r.status_code == 200, r.text
            data = r.json()
            assert data["ok"] is True
            assert data["applied"] >= 1
            v = data["vehicle"]
            assert v["conso_officielle_l_100km"] == 6.5
            assert v["conso_officielle_norme"] == "WLTP"

            # provenance visible via field-meta
            r2 = api.get(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/field-meta")
            assert r2.status_code == 200
            metas = r2.json()
            m = next((m for m in metas if m["field"] == "conso_officielle_l_100km"), None)
            assert m is not None, "field-meta absent"
            assert m["source"] == "external_vehicle_database"
            assert m["provider"] == "astra_tas"
            assert m.get("source_ref") == "homologation"

            # audit entry mentions 'Base officielle ASTRA/OFROU'
            r3 = api.get(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/history")
            assert r3.status_code == 200
            hist = r3.json()
            assert any("Base officielle ASTRA/OFROU" in (e.get("detail") or "")
                       for e in hist), "audit history missing ASTRA mention"
        finally:
            # restore original values
            restore = {}
            if original_conso is not None:
                restore["conso_officielle_l_100km"] = original_conso
            if original_norme is not None:
                restore["conso_officielle_norme"] = original_norme
            if restore:
                mongo.vehicles.update_one({"id": VEHICLE_ID}, {"$set": restore})
            # remove test-created field-meta rows for these two fields
            mongo.vehicle_field_meta.delete_many({
                "vehicle_id": VEHICLE_ID,
                "field": {"$in": ["conso_officielle_l_100km", "conso_officielle_norme"]},
                "provider": "swisscarinfo",
            })


# --------------------------- 4. CAN guard ---------------------------
class TestCanGuard:
    def test_apply_does_not_overwrite_can_locked_field(self, api, mongo, original_vehicle):
        original_co2 = original_vehicle.get("co2_g_km")
        # seed a navixy_can meta on co2_g_km
        mongo.vehicle_field_meta.update_one(
            {"vehicle_id": VEHICLE_ID, "field": "co2_g_km"},
            {"$set": {"vehicle_id": VEHICLE_ID, "field": "co2_g_km",
                      "provider": "navixy_can", "source": "can_bus",
                      "label": "CO₂ officiel (g/km)"}},
            upsert=True,
        )
        try:
            payload = {
                "fields": {"co2_g_km": 999.0},
                "matched_by": "plate",
                "retrieved_at": "2026-06-20T10:00:00+00:00",
            }
            r = api.post(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/enrich-technical/apply",
                         json=payload)
            assert r.status_code == 200, r.text
            data = r.json()
            # co2_g_km must NOT change
            v = data["vehicle"]
            assert v.get("co2_g_km") == original_co2, \
                f"CAN-locked field was overwritten: {v.get('co2_g_km')} vs {original_co2}"
            assert data["applied"] == 0
        finally:
            # remove test-created CAN meta
            mongo.vehicle_field_meta.delete_one(
                {"vehicle_id": VEHICLE_ID, "field": "co2_g_km", "provider": "navixy_can"})
            # ensure co2 restored (should still be same, but defensive)
            if original_co2 is not None:
                mongo.vehicles.update_one({"id": VEHICLE_ID},
                                          {"$set": {"co2_g_km": original_co2}})


# --------------------------- helpers for scan tests ---------------------------
def _make_text_jpeg(text: str, size=(900, 600)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    d.rectangle([10, 10, size[0] - 10, size[1] - 10], outline="black", width=3)
    d.text((40, 40), text, fill="black")
    d.text((40, 120), "PERMIS DE CIRCULATION", fill="black")
    d.text((40, 200), "Plaque: BE 579928", fill="black")
    d.text((40, 260), "VIN: TEST123ABCXYZ", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=88)
    return buf.getvalue()


def _cleanup_doc(api, mongo, doc_id):
    try:
        api.delete(f"{BASE_URL}/api/documents/{doc_id}")
    except Exception:
        pass
    mongo.documents.delete_one({"id": doc_id})


# --------------------------- 5. Scan as_pdf=1 ---------------------------
class TestScanAsPdf:
    def test_two_jpegs_assembled_into_single_pdf(self, api, mongo):
        img1 = _make_text_jpeg("PAGE 1 - test")
        img2 = _make_text_jpeg("PAGE 2 - test")
        files = [
            ("files", ("page1.jpg", img1, "image/jpeg")),
            ("files", ("page2.jpg", img2, "image/jpeg")),
        ]
        data = {"document_type": "permis_circulation", "as_pdf": "1"}
        r = api.post(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/documents/scan",
                     files=files, data=data, timeout=180)
        assert r.status_code == 200, r.text
        result = r.json()
        doc_id = result.get("document_id") or (result.get("document") or {}).get("id")
        assert doc_id, f"no document_id in response: {result}"
        try:
            # fetch document metadata
            listing = api.get(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/documents").json()
            doc = next((d for d in listing if d["id"] == doc_id), None)
            assert doc is not None
            assert doc["content_type"] == "application/pdf"
            assert doc["original_filename"].startswith("scan-")
            assert doc["original_filename"].endswith(".pdf")
            pages = doc.get("pages") or []
            assert len(pages) == 1, f"expected single pages entry, got {len(pages)}"
            # download via /api/files/
            r2 = api.get(f"{BASE_URL}/api/files/{doc['storage_path']}")
            assert r2.status_code == 200
            assert r2.headers.get("content-type", "").startswith("application/pdf")
            body = r2.content
            assert body[:4] == b"%PDF", "downloaded file is not a valid PDF"
            # OCR extraction should have populated something (best-effort)
            # not strictly asserting content since LLM latency may cause async pending
        finally:
            _cleanup_doc(api, mongo, doc_id)


# --------------------------- 6. Scan regression (no as_pdf) ---------------------------
class TestScanRegressionJpeg:
    def test_single_image_stays_jpeg(self, api, mongo):
        img = _make_text_jpeg("classic upload")
        files = [("files", ("classic.jpg", img, "image/jpeg"))]
        data = {"document_type": "permis_circulation"}
        r = api.post(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/documents/scan",
                     files=files, data=data, timeout=180)
        assert r.status_code == 200, r.text
        result = r.json()
        doc_id = result.get("document_id") or (result.get("document") or {}).get("id")
        assert doc_id
        try:
            listing = api.get(f"{BASE_URL}/api/vehicles/{VEHICLE_ID}/documents").json()
            doc = next((d for d in listing if d["id"] == doc_id), None)
            assert doc is not None
            assert "pdf" not in (doc["content_type"] or "").lower(), \
                f"content_type unexpectedly PDF: {doc['content_type']}"
            assert doc["original_filename"] == "classic.jpg"
        finally:
            _cleanup_doc(api, mongo, doc_id)
