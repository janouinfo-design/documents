"""Iteration 4 — Backend tests for the intelligent document scan feature."""
import io
import os
import time

import pytest
import requests
from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL")
            or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

TIMEOUT_SCAN = 120  # LLM call ~10-30s


# ---------------------------------------------------------------------------
# Helpers to generate synthetic swiss vehicle documents
# ---------------------------------------------------------------------------
def _font(size=22):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _render_jpg(lines: list[tuple[str, int]], size=(1200, 1600)) -> bytes:
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    # frame
    d.rectangle([20, 20, size[0]-20, size[1]-20], outline="black", width=3)
    y = 60
    for text, sz in lines:
        d.text((60, y), text, fill="black", font=_font(sz))
        y += sz + 14
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=90)
    return buf.getvalue()


def _permis_circulation_jpg() -> bytes:
    return _render_jpg([
        ("CONFEDERATION SUISSE — PERMIS DE CIRCULATION", 30),
        ("", 10),
        ("Immatriculation : VD 445566", 26),
        ("N° de chassis (VIN) : WAUZZZ8V5KA098765", 26),
        ("Marque : AUDI", 26),
        ("Modele : A3 SPORTBACK", 26),
        ("Variante / type : 8V", 26),
        ("Categorie : M1", 26),
        ("Carburant : Essence", 26),
        ("Cylindree : 1395 cm3", 26),
        ("Puissance : 110 kW", 26),
        ("Poids a vide : 1320 kg", 26),
        ("Poids total : 1850 kg", 26),
        ("Nombre de places : 5", 26),
        ("1re mise en circulation : 02.07.2019", 26),
        ("N° d'homologation : 1AB123", 26),
    ])


def _assurance_pdf() -> bytes:
    import fitz
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    txt = (
        "ATTESTATION D'ASSURANCE VEHICULE\n\n"
        "Compagnie : AXA Assurances SA\n"
        "N° de police : POL-123456\n"
        "Type de couverture : Casco complete\n"
        "Immatriculation : VD 445566\n"
        "VIN : WAUZZZ8V5KA098765\n"
        "Date de debut : 01.01.2026\n"
        "Date d'echeance : 31.12.2026\n"
        "Prime annuelle : 1450 CHF\n"
    )
    page.insert_text((60, 80), txt, fontsize=14)
    out = doc.tobytes()
    doc.close()
    return out


def _assurance_soon_pdf() -> bytes:
    """Assurance with date_echeance ~15 days in the future to trigger alerts."""
    import fitz
    from datetime import date, timedelta
    due = (date.today() + timedelta(days=15)).strftime("%d.%m.%Y")
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    txt = (
        "ATTESTATION D'ASSURANCE VEHICULE\n\n"
        "Compagnie : Zurich Assurances\n"
        "N° de police : POL-999888\n"
        "Type de couverture : Responsabilite civile\n"
        f"Date de debut : 01.01.2026\n"
        f"Date d'echeance : {due}\n"
        "Prime annuelle : 890 CHF\n"
    )
    page.insert_text((60, 80), txt, fontsize=14)
    out = doc.tobytes()
    doc.close()
    return out


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
@pytest.fixture(scope="module")
def session():
    s = requests.Session()
    return s


@pytest.fixture(scope="module")
def vehicles(session):
    r = session.get(f"{API}/vehicles", timeout=30)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def target_vehicle(vehicles):
    """Pick a Navixy vehicle that is NOT the one already used by main-agent tests."""
    reserved = "d1099b53-a118-42d8-adfc-3d1b9e1fdcb0"
    for v in vehicles:
        if v["id"] != reserved and (v.get("plaque") or "").strip():
            return v
    return vehicles[0]


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
class TestScanErrors:
    """Argument validation on POST /api/vehicles/{id}/documents/scan."""

    def test_unknown_vehicle_returns_404(self, session):
        img = _permis_circulation_jpg()
        r = session.post(f"{API}/vehicles/DOES-NOT-EXIST/documents/scan",
                         files=[("files", ("p.jpg", img, "image/jpeg"))], timeout=30)
        assert r.status_code == 404

    def test_no_file_returns_400(self, session, target_vehicle):
        r = session.post(f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
                         data={}, timeout=30)
        assert r.status_code == 400

    def test_bad_extension_returns_400(self, session, target_vehicle):
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("evil.zip", b"PK\x03\x04not-a-zip", "application/zip"))],
            timeout=30,
        )
        assert r.status_code == 400
        assert "Format" in r.text or "supporté" in r.text or "format" in r.text.lower()


