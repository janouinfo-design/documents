"""Photo principale du véhicule — source canonique, sécurité, RBAC, et sync avatar Navixy
(capacité vérifiée : POST /vehicle/avatar/upload multipart). Mock Navixy local — zéro écriture réelle."""
import io
import json
import threading
import uuid
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest
import requests
from dotenv import dotenv_values
from PIL import Image
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT = f"pytest-photo-{_RUN}"
ADMIN = (f"photo-adm-{_RUN}@pytest.ch", f"Adm-{_RUN}-1")
_S = {}
_cache = {}

MOCK = {"avatar_uploads": [], "fail_avatar": False, "remote_avatar": "remoteavatar.png"}


def _png_bytes(size=(60, 40), color=(30, 60, 120)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, "PNG")
    return buf.getvalue()


class _Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _json(self, out, code=200):
        payload = json.dumps(out).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self):
        if self.path.startswith("/static/vehicle/avatars/"):
            data = _png_bytes((80, 50), (90, 20, 20))
            self.send_response(200)
            self.send_header("Content-Type", "image/png")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self._json({"success": True})

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0) or 0)
        raw = self.rfile.read(length) if length else b""
        path = self.path.split("?")[0]
        ctype = self.headers.get("Content-Type", "")
        if path == "/vehicle/avatar/upload":
            if MOCK["fail_avatar"]:
                self._json({"success": False, "status": {"code": 234}})
                return
            MOCK["avatar_uploads"].append({"content_type": ctype, "size": len(raw)})
            self._json({"success": True, "value": f"mockavatar-{len(MOCK['avatar_uploads'])}.png"})
            return
        body = json.loads(raw or b"{}") if "json" in ctype else {}
        if path == "/vehicle/read":
            self._json({"success": True, "value": {"id": body.get("vehicle_id"), "label": "Mock",
                                                   "avatar_file_name": MOCK["remote_avatar"]}})
        elif path == "/vehicle/list":
            self._json({"success": True, "list": []})
        else:
            self._json({"success": True, "list": []})


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(email, password):
    key = (email, password)
    if key not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": email, "password": password}, timeout=30)
        assert r.status_code == 200, f"login {email} -> {r.status_code}"
        _cache[key] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[key]


def sa():
    return _h(_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"])


def ro():
    return _h("ro-e2e@client-test.ch", "RoTest-2026y")


def _upload_photo(vid, data=None, filename="photo.png", replace=False, headers=None):
    return requests.post(f"{_BASE}/api/vehicles/{vid}/photo",
                         files={"file": (filename, data or _png_bytes(), "image/png")},
                         data={"replace": "true" if replace else "false"},
                         headers=headers or _h(*ADMIN), timeout=60)


def setup_module():
    srv = HTTPServer(("127.0.0.1", 0), _Handler)
    _S["server"] = srv
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base_url = f"http://127.0.0.1:{srv.server_address[1]}"
    r = requests.post(f"{_BASE}/api/admin/tenants", json={"name": f"Photo {_RUN}", "id": TENANT},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    r = requests.post(f"{_BASE}/api/admin/tenants/{TENANT}/users",
                      json={"email": ADMIN[0], "password": ADMIN[1], "role": "admin"},
                      headers=sa(), timeout=30)
    assert r.status_code == 200, r.text
    _mongo().tenant_integrations.insert_one({
        "tenant_id": TENANT, "provider": "navixy", "enabled": True,
        "api_hash": f"mock-{_RUN}", "base_url": base_url, "write_enabled": True})
    # Véhicule lié (id canonique + navixy_vehicle_id) et véhicule non lié
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"PH {_RUN[:6].upper()}", "marque": "VW", "modele": "Caddy"})
    _S["veh"] = r.json()["id"]
    _mongo().vehicles.update_one({"id": _S["veh"]}, {"$set": {"navixy_vehicle_id": 901}})
    r = requests.post(f"{_BASE}/api/vehicles", headers=_h(*ADMIN), timeout=30,
                      json={"plaque": f"PU {_RUN[:6].upper()}", "marque": "Ford", "modele": "Transit"})
    _S["veh_unlinked"] = r.json()["id"]
    vb = _mongo().vehicles.find_one({"tenant_id": "client-test-e2e"}, {"_id": 0, "id": 1})
    _S["veh_ro"] = vb["id"] if vb else None


