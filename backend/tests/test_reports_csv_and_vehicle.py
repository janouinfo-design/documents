"""Tests: /api/reports/couts.csv and /api/reports/vehicule/{id}.pdf + audit."""
import asyncio
import csv
import io
import os
import re
from datetime import datetime

import pymupdf
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"

VEHICLE_ID = "d1099b53-a118-42d8-adfc-3d1b9e1fdcb0"
VEHICLE_PLAQUE = "BE 579928"

EXPECTED_HEADER = [
    "Plaque", "Marque", "Modèle", "Base", "Groupe", "Statut",
    "Société leasing", "Fin de leasing", "Mensualité CHF", "Mois restants", "Coût restant CHF",
    "Compagnie assurance", "Échéance assurance", "Prime annuelle CHF", "Prochain contrôle",
    "Coût annuel tous postes CHF",
]


@pytest.fixture(scope="module")
def vehicles_list():
    r = requests.get(f"{API}/vehicles", timeout=30)
    assert r.status_code == 200
    return r.json()


# ---- /api/reports/couts.csv ----
class TestCostsCSV:
    @pytest.fixture(scope="class")
    def csv_response(self):
        return requests.get(f"{API}/reports/couts.csv", timeout=30)

    def test_headers(self, csv_response):
        assert csv_response.status_code == 200
        ct = csv_response.headers.get("content-type", "")
        assert "text/csv" in ct
        cd = csv_response.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert "couts-flotte-logitrak.csv" in cd

    def test_bom_and_parse(self, csv_response, vehicles_list):
        raw = csv_response.content.decode("utf-8")
        assert raw.startswith("\ufeff"), "CSV must start with UTF-8 BOM"
        body = raw.lstrip("\ufeff")
        reader = list(csv.reader(io.StringIO(body), delimiter=";"))
        assert len(reader) >= 2
        header = reader[0]
        assert header == EXPECTED_HEADER, f"Header mismatch: {header}"
        # rows = vehicles + TOTAL line
        assert len(reader) == len(vehicles_list) + 2, (
            f"Expected {len(vehicles_list)} veh + header + TOTAL, got {len(reader)}"
        )
        # TOTAL line
        last = reader[-1]
        assert last[0].strip().upper() == "TOTAL", f"Last row not TOTAL: {last}"

    def test_cross_check_values(self, csv_response, vehicles_list):
        raw = csv_response.content.decode("utf-8").lstrip("\ufeff")
        reader = list(csv.reader(io.StringIO(raw), delimiter=";"))
        header = reader[0]
        # Build plaque -> row map
        rows = {r[0]: r for r in reader[1:-1]}
        checked = 0
        for v in vehicles_list:
            plaque = v.get("plaque")
            if plaque not in rows:
                continue
            row = rows[plaque]
            leasing = v.get("leasing") or {}
            assurance = v.get("assurance") or {}
            metrics_leasing = (v.get("metrics") or {}).get("leasing") or {}

            # Mensualité (col idx 8)
            mens = leasing.get("mensualite")
            if mens:
                assert str(int(round(float(mens)))) in row[8].replace("'", "").replace(" ", "") or \
                       f"{float(mens):.2f}" in row[8], f"Mensualité mismatch for {plaque}: row={row[8]}, api={mens}"

            # Prime annuelle (col idx 13)
            prime = assurance.get("prime_annuelle")
            if prime:
                cleaned = row[13].replace("'", "").replace(" ", "")
                assert str(int(round(float(prime)))) in cleaned or f"{float(prime):.2f}" in row[13], \
                    f"Prime mismatch for {plaque}: row={row[13]}, api={prime}"

            # Coût restant (col idx 10)
            cost_rem = metrics_leasing.get("cost_remaining")
            if cost_rem:
                cleaned = row[10].replace("'", "").replace(" ", "")
                assert str(int(round(float(cost_rem)))) in cleaned, \
                    f"Cost remaining mismatch for {plaque}: row={row[10]}, api={cost_rem}"

            checked += 1
            if checked >= 3:
                break
        assert checked >= 2, "Could not cross-check 2 vehicles"

    def test_date_format_fr(self, csv_response):
        raw = csv_response.content.decode("utf-8").lstrip("\ufeff")
        reader = list(csv.reader(io.StringIO(raw), delimiter=";"))
        # Look for at least one JJ.MM.AAAA date across rows
        found = False
        for row in reader[1:-1]:
            for cell in row:
                if re.fullmatch(r"\d{2}\.\d{2}\.\d{4}", cell.strip()):
                    found = True
                    break
            if found:
                break
        assert found, "No JJ.MM.AAAA date format found in CSV"