class TestScanPermisJpg:
    """Full happy path — JPEG permis de circulation → extraction → validation."""

    @pytest.fixture(scope="class")
    def scan_result(self, session, target_vehicle):
        img = _permis_circulation_jpg()
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("permis.jpg", img, "image/jpeg"))],
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        return data

    def test_scan_response_shape(self, scan_result):
        assert scan_result["extraction_status"] == "done", scan_result
        assert scan_result["document_type"] == "permis_circulation"
        assert isinstance(scan_result["fields"], list)
        assert len(scan_result["fields"]) >= 5
        for f in scan_result["fields"]:
            assert "field" in f and "value" in f
            assert "confidence" in f and "current_value" in f and "conflict" in f

    def test_scan_detected_values(self, scan_result):
        by_key = {f["field"]: f for f in scan_result["fields"]}
        # Loose assertions — LLM may miss one, but plaque/vin/marque are usually solid
        must_have = {"plaque", "vin", "marque"}
        assert must_have.issubset(set(by_key)), f"missing keys: {must_have - set(by_key)}"
        assert "AUDI" in str(by_key["marque"]["value"]).upper()
        assert "WAUZZZ8V5KA098765" in str(by_key["vin"]["value"]).replace(" ", "")

    def test_validate_applies_only_sent_fields(self, session, target_vehicle, scan_result):
        doc_id = scan_result["document_id"]
        # Only send a subset — puissance_kw and type_carburant
        by_key = {f["field"]: f for f in scan_result["fields"]}
        payload_fields = {}
        for k in ("type_carburant", "puissance_kw", "cylindree_cm3"):
            if k in by_key and by_key[k].get("value") is not None:
                payload_fields[k] = by_key[k]["value"]
        assert payload_fields, "no expected fields detected — LLM regressed?"

        r = session.post(f"{API}/documents/{doc_id}/validate",
                         json={"document_type": "permis_circulation", "fields": payload_fields},
                         timeout=60)
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        assert data["applied"] >= 1
        v = data["vehicle"]
        # Root updates: puissance_kw / cylindree_cm3 / type_carburant live at root
        if "type_carburant" in payload_fields:
            assert (v.get("type_carburant") or "").lower().startswith("ess")

        # Document is now validated
        docs = session.get(f"{API}/vehicles/{target_vehicle['id']}/documents", timeout=30).json()
        this = next(d for d in docs if d["id"] == doc_id)
        assert this["extraction_status"] == "validated"
        assert this.get("folder") in ("Carte grise", "carte_grise", "Carte Grise")

    def test_field_meta_and_history(self, session, target_vehicle, scan_result):
        vid = target_vehicle["id"]
        metas = session.get(f"{API}/vehicles/{vid}/field-meta", timeout=30).json()
        assert isinstance(metas, list)
        sources = {m["field"]: m for m in metas if m.get("source") == "document_scan"}
        assert sources, "no vehicle_field_meta entries with source=document_scan"
        # At least one of the fields we just validated must appear
        assert any(k in sources for k in ("type_carburant", "puissance_kw", "cylindree_cm3"))
        for m in sources.values():
            assert "confidence" in m

        hist = session.get(f"{API}/vehicles/{vid}/history", timeout=30).json()
        assert isinstance(hist, list) and hist
        joined = " ".join(str(h.get("detail", "") or h.get("message", "")) for h in hist)
        assert "→" in joined or "->" in joined or "source" in joined.lower()


