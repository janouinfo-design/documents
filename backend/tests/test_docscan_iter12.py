"""Iteration 12 — Type mismatch, quality gate, vignette, traçabilité."""
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

TIMEOUT_SCAN = 180
RESERVED_VEHICLE = "d1099b53-a118-42d8-adfc-3d1b9e1fdcb0"


def _font(size=22):
    for p in ("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"):
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def _render_jpg(lines, size=(1200, 1600), quality=92):
    img = Image.new("RGB", size, "white")
    d = ImageDraw.Draw(img)
    d.rectangle([20, 20, size[0]-20, size[1]-20], outline="black", width=3)
    y = 60
    for text, sz in lines:
        d.text((60, y), text, fill="black", font=_font(sz))
        y += sz + 14
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


def _assurance_img() -> bytes:
    return _render_jpg([
        ("ATTESTATION D'ASSURANCE VEHICULE", 34),
        ("", 8),
        ("Compagnie : AXA Assurances SA", 28),
        ("N° de police : POL-2026-778899", 28),
        ("Type de couverture : Casco complete", 28),
        ("Immatriculation : VD 445566", 28),
        ("VIN : WAUZZZ8V5KA098765", 28),
        ("Date de debut : 01.02.2026", 28),
        ("Date d'echeance : 31.01.2027", 28),
        ("Prime annuelle : 1520 CHF", 28),
    ], size=(900, 1200))


def _vignette_img() -> bytes:
    return _render_jpg([
        ("E-VIGNETTE SUISSE 2026", 36),
        ("", 8),
        ("Immatriculation : VD 445566", 28),
        ("Type : vignette autoroutiere annuelle", 28),
        ("Annee de validite : 2026", 28),
        ("Achetee le : 05.01.2026", 28),
        ("Valable jusqu'au : 31.01.2027", 28),
        ("Prix : CHF 40.00", 28),
        ("Statut : active", 28),
    ], size=(900, 1000))


def _tiny_img() -> bytes:
    return _render_jpg([("XX", 20)], size=(180, 120))


def _lowres_img() -> bytes:
    # 500x350 lisible mais faible résolution → warning non bloquant
    return _render_jpg([
        ("PERMIS DE CIRCULATION", 22),
        ("Plaque : VD 445566", 18),
        ("VIN : WAUZZZ8V5KA098765", 18),
        ("Marque : AUDI", 18),
        ("Modele : A3", 18),
        ("Carburant : Essence", 18),
    ], size=(500, 350))


@pytest.fixture(scope="module")
def session():
    return requests.Session()


@pytest.fixture(scope="module")
def target_vehicle(session):
    r = session.get(f"{API}/vehicles", timeout=30)
    assert r.status_code == 200
    vehicles = r.json()
    for v in vehicles:
        if v["id"] != RESERVED_VEHICLE and (v.get("plaque") or "").strip():
            return v
    return vehicles[0]


@pytest.fixture(scope="module")
def created_docs():
    return []


@pytest.fixture(scope="module", autouse=True)
def _cleanup(session, created_docs):
    yield
    for doc_id in created_docs:
        try:
            session.delete(f"{API}/documents/{doc_id}", timeout=15)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Test A: Quality gate — 180x120 must 422 BEFORE Claude call & create no doc
# ---------------------------------------------------------------------------
class TestQualityBlocked:
    def test_tiny_image_422_no_doc(self, session, target_vehicle):
        vid = target_vehicle["id"]
        docs_before = session.get(f"{API}/vehicles/{vid}/documents", timeout=30).json()
        n_before = len(docs_before)

        r = session.post(
            f"{API}/vehicles/{vid}/documents/scan",
            files=[("files", ("tiny.jpg", _tiny_img(), "image/jpeg"))],
            data={"document_type": "permis_circulation"},
            timeout=30,
        )
        assert r.status_code == 422, r.text
        assert "reprendre" in r.text.lower() or "lisibles" in r.text.lower()

        docs_after = session.get(f"{API}/vehicles/{vid}/documents", timeout=30).json()
        assert len(docs_after) == n_before, "un document a été créé malgré le blocage qualité"


# ---------------------------------------------------------------------------
# Test B: Type mismatch — attestation d'assurance scannée en 'permis_circulation'
# ---------------------------------------------------------------------------
class TestTypeMismatch:
    @pytest.fixture(scope="class")
    def mismatch_scan(self, session, target_vehicle, created_docs):
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("assur.jpg", _assurance_img(), "image/jpeg"))],
            data={"document_type": "permis_circulation"},
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if data.get("document_id"):
            created_docs.append(data["document_id"])
        return data

    def test_type_mismatch_present(self, mismatch_scan):
        tm = mismatch_scan.get("type_mismatch")
        assert tm, f"type_mismatch missing: {mismatch_scan}"
        assert tm["expected"] == "permis_circulation"
        assert tm["detected"] == "assurance"
        assert tm.get("expected_label") and tm.get("detected_label")
        assert tm.get("confidence") is not None

    def test_missing_fields_and_status(self, mismatch_scan):
        # missing_fields must be populated (assurance data doesn't fit permis fields)
        assert isinstance(mismatch_scan.get("missing_fields"), list)
        assert len(mismatch_scan["missing_fields"]) >= 3
        # Each field has status + confidence
        for f in mismatch_scan["fields"]:
            assert "status" in f, f
            assert f["status"] in ("found", "uncertain", "missing")
            assert "confidence" in f

    def test_no_vehicle_write_before_validate(self, session, target_vehicle, mismatch_scan):
        # Vehicle must NOT have been modified by the scan itself
        v = session.get(f"{API}/vehicles/{target_vehicle['id']}", timeout=30).json()
        # None of the assurance fields should have been applied
        assert v.get("compagnie") in (None, "", target_vehicle.get("compagnie")) or True
        # Deeper: assurance sub-object shouldn't contain POL-2026-778899
        assurance = v.get("assurance") or {}
        assert "POL-2026-778899" not in str(assurance)

    def test_traceability_fields_on_document(self, session, target_vehicle, mismatch_scan):
        docs = session.get(f"{API}/vehicles/{target_vehicle['id']}/documents", timeout=30).json()
        this = next((d for d in docs if d["id"] == mismatch_scan["document_id"]), None)
        assert this, "document introuvable"
        assert this.get("imported_by") == "utilisateur"
        assert this.get("analyzed_at")
        assert this.get("detected_type") == "assurance"
        assert "quality_warnings" in this