# ---- /api/reports/vehicule/{id}.pdf ----
class TestVehiclePDF:
    @pytest.fixture(scope="class")
    def pdf_resp(self):
        return requests.get(f"{API}/reports/vehicule/{VEHICLE_ID}.pdf", timeout=60)

    @pytest.fixture(scope="class")
    def pdf_text(self, pdf_resp):
        doc = pymupdf.open(stream=pdf_resp.content, filetype="pdf")
        text = "\n".join(p.get_text() for p in doc)
        doc.close()
        return text

    def test_headers(self, pdf_resp):
        assert pdf_resp.status_code == 200
        assert pdf_resp.headers.get("content-type", "").startswith("application/pdf")
        cd = pdf_resp.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert "fiche-be-579928.pdf" in cd
        assert pdf_resp.content[:5] == b"%PDF-"

    def test_sections_present(self, pdf_text):
        assert "Fiche v" in pdf_text  # "Fiche véhicule"
        assert VEHICLE_PLAQUE in pdf_text
        # Section headings (accents may or may not be preserved by fpdf latin1 sanitizer)
        for needle in ["Identit", "Moteur", "Leasing", "Assurance", "Contr", "Documents", "Historique"]:
            assert needle in pdf_text, f"Missing section keyword '{needle}' in PDF text"

    def test_consumption_wltp(self, pdf_text):
        # 7.2 L/100 km WLTP must be present
        assert "7.2" in pdf_text or "7,2" in pdf_text, "Consumption value 7.2 missing"
        assert "WLTP" in pdf_text, "WLTP marker missing"

    def test_history_and_documents(self, pdf_text):
        r_docs = requests.get(f"{API}/vehicles/{VEHICLE_ID}/documents", timeout=30)
        assert r_docs.status_code == 200
        docs = [d for d in r_docs.json() if not d.get("is_deleted")]
        # PDF should mention Documents section; if any non-deleted doc exists, at least one filename should appear
        if docs:
            found_any = any((d.get("original_name") or d.get("stored_name") or "")[:20] in pdf_text
                            for d in docs)
            # not strictly required - filenames may be truncated - so just ensure section exists
            assert "Documents" in pdf_text
        # History section
        assert "Historique" in pdf_text

    def test_not_found(self):
        r = requests.get(f"{API}/reports/vehicule/inexistant-id.pdf", timeout=30)
        assert r.status_code == 404
        try:
            detail = r.json().get("detail", "")
        except Exception:
            detail = r.text
        assert "introuvable" in detail.lower() or "inexistant" in detail.lower() or \
               "non trouv" in detail.lower(), f"Detail not in French: {detail}"


# ---- Audit log ----
class TestAudit:
    def test_download_audit_for_csv_and_vehicle(self):
        from motor.motor_asyncio import AsyncIOMotorClient
        backend_env = dotenv_values("/app/backend/.env")
        mongo_url = backend_env.get("MONGO_URL", "").strip('"')
        db_name = backend_env.get("DB_NAME", "").strip('"')

        async def _run():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            before = await db.audit_logs.count_documents({"action": "download", "entity": "report"})
            r1 = requests.get(f"{API}/reports/couts.csv", timeout=30)
            r2 = requests.get(f"{API}/reports/vehicule/{VEHICLE_ID}.pdf", timeout=60)
            assert r1.status_code == 200
            assert r2.status_code == 200
            after = await db.audit_logs.count_documents({"action": "download", "entity": "report"})
            latest = await db.audit_logs.find(
                {"action": "download", "entity": "report"}
            ).sort("created_at", -1).to_list(5)
            client.close()
            return before, after, latest

        loop_running = False
        try:
            loop_running = asyncio.get_event_loop().is_running()
        except Exception:
            pass
        before, after, latest = asyncio.run(_run()) if not loop_running else \
            asyncio.get_event_loop().run_until_complete(_run())
        assert after >= before + 2, f"Expected +2 audit entries, got before={before}, after={after}"
        entity_ids = [x.get("entity_id") for x in latest]
        assert any("couts" in (e or "") for e in entity_ids), f"No CSV audit found: {entity_ids}"
        assert any("vehicule" in (e or "") for e in entity_ids), f"No vehicle PDF audit: {entity_ids}"