class TestScanPdfAssurance:
    def test_assurance_pdf_detection(self, session, target_vehicle):
        pdf = _assurance_pdf()
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("assur.pdf", pdf, "application/pdf"))],
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["extraction_status"] == "done", data
        assert data["document_type"] == "assurance"
        keys = {f["field"] for f in data["fields"]}
        # Must at least detect compagnie or numero_police + date_echeance
        assert keys & {"compagnie", "numero_police", "date_echeance"}
        # Save doc_id for re-analyse test
        pytest.assurance_doc_id = data["document_id"]

    def test_reanalyse_with_document_id(self, session, target_vehicle):
        """POST scan with document_id (no re-upload) should re-extract without duplicating."""
        doc_id = getattr(pytest, "assurance_doc_id", None)
        if not doc_id:
            pytest.skip("assurance scan didn't run")
        vid = target_vehicle["id"]
        docs_before = session.get(f"{API}/vehicles/{vid}/documents", timeout=30).json()
        n_before = len(docs_before)

        r = session.post(
            f"{API}/vehicles/{vid}/documents/scan",
            data={"document_id": doc_id, "document_type": "assurance"},
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["document_id"] == doc_id
        assert data["extraction_status"] == "done"

        docs_after = session.get(f"{API}/vehicles/{vid}/documents", timeout=30).json()
        assert len(docs_after) == n_before, "re-analyse must NOT create a new document"


class TestNavixyProtection:
    """A validated VIN must survive a Navixy sync (except kilometrage)."""

    def test_navixy_sync_preserves_validated_vin(self, session, vehicles):
        # Use the vehicle already validated by the main agent
        vid = "d1099b53-a118-42d8-adfc-3d1b9e1fdcb0"
        v = next((x for x in vehicles if x["id"] == vid), None)
        if not v:
            pytest.skip("main-agent seed vehicle missing")
        vin_before = v.get("vin")
        km_before = v.get("kilometrage")
        assert vin_before, "expected validated VIN on seed vehicle"

        r = session.post(f"{API}/navixy/sync", timeout=60)
        assert r.status_code == 200, r.text

        v_after = session.get(f"{API}/vehicles/{vid}", timeout=30).json()
        assert v_after.get("vin") == vin_before, (
            f"navixy sync overwrote a validated VIN: {vin_before} -> {v_after.get('vin')}"
        )
        # kilometrage may or may not change — just make sure the key still exists
        assert "kilometrage" in v_after


class TestAlertsFromValidatedInsurance:
    def test_validated_insurance_creates_alert(self, session, target_vehicle):
        # 1. scan a soon-expiring assurance
        pdf = _assurance_soon_pdf()
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("assur_soon.pdf", pdf, "application/pdf"))],
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["extraction_status"] == "done"
        by_key = {f["field"]: f for f in data["fields"]}
        if "date_echeance" not in by_key or by_key["date_echeance"].get("value") is None:
            pytest.skip("LLM did not extract date_echeance — cannot test alert trigger")

        # 2. Validate
        payload = {"document_type": "assurance",
                   "fields": {"date_echeance": by_key["date_echeance"]["value"]}}
        rv = session.post(f"{API}/documents/{data['document_id']}/validate",
                          json=payload, timeout=60)
        assert rv.status_code == 200

        # 3. Kick alert engine
        session.post(f"{API}/alerts/run", timeout=60)

        # 4. Fetch alerts
        alerts = session.get(f"{API}/alerts", timeout=30).json()
        items = alerts.get("items", [])
        # We should find one for this vehicle w/ assurance echeance
        matches = [a for a in items
                   if a.get("vehicle_id") == target_vehicle["id"]
                   and "assur" in (a.get("type") or "").lower()]
        assert matches, f"no assurance alert found for vehicle {target_vehicle['id']}"


class TestRegression:
    """Make sure existing endpoints keep working."""

    def test_dashboard(self, session):
        r = session.get(f"{API}/dashboard", timeout=30)
        assert r.status_code == 200
        d = r.json()
        for k in ("total_vehicles", "vehicles_conformes"):
            assert k in d

    def test_timeline(self, session):
        r = session.get(f"{API}/timeline", timeout=30)
        assert r.status_code == 200
        assert isinstance(r.json(), list)

    def test_alerts(self, session):
        r = session.get(f"{API}/alerts", timeout=30)
        assert r.status_code == 200
        j = r.json()
        assert "items" in j and "stats" in j

    def test_navixy_status(self, session):
        r = session.get(f"{API}/navixy/status", timeout=30)
        assert r.status_code == 200
        assert "connected" in r.json()

    def test_vehicles_list_and_get(self, session, vehicles):
        v = vehicles[0]
        r = session.get(f"{API}/vehicles/{v['id']}", timeout=30)
        assert r.status_code == 200
        assert r.json()["id"] == v["id"]

    def test_classic_upload_still_works(self, session, target_vehicle):
        # POST /api/vehicles/{id}/documents (classic upload, no scan)
        files = [("file", ("note.jpg", _render_jpg([("NOTE", 40)], (400, 300)), "image/jpeg"))]
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents",
            files=files, data={"folder": "Divers"}, timeout=30,
        )
        assert r.status_code in (200, 201), r.text
        # Cleanup
        doc = r.json()
        if isinstance(doc, dict) and doc.get("id"):
            session.delete(f"{API}/documents/{doc['id']}", timeout=15)