def teardown_module():
    _S["server"].shutdown()
    db = _mongo()
    for coll in ("vehicles", "documents", "files", "audit_logs", "vehicle_field_meta",
                 "tenant_integrations", "users"):
        db[coll].delete_many({"tenant_id": TENANT})
    db.tenants.delete_many({"id": TENANT})


class TestSecuriteUpload:
    def test_fichier_invalide_422(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/photo",
                          files={"file": ("notes.txt", b"pas une image", "text/plain")},
                          data={"replace": "false"}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 422

    def test_extension_image_mais_contenu_invalide_422(self):
        r = _upload_photo(_S["veh"], data=b"faux contenu png")
        assert r.status_code == 422  # contenu réel vérifié, pas seulement l'extension

    def test_taille_excessive_413(self):
        big = _png_bytes() + b"\x00" * (10 * 1024 * 1024 + 1)
        r = _upload_photo(_S["veh"], data=big)
        assert r.status_code == 413

    def test_vehicule_inexistant_404(self):
        r = _upload_photo("n-existe-pas")
        assert r.status_code == 404

    def test_read_only_403(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        r = _upload_photo(_S["veh_ro"], headers=ro())
        assert r.status_code == 403
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_ro']}/photo", headers=ro(), timeout=30)
        assert r.status_code == 403

    def test_cross_tenant_404(self):
        if not _S["veh_ro"]:
            pytest.skip("pas de véhicule read_only tenant")
        r = _upload_photo(_S["veh_ro"])  # admin d'un autre tenant
        assert r.status_code == 404


class TestPhotoCanonique:
    def test_upload_valide_photo_thumb_et_sync(self):
        r = _upload_photo(_S["veh"])
        assert r.status_code == 200, r.text
        res = r.json()
        assert res["photo"]["origin"] == "upload"
        assert res["photo"]["thumb_path"]  # miniature générée pour la liste
        assert res["navixy_photo"]["status"] == "synced"
        assert res["navixy_photo"]["avatar_file_name"].startswith("mockavatar")
        assert len(MOCK["avatar_uploads"]) == 1
        assert "multipart/form-data" in MOCK["avatar_uploads"][0]["content_type"]
        v = _mongo().vehicles.find_one({"id": _S["veh"]}, {"_id": 0})
        assert v["photo_url"] == f"/api/files/{v['photo']['storage_path']}"  # source canonique unique
        assert v["tenant_id"] == TENANT
        assert v["integrations"]["navixy"]["photo_sync"]["status"] == "synced"

    def test_fichier_et_thumb_servis_tenant_scope(self):
        v = _mongo().vehicles.find_one({"id": _S["veh"]}, {"_id": 0, "photo": 1})
        for p in (v["photo"]["storage_path"], v["photo"]["thumb_path"]):
            r = requests.get(f"{_BASE}/api/files/{p}", headers=_h(*ADMIN), timeout=30)
            assert r.status_code == 200 and r.headers["content-type"].startswith("image/")
            r = requests.get(f"{_BASE}/api/files/{p}", headers=ro(), timeout=30)
            assert r.status_code == 404  # tenant B ne voit jamais la photo du tenant A

    def test_remplacement_sans_confirmation_409(self):
        r = _upload_photo(_S["veh"])
        assert r.status_code == 409  # jamais de remplacement silencieux

    def test_remplacement_confirme_ok(self):
        r = _upload_photo(_S["veh"], replace=True)
        assert r.status_code == 200
        assert len(MOCK["avatar_uploads"]) == 2  # re-push après remplacement

    def test_echec_navixy_photo_locale_conservee(self):
        MOCK["fail_avatar"] = True
        try:
            r = _upload_photo(_S["veh"], replace=True)
            assert r.status_code == 200, r.text  # l'échec Navixy n'annule JAMAIS le local
            assert r.json()["navixy_photo"]["status"] == "failed"
            v = _mongo().vehicles.find_one({"id": _S["veh"]}, {"_id": 0})
            assert v["photo_url"]
            sync = v["integrations"]["navixy"]["photo_sync"]
            assert sync["status"] == "failed" and sync["attempts"] >= 1
        finally:
            MOCK["fail_avatar"] = False

    def test_retry_apres_echec(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/photo/navixy/push",
                          headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200
        assert r.json()["navixy_photo"]["status"] == "synced"

    def test_non_lie_statut_honnete(self):
        r = _upload_photo(_S["veh_unlinked"])
        assert r.status_code == 200
        assert r.json()["navixy_photo"]["status"] == "not_linked"  # aucun faux succès

    def test_suppression_locale_navixy_intact(self):
        n = len(MOCK["avatar_uploads"])
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo",
                            headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200 and r.json()["navixy"] == "unchanged"
        assert len(MOCK["avatar_uploads"]) == n  # aucun appel Navixy à la suppression
        v = _mongo().vehicles.find_one({"id": _S["veh_unlinked"]}, {"_id": 0})
        assert not v.get("photo_url") and not v.get("photo")
        r = requests.delete(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo",
                            headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 404


class TestDepuisDocument:
    def _add_doc(self, filename, content, mime, folder="Photos"):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/documents",
                          files={"file": (filename, content, mime)},
                          data={"folder": folder}, headers=_h(*ADMIN), timeout=60)
        assert r.status_code == 200, r.text
        return r.json()

    def test_document_image_devient_photo_sans_copie(self):
        doc = self._add_doc(f"vue-{_RUN}.png", _png_bytes((100, 70)), "image/png")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/from-document",
                          json={"document_id": doc["id"]}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
        v = _mongo().vehicles.find_one({"id": _S["veh_unlinked"]}, {"_id": 0, "photo": 1})
        assert v["photo"]["storage_path"] == doc["storage_path"]  # fichier réutilisé, pas de copie
        assert v["photo"]["origin"] == "document"
        assert v["photo"]["source_document_id"] == doc["id"]

    def test_document_non_image_422(self):
        doc = self._add_doc(f"facture-{_RUN}.pdf", b"%PDF-1.4 minimal", "application/pdf", "Factures")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/from-document",
                          json={"document_id": doc["id"]}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 422  # jamais automatique et jamais un PDF

    def test_document_autre_vehicule_404(self):
        doc = self._add_doc(f"autre-{_RUN}.png", _png_bytes(), "image/png")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh']}/photo/from-document",
                          json={"document_id": doc["id"]}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 404  # identité canonique stricte, pas d'association ambiguë

    def test_remplacement_document_sans_flag_409(self):
        doc = self._add_doc(f"vue2-{_RUN}.png", _png_bytes((90, 60)), "image/png")
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/from-document",
                          json={"document_id": doc["id"]}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 409
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/from-document",
                          json={"document_id": doc["id"], "replace": True}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200


class TestImportNavixy:
    def test_import_manuel_depuis_navixy(self):
        _mongo().vehicles.update_one({"id": _S["veh_unlinked"]}, {"$set": {"navixy_vehicle_id": 902}})
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/navixy/import",
                          json={"replace": True}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 200, r.text
        v = _mongo().vehicles.find_one({"id": _S["veh_unlinked"]}, {"_id": 0})
        assert v["photo"]["origin"] == "navixy_import"
        assert v["integrations"]["navixy"]["photo_sync"]["direction"] == "import"

    def test_import_sans_replace_409_si_photo(self):
        r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/navixy/import",
                          json={"replace": False}, headers=_h(*ADMIN), timeout=30)
        assert r.status_code == 409

    def test_import_sans_avatar_404(self):
        MOCK["remote_avatar"] = ""
        try:
            r = requests.post(f"{_BASE}/api/vehicles/{_S['veh_unlinked']}/photo/navixy/import",
                              json={"replace": True}, headers=_h(*ADMIN), timeout=30)
            assert r.status_code == 404
        finally:
            MOCK["remote_avatar"] = "remoteavatar.png"
