"""Iteration 8 — Verify fail-fast 503 when EMERGENT_LLM_KEY is empty.

Uses httpx ASGITransport in a pytest-asyncio session to drive the FastAPI app
in the same event loop as Motor. `server.EMERGENT_KEY` is monkeypatched at
runtime (backend/.env is never touched)."""
import io
import sys
from pathlib import Path

import pytest
import pytest_asyncio
from PIL import Image, ImageDraw
import httpx
from httpx import ASGITransport

BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import server as server_mod  # noqa: E402


def _small_jpg() -> bytes:
    img = Image.new("RGB", (400, 300), "white")
    ImageDraw.Draw(img).text((20, 20), "TEST", fill="black")
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return buf.getvalue()


@pytest_asyncio.fixture
async def aclient():
    # Rebind motor client to the current running loop
    from motor.motor_asyncio import AsyncIOMotorClient
    import os
    server_mod.client = AsyncIOMotorClient(os.environ["MONGO_URL"])
    server_mod.db = server_mod.client[os.environ["DB_NAME"]]
    transport = ASGITransport(app=server_mod.app)
    async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as ac:
        r = await ac.post("/api/auth/login", json={
            "email": os.environ["ADMIN_EMAIL"], "password": os.environ["ADMIN_PASSWORD"]})
        ac.headers["Authorization"] = f"Bearer {r.json()['token']}"
        yield ac


@pytest_asyncio.fixture
async def vehicle_id(aclient):
    r = await aclient.get("/api/vehicles")
    assert r.status_code == 200, r.text
    vehicles = r.json()
    assert vehicles, "no vehicle in DB"
    for v in vehicles:
        if v.get("plaque"):
            return v["id"]
    return vehicles[0]["id"]


class TestScanFailFastNoKey:
    """When EMERGENT_LLM_KEY is empty, scan must 503 and NOT create any doc."""

    @pytest.mark.asyncio
    async def test_fail_fast_503_message(self, aclient, vehicle_id, monkeypatch):
        monkeypatch.setattr(server_mod, "EMERGENT_KEY", "", raising=False)
        monkeypatch.setattr(server_mod, "ANTHROPIC_KEY", "", raising=False)

        r_before = await aclient.get(f"/api/vehicles/{vehicle_id}/documents")
        assert r_before.status_code == 200
        n_before = len(r_before.json())

        img = _small_jpg()
        r = await aclient.post(
            f"/api/vehicles/{vehicle_id}/documents/scan",
            files={"files": ("permis.jpg", img, "image/jpeg")},
        )
        assert r.status_code == 503, r.text
        detail = r.json().get("detail", "")
        assert "EMERGENT_LLM_KEY" in detail, f"missing key hint in: {detail}"
        assert "deploy/.env" in detail, f"missing deploy hint in: {detail}"

        r_after = await aclient.get(f"/api/vehicles/{vehicle_id}/documents")
        assert r_after.status_code == 200
        n_after = len(r_after.json())
        assert n_after == n_before, f"fail-fast leaked a doc: {n_before} -> {n_after}"

    @pytest.mark.asyncio
    async def test_fail_fast_before_type_validation(self, aclient, vehicle_id, monkeypatch):
        monkeypatch.setattr(server_mod, "EMERGENT_KEY", "", raising=False)
        monkeypatch.setattr(server_mod, "ANTHROPIC_KEY", "", raising=False)
        img = _small_jpg()
        r = await aclient.post(
            f"/api/vehicles/{vehicle_id}/documents/scan",
            files={"files": ("x.jpg", img, "image/jpeg")},
            data={"document_type": "not_a_real_type"},
        )
        assert r.status_code == 503, r.text

    @pytest.mark.asyncio
    async def test_unknown_vehicle_still_404(self, aclient, monkeypatch):
        monkeypatch.setattr(server_mod, "EMERGENT_KEY", "", raising=False)
        monkeypatch.setattr(server_mod, "ANTHROPIC_KEY", "", raising=False)
        img = _small_jpg()
        r = await aclient.post(
            "/api/vehicles/DOES-NOT-EXIST/documents/scan",
            files={"files": ("x.jpg", img, "image/jpeg")},
        )
        assert r.status_code == 404, r.text


class TestKeyPresent:
    """Regression: with the real key loaded, endpoint does NOT return the fail-fast 503."""

    @pytest.mark.asyncio
    async def test_scan_does_not_fail_fast(self, aclient, vehicle_id):
        assert server_mod.EMERGENT_KEY, "EMERGENT_LLM_KEY is empty in the running process"
        img = _small_jpg()
        r = await aclient.post(
            f"/api/vehicles/{vehicle_id}/documents/scan",
            files={"files": ("tiny.jpg", img, "image/jpeg")},
        )
        # The tiny synthetic image may still return 200 (extraction_status=failed
        # after LLM), 422 (image illisible), or 502 (storage). Never the fail-fast 503.
        if r.status_code == 503:
            assert "EMERGENT_LLM_KEY" not in r.json().get("detail", ""), r.text

        if r.status_code == 200:
            doc_id = r.json().get("document_id")
            if doc_id:
                await aclient.delete(f"/api/documents/{doc_id}")