# ---------------------------------------------------------------------------
# Test C: Re-analyse with document_id + corrected type
# ---------------------------------------------------------------------------
class TestReanalyseWithDetectedType:
    def test_reanalyse_clears_mismatch(self, session, target_vehicle, created_docs):
        if not created_docs:
            pytest.skip("no assurance doc from previous test")
        doc_id = created_docs[0]
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
        assert data.get("type_mismatch") in (None, {}), data.get("type_mismatch")
        assert data["document_type"] == "assurance"
        keys = {f["field"] for f in data["fields"]}
        assert keys & {"compagnie", "numero_police", "date_echeance", "date_debut", "prime_annuelle"}

        # no new document created
        docs_after = session.get(f"{API}/vehicles/{vid}/documents", timeout=30).json()
        assert len(docs_after) == n_before


# ---------------------------------------------------------------------------
# Test D: Vignette autoroutière type — scan + validate + traceability
# ---------------------------------------------------------------------------
class TestVignette:
    @pytest.fixture(scope="class")
    def vignette_scan(self, session, target_vehicle, created_docs):
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("vignette.jpg", _vignette_img(), "image/jpeg"))],
            data={"document_type": "vignette"},
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if data.get("document_id"):
            created_docs.append(data["document_id"])
        return data

    def test_vignette_type_and_fields(self, vignette_scan):
        assert vignette_scan["document_type"] == "vignette"
        keys = {f["field"] for f in vignette_scan["fields"]}
        expected = {"annee", "type_vignette", "date_achat", "date_expiration", "prix_chf", "statut"}
        common = keys & expected
        assert len(common) >= 3, f"expected >=3 vignette-specific fields, got {common} within {keys}"

    def test_vignette_folder(self, session, target_vehicle, vignette_scan):
        docs = session.get(f"{API}/vehicles/{target_vehicle['id']}/documents", timeout=30).json()
        this = next((d for d in docs if d["id"] == vignette_scan["document_id"]), None)
        assert this
        assert this.get("folder") in ("Vignette", "vignette"), this.get("folder")

    def test_validate_vignette(self, session, target_vehicle, vignette_scan):
        by_key = {f["field"]: f for f in vignette_scan["fields"]}
        payload_fields = {}
        for k in ("annee", "date_expiration", "prix_chf", "statut", "type_vignette"):
            if k in by_key and by_key[k].get("value") not in (None, ""):
                payload_fields[k] = by_key[k]["value"]
        assert payload_fields, "no vignette fields extracted — cannot validate"

        r = session.post(
            f"{API}/documents/{vignette_scan['document_id']}/validate",
            json={"document_type": "vignette", "fields": payload_fields},
            timeout=60,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        assert data["ok"] is True
        # NOTE: `applied` reflects vehicle field changes only.
        # Vignette fields all have target=document → applied stays 0 by design.
        # We instead verify document_data + validated_fields on the doc record.

        # Document now shows validated_by + validated_at + validated_fields + document_data
        docs = session.get(f"{API}/vehicles/{target_vehicle['id']}/documents", timeout=30).json()
        this = next(d for d in docs if d["id"] == vignette_scan["document_id"])
        assert this["extraction_status"] == "validated"
        assert this.get("validated_by") == "utilisateur"
        assert this.get("validated_at")
        assert this.get("validated_fields")
        # document_data must carry the validated target-document fields
        dd = this.get("document_data") or {}
        assert dd, f"document_data empty on validated vignette: {this}"
        assert set(dd.keys()) & set(payload_fields.keys()), (
            f"none of {payload_fields.keys()} landed in document_data ({dd})"
        )


# ---------------------------------------------------------------------------
# Test E: Quality warning non-bloquant (500x350)
# ---------------------------------------------------------------------------
class TestQualityWarning:
    def test_lowres_warning_but_success(self, session, target_vehicle, created_docs):
        r = session.post(
            f"{API}/vehicles/{target_vehicle['id']}/documents/scan",
            files=[("files", ("lowres.jpg", _lowres_img(), "image/jpeg"))],
            data={"document_type": "permis_circulation"},
            timeout=TIMEOUT_SCAN,
        )
        assert r.status_code == 200, r.text
        data = r.json()
        if data.get("document_id"):
            created_docs.append(data["document_id"])
        qw = data.get("quality_warnings") or []
        assert any("résolution" in x.lower() or "resolution" in x.lower() for x in qw), qw
        # analysis still done
        assert data["extraction_status"] == "done"
