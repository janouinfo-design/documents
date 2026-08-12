"""Tests: /api/config/status and /api/reports/conformite.pdf + audit log."""
import io
import os
import re
from datetime import datetime, timezone

import pymupdf
import pytest
import requests
from dotenv import dotenv_values

frontend_env = dotenv_values("/app/frontend/.env")
BASE_URL = (os.environ.get("REACT_APP_BACKEND_URL") or frontend_env.get("REACT_APP_BACKEND_URL")).rstrip("/")
API = f"{BASE_URL}/api"


# ---- /api/config/status ----
class TestConfigStatus:
    def test_config_status_shape(self):
        r = requests.get(f"{API}/config/status", timeout=15)
        assert r.status_code == 200
        data = r.json()
        assert set(data.keys()) >= {"scan_configured", "technical_data_configured"}
        assert isinstance(data["scan_configured"], bool)
        assert isinstance(data["technical_data_configured"], bool)

    def test_config_status_preview_values(self):
        # Preview: scan configuré (Claude) ; base technique = données ASTRA importées
        r = requests.get(f"{API}/config/status", timeout=15)
        data = r.json()
        assert data["scan_configured"] is True, data
        assert data["technical_data_configured"] is True, data


# ---- /api/reports/conformite.pdf ----
@pytest.fixture(scope="module")
def pdf_response():
    r = requests.get(f"{API}/reports/conformite.pdf", timeout=60)
    return r


@pytest.fixture(scope="module")
def vehicles_list():
    r = requests.get(f"{API}/vehicles", timeout=30)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope="module")
def pdf_text(pdf_response):
    doc = pymupdf.open(stream=pdf_response.content, filetype="pdf")
    text = "\n".join(page.get_text() for page in doc)
    doc.close()
    return text


class TestConformityReport:
    def test_headers_and_body(self, pdf_response):
        assert pdf_response.status_code == 200
        assert pdf_response.headers.get("content-type", "").startswith("application/pdf")
        cd = pdf_response.headers.get("content-disposition", "")
        assert "attachment" in cd.lower()
        assert "rapport-conformite-logitrak.pdf" in cd
        assert pdf_response.content[:5] == b"%PDF-"

    def test_sections_present(self, pdf_text):
        # Latin-1 sanitization keeps accents; check core headings
        assert "Rapport de conformit" in pdf_text
        assert "Synth" in pdf_text  # "Synthèse"
        assert "ch" in pdf_text.lower()  # "Échéances"
        assert "ances & conformit" in pdf_text or "conformit" in pdf_text
        assert "ts leasing" in pdf_text or "Co" in pdf_text  # "Coûts leasing & assurance"
        assert "TOTAL" in pdf_text

    def test_all_vehicles_listed(self, pdf_text, vehicles_list):
        assert len(vehicles_list) > 0
        missing = [v.get("plaque") for v in vehicles_list if v.get("plaque") and v["plaque"] not in pdf_text]
        assert not missing, f"Plaques missing from PDF: {missing}"

    def test_chf_swiss_formatting(self, pdf_text):
        # Look for CHF amounts with apostrophe thousands separators, e.g. 82'290 CHF
        m = re.findall(r"\d{1,3}(?:'\d{3})+\s*CHF", pdf_text)
        assert m, f"No Swiss-formatted CHF amounts found. Sample text: {pdf_text[:400]}"

    def test_cost_remaining_matches_api(self, pdf_text, vehicles_list):
        """Cross-check cost_remaining for up to 3 vehicles with a non-zero value."""
        checked = 0
        for v in vehicles_list:
            m = ((v.get("metrics") or {}).get("leasing") or {}).get("cost_remaining")
            if not m:
                continue
            expected = f"{float(m):,.0f}".replace(",", "'") + " CHF"
            plaque = v.get("plaque")
            assert expected in pdf_text, f"Vehicle {plaque}: expected '{expected}' in PDF"
            checked += 1
            if checked >= 3:
                break
        assert checked >= 1, "No vehicle with leasing.cost_remaining to cross-check"

    def test_dates_match_api(self, pdf_text, vehicles_list):
        """Cross-check leasing/assurance/controle dates for 2-3 vehicles."""
        checked = 0
        for v in vehicles_list:
            leasing = (v.get("leasing") or {}).get("date_fin")
            assurance = (v.get("assurance") or {}).get("date_echeance")
            controle = (v.get("controle_technique") or {}).get("date_prochain")
            for iso in (leasing, assurance, controle):
                if not iso:
                    continue
                try:
                    fr = datetime.fromisoformat(str(iso)[:10]).strftime("%d.%m.%Y")
                except ValueError:
                    continue
                assert fr in pdf_text, f"Date {fr} (from {iso}) not in PDF for {v.get('plaque')}"
            if leasing or assurance or controle:
                checked += 1
            if checked >= 3:
                break
        assert checked >= 2, "Could not cross-check dates for at least 2 vehicles"


# ---- Audit log ----
class TestAuditLog:
    def test_download_audit_created(self):
        import asyncio
        from motor.motor_asyncio import AsyncIOMotorClient

        backend_env = dotenv_values("/app/backend/.env")
        mongo_url = backend_env.get("MONGO_URL", "").strip('"')
        db_name = backend_env.get("DB_NAME", "").strip('"')

        async def _run():
            client = AsyncIOMotorClient(mongo_url)
            db = client[db_name]
            before = await db.audit_logs.count_documents({"action": "download", "entity": "report"})
            # Trigger a new download
            r = requests.get(f"{API}/reports/conformite.pdf", timeout=60)
            assert r.status_code == 200
            after = await db.audit_logs.count_documents({"action": "download", "entity": "report"})
            latest = await db.audit_logs.find_one(
                {"action": "download", "entity": "report"}, sort=[("created_at", -1)]
            )
            client.close()
            return before, after, latest

        before, after, latest = asyncio.get_event_loop().run_until_complete(_run()) \
            if not asyncio.get_event_loop().is_running() else asyncio.run(_run())
        assert after == before + 1, f"Audit count did not increase (before={before}, after={after})"
        assert latest is not None
        assert latest.get("entity_id") == "conformite"
