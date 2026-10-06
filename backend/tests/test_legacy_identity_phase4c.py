"""Phase 4C — Lot A : identité legacy / idempotence / correspondances (zéro migration).

Tenants de test créés/supprimés par la suite : pytest-legacy-a-<run>, pytest-legacy-b-<run>.
Aucune donnée legacy réelle n'est migrée ; seules des lignes de test sont écrites puis nettoyées.
"""
import asyncio
import sys
import uuid
from pathlib import Path

import pytest
import requests
from dotenv import dotenv_values
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError

BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
API = f"{BASE}/api"
BACKEND_DIR = str(Path(__file__).resolve().parents[1])
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)
_be = dotenv_values(Path(BACKEND_DIR, ".env"))
_db = MongoClient(_be["MONGO_URL"])[_be["DB_NAME"]]

RUN = uuid.uuid4().hex[:8]
TA, TB = f"pytest-legacy-a-{RUN}", f"pytest-legacy-b-{RUN}"
KEY_A = 990000 + int(RUN[:4], 16) % 9000
PWD = "LegacyTest-2026!"
LEGACY_VEHICLE = f"jrn-veh-{RUN}"
LEGACY_TENANT = f"jrn-tenant-{RUN}"


def _seed_user(tenant_id, role, tag):
    import auth as auth_mod
    email = f"legacy-{tag}-{RUN}@pytest.ch"
    _db.users.update_one({"email": email}, {"$set": {
        "id": str(uuid.uuid4()), "email": email, "name": tag, "role": role, "tenant_id": tenant_id,
        "password_hash": auth_mod.hash_password(PWD), "password_changed_in_app": False}}, upsert=True)
    return email


def _login(email, password=PWD):
    r = requests.post(f"{API}/auth/login", json={"email": email, "password": password}, timeout=20)
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


@pytest.fixture(scope="module")
def ctx():
    for t in (TA, TB):
        _db.tenants.insert_one({"id": t, "name": f"Legacy {t}", "disabled": False, "modules": {"documents": True}})
    _db.tenant_integrations.insert_one({"tenant_id": TA, "provider": "navixy", "master_user_id": KEY_A, "enabled": False})
    h = {"adm_a": _login(_seed_user(TA, "admin", "adm-a")),
         "ro_a": _login(_seed_user(TA, "read_only", "ro-a")),
         "adm_b": _login(_seed_user(TB, "admin", "adm-b")),
         "sa": _login(_be["SUPERADMIN_EMAIL"], _be["SUPERADMIN_PASSWORD"])}

    def mk(headers, payload):
        r = requests.post(f"{API}/vehicles", json=payload, headers=headers, timeout=20)
        assert r.status_code == 200, r.text
        return r.json()["id"]

    v = {"a_vin": mk(h["adm_a"], {"plaque": f"LA {RUN[:5]}", "vin": f"WVWZZZ1KZ{RUN[:8].upper()}", "marque": "A"}),
         "a_trk": mk(h["adm_a"], {"plaque": f"LB {RUN[:5]}", "marque": "A"}),
         "a_plate": mk(h["adm_a"], {"plaque": f"LC {RUN[:5]}", "marque": "A"}),
         "b_veh": mk(h["adm_b"], {"plaque": f"LD {RUN[:5]}", "marque": "B"})}
    _db.vehicles.update_one({"id": v["a_trk"]}, {"$set": {"navixy_tracker_id": 7000000 + KEY_A}})
    yield {"h": h, "v": v}
    _db.users.delete_many({"email": {"$regex": f"legacy-.*-{RUN}@pytest.ch$"}})
    for coll in ("vehicles", "documents", "fuel_transactions", "legacy_vehicle_map", "audit_logs",
                 "tenant_integrations", "tenant_settings", "alerts", "vehicle_field_meta"):
        _db[coll].delete_many({"tenant_id": {"$in": [TA, TB]}})
    _db.legacy_tenant_map.delete_many({"legacy_tenant_id": {"$regex": f"{RUN}$"}})
    _db.tenants.delete_many({"id": {"$in": [TA, TB]}})
    _db.login_attempts.delete_many({})


def _run(coro):
    from motor.motor_asyncio import AsyncIOMotorClient

    async def _wrap():
        db = AsyncIOMotorClient(_be["MONGO_URL"])[_be["DB_NAME"]]
        return await coro(db)
    return asyncio.run(_wrap())


class TestIdempotence:
    def test_1_replay_same_key_creates_single_record(self):
        import legacy_identity as li
        payload = {"vehicle_id": "x", "montant": 10.5, "devise": "CHF", "document_type": "ticket_carburant",
                   "is_deleted": False}
        key = dict(tenant_id=TA, legacy_source="journal", legacy_id=f"tx-{RUN}")
        r1 = _run(lambda db: li.upsert_legacy_record(db, "fuel_transactions", payload=payload, **key))
        r2 = _run(lambda db: li.upsert_legacy_record(db, "fuel_transactions", payload=payload, **key))
        r3 = _run(lambda db: li.upsert_legacy_record(db, "fuel_transactions", payload={**payload, "montant": 11}, **key))
        assert r1["created"] is True and r2["created"] is False and r3["created"] is False
        assert r1["id"] == r2["id"] == r3["id"]
        assert r2["changed"] is False and r3["changed"] is True
        assert _db.fuel_transactions.count_documents(key) == 1
        doc = _db.fuel_transactions.find_one(key)
        assert doc["migration_version"] == 1 and len(doc["legacy_payload_sha256"]) == 64 and doc["montant"] == 11

    def test_2_duplicate_legacy_id_same_tenant_refused_by_index(self):
        key = dict(tenant_id=TA, legacy_source="journal", legacy_id=f"dup-{RUN}")
        _db.documents.insert_one({**key, "id": str(uuid.uuid4()), "is_deleted": False})
        with pytest.raises(DuplicateKeyError):
            _db.documents.insert_one({**key, "id": str(uuid.uuid4()), "is_deleted": False})
        assert _db.documents.count_documents(key) == 1
        names = {i["name"] for i in _db.documents.list_indexes()} | {i["name"] for i in _db.fuel_transactions.list_indexes()}
        assert "uniq_legacy_key" in names

    def test_3_same_legacy_id_other_tenant_isolated(self):
        import legacy_identity as li
        lid = f"shared-{RUN}"
        ra = _run(lambda db: li.upsert_legacy_record(db, "documents", TA, "journal", lid, {"document_type": "amende"}))
        rb = _run(lambda db: li.upsert_legacy_record(db, "documents", TB, "journal", lid, {"document_type": "amende"}))
        assert ra["created"] and rb["created"] and ra["id"] != rb["id"]
        assert _db.documents.count_documents({"legacy_id": lid, "tenant_id": TA}) == 1
        assert _db.documents.count_documents({"legacy_id": lid, "tenant_id": TB}) == 1

    def test_payload_tenant_mismatch_refused(self):
        import legacy_identity as li
        with pytest.raises(ValueError):
            _run(lambda db: li.upsert_legacy_record(db, "documents", TA, "journal", "x", {"tenant_id": TB}))


class TestTenantMap:
    def test_4_unconfirmed_map_unusable_and_candidates_read_only(self, ctx):
        sa = ctx["h"]["sa"]
        before = _db.legacy_tenant_map.count_documents({})
        r = requests.post(f"{API}/admin/legacy/tenant-map/candidates", headers=sa, json={"tenants": [
            {"legacy_tenant_id": LEGACY_TENANT, "navixy_master_user_id": KEY_A, "name": "Nom Trompeur"},
            {"legacy_tenant_id": f"nokey-{RUN}", "name": "Legacy pytest-legacy-a"},
            {"legacy_tenant_id": f"unknown-{RUN}", "navixy_master_user_id": 1}]}, timeout=20)
        assert r.status_code == 200, r.text
        items = {i["legacy_tenant_id"]: i for i in r.json()["items"]}
        assert items[LEGACY_TENANT]["status"] == "found" and items[LEGACY_TENANT]["candidates"][0]["tenant_id"] == TA
        assert items[f"nokey-{RUN}"]["status"] == "no_technical_key" and items[f"nokey-{RUN}"]["candidates"] == []
        assert items[f"unknown-{RUN}"]["status"] == "not_found"
        assert r.json()["written"] == 0 and _db.legacy_tenant_map.count_documents({}) == before
        r = requests.get(f"{API}/admin/legacy/tenant-map/resolve", headers=sa,
                         params={"legacy_tenant_id": LEGACY_TENANT}, timeout=20)
        assert r.status_code == 404

    def test_5_mapping_by_name_forbidden(self, ctx):
        sa = ctx["h"]["sa"]
        r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=sa, json={
            "legacy_tenant_id": LEGACY_TENANT, "tenant_id": TB, "match_value": KEY_A}, timeout=20)
        assert r.status_code == 422 and "Clé technique" in r.json()["detail"]
        assert _db.legacy_tenant_map.count_documents({"legacy_tenant_id": LEGACY_TENANT}) == 0

    def test_6_default_fallback_forbidden(self, ctx):
        sa = ctx["h"]["sa"]
        r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=sa, json={
            "legacy_tenant_id": "default", "tenant_id": "default", "match_value": 1}, timeout=20)
        assert r.status_code == 422
        r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=sa, json={
            "legacy_tenant_id": "default", "tenant_id": "default"}, timeout=20)
        assert r.status_code == 422
        assert _db.legacy_tenant_map.count_documents({"legacy_tenant_id": "default"}) == 0

    def test_confirm_then_resolve_idempotent_and_conflict(self, ctx):
        sa = ctx["h"]["sa"]
        body = {"legacy_tenant_id": LEGACY_TENANT, "tenant_id": TA, "match_value": KEY_A}
        r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=sa, json=body, timeout=20)
        assert r.status_code == 200 and r.json()["status"] == "confirmed", r.text
        assert r.json()["confirmed_by"] == _be["SUPERADMIN_EMAIL"]
        r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=sa, json=body, timeout=20)
        assert r.status_code == 200
        assert _db.legacy_tenant_map.count_documents({"legacy_tenant_id": LEGACY_TENANT}) == 1
        r = requests.get(f"{API}/admin/legacy/tenant-map/resolve", headers=sa,
                         params={"legacy_tenant_id": LEGACY_TENANT}, timeout=20)
        assert r.status_code == 200 and r.json()["tenant_id"] == TA
        # un 2e tenant Journal vers le même client Documents → conflit explicite
        r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=sa, json={
            **body, "legacy_tenant_id": f"{LEGACY_TENANT}-bis"}, timeout=20)
        assert r.status_code == 409 and r.json()["detail"]["conflicts"][0]["type"] == "tenant_already_mapped"
        assert _db.audit_logs.count_documents({"entity": "legacy_tenant_map", "entity_id": LEGACY_TENANT,
                                               "action": "legacy_tenant_map_confirm"}) >= 1

    def test_tenant_map_superadmin_only(self, ctx):
        for h in (ctx["h"]["adm_a"], ctx["h"]["ro_a"]):
            assert requests.get(f"{API}/admin/legacy/tenant-map", headers=h, timeout=20).status_code == 403
            r = requests.post(f"{API}/admin/legacy/tenant-map/confirm", headers=h, json={
                "legacy_tenant_id": LEGACY_TENANT, "tenant_id": TA, "match_value": KEY_A}, timeout=20)
            assert r.status_code == 403

    def test_revoke_audited(self, ctx):
        sa = ctx["h"]["sa"]
        r = requests.post(f"{API}/admin/legacy/tenant-map/revoke", headers=sa,
                          json={"legacy_tenant_id": LEGACY_TENANT, "reason": ""}, timeout=20)
        assert r.status_code == 422
        r = requests.post(f"{API}/admin/legacy/tenant-map/revoke", headers=sa,
                          json={"legacy_tenant_id": LEGACY_TENANT, "reason": "test rollback"}, timeout=20)
        assert r.status_code == 200 and r.json()["status"] == "revoked"
        assert requests.get(f"{API}/admin/legacy/tenant-map/resolve", headers=sa,
                            params={"legacy_tenant_id": LEGACY_TENANT}, timeout=20).status_code == 404
        a = _db.audit_logs.find_one({"entity": "legacy_tenant_map", "action": "legacy_tenant_map_revoke",
                                     "entity_id": LEGACY_TENANT})
        assert a and "test rollback" in a["detail"] and a["user"] == _be["SUPERADMIN_EMAIL"] and a["created_at"]


class TestVehicleMap:
    def _payload(self, ctx):
        v = ctx["v"]
        trk = _db.vehicles.find_one({"id": v["a_trk"]})["navixy_tracker_id"]
        return {"vehicles": [
            {"legacy_vehicle_id": f"{LEGACY_VEHICLE}-vin", "vin": f"wvw-zzz1kz{RUN[:8]}", "plate": "XX 1"},
            {"legacy_vehicle_id": f"{LEGACY_VEHICLE}-trk", "navixy_tracker_id": trk, "plate": "XX 2"},
            {"legacy_vehicle_id": f"{LEGACY_VEHICLE}-plate", "plate": f"lc-{RUN[:5]}", "model": "Plate only"},
            {"legacy_vehicle_id": f"{LEGACY_VEHICLE}-none", "plate": "ZZ 999999"},
        ]}

    def test_7_8_candidates_read_only_plate_manual_tracker_warning(self, ctx):
        h, v = ctx["h"]["adm_a"], ctx["v"]
        before = _db.legacy_vehicle_map.count_documents({"tenant_id": TA})
        r = requests.post(f"{API}/legacy/vehicle-map/candidates", headers=h, json=self._payload(ctx), timeout=20)
        assert r.status_code == 200, r.text
        items = {i["legacy_vehicle_id"]: i for i in r.json()["items"]}
        vin = items[f"{LEGACY_VEHICLE}-vin"]
        assert vin["status"] == "strong_candidate" and vin["method_suggested"] == "vin"
        assert vin["candidates"][0]["vehicle_id"] == v["a_vin"]
        trk = items[f"{LEGACY_VEHICLE}-trk"]
        assert trk["status"] == "candidate_warning" and "tracker_join_no_assignment_history" in trk["warnings"]
        assert trk["method_suggested"] == "tracker_history_confirmed" and trk["candidates"][0]["vehicle_id"] == v["a_trk"]
        plate = items[f"{LEGACY_VEHICLE}-plate"]
        assert plate["status"] == "manual_review" and plate["method_suggested"] == "manual"
        assert plate["candidates"][0]["vehicle_id"] == v["a_plate"] and plate["candidates"][0]["matched_by"] == "plate"
        assert items[f"{LEGACY_VEHICLE}-none"]["status"] == "not_found"
        assert r.json()["written"] == 0 and _db.legacy_vehicle_map.count_documents({"tenant_id": TA}) == before
        # aucun candidat du tenant B ne fuit
        assert all(c["vehicle_id"] != v["b_veh"] for i in items.values() for c in i["candidates"])

    def test_stage_then_list(self, ctx):
        h = ctx["h"]["adm_a"]
        r = requests.post(f"{API}/legacy/vehicle-map/stage", headers=h, json=self._payload(ctx), timeout=20)
        assert r.status_code == 200 and r.json()["created"] == 4 and r.json()["skipped"] == 0, r.text
        r = requests.post(f"{API}/legacy/vehicle-map/stage", headers=h, json=self._payload(ctx), timeout=20)
        assert r.json()["created"] == 0 and r.json()["updated"] == 4
        assert _db.legacy_vehicle_map.count_documents({"tenant_id": TA}) == 4
        r = requests.get(f"{API}/legacy/vehicle-map", headers=h, params={"status": "pending"}, timeout=20)
        assert r.status_code == 200 and r.json()["counts"]["pending"] == 4
        assert all(row["status"] == "pending" and row["vehicle_id"] is None for row in r.json()["rows"])
        # le tenant B ne voit rien
        rb = requests.get(f"{API}/legacy/vehicle-map", headers=ctx["h"]["adm_b"], timeout=20)
        assert rb.json()["rows"] == [] and rb.json()["counts"]["pending"] == 0

    def test_confirm_methods_and_audit(self, ctx):
        h, v = ctx["h"]["adm_a"], ctx["v"]
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-vin/confirm", headers=h,
                          json={"vehicle_id": v["a_vin"], "note": "vin ok"}, timeout=20)
        assert r.status_code == 200 and r.json()["status"] == "confirmed" and r.json()["method"] == "vin", r.text
        assert r.json()["vehicle"]["vehicle_id"] == v["a_vin"]
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-trk/confirm", headers=h,
                          json={"vehicle_id": v["a_trk"]}, timeout=20)
        assert r.json()["method"] == "tracker_history_confirmed"
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-plate/confirm", headers=h,
                          json={"vehicle_id": v["a_plate"]}, timeout=20)
        assert r.json()["method"] == "manual"
        a = _db.audit_logs.find_one({"entity": "legacy_vehicle_map", "action": "legacy_map_confirm",
                                     "entity_id": f"{LEGACY_VEHICLE}-vin", "tenant_id": TA})
        assert a and a["vehicle_id"] == v["a_vin"] and a["user"].startswith("legacy-adm-a") and "via vin" in a["detail"]
        # re-confirmer la même cible = idempotent, pas de doublon
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-vin/confirm", headers=h,
                          json={"vehicle_id": v["a_vin"]}, timeout=20)
        assert r.status_code == 200
        assert _db.legacy_vehicle_map.count_documents({"tenant_id": TA, "legacy_vehicle_id": f"{LEGACY_VEHICLE}-vin"}) == 1
        # une ligne confirmée n'est pas écrasée par un re-stage
        r = requests.post(f"{API}/legacy/vehicle-map/stage", headers=h, json=self._payload(ctx), timeout=20)
        assert r.json()["skipped"] == 3 and r.json()["updated"] == 1

    def test_9_conflict_no_silent_overwrite(self, ctx):
        h, v = ctx["h"]["adm_a"], ctx["v"]
        # X (déjà → a_vin) vers a_plate (déjà rattaché à -plate) → 2 conflits, refus 409
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-vin/confirm", headers=h,
                          json={"vehicle_id": v["a_plate"]}, timeout=20)
        assert r.status_code == 409, r.text
        types = {c["type"] for c in r.json()["detail"]["conflicts"]}
        assert types == {"legacy_already_confirmed", "vehicle_already_mapped"}
        row = _db.legacy_vehicle_map.find_one({"tenant_id": TA, "legacy_vehicle_id": f"{LEGACY_VEHICLE}-vin"})
        assert row["vehicle_id"] == v["a_vin"]
        # override sans motif → toujours 409
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-vin/confirm", headers=h,
                          json={"vehicle_id": v["a_plate"], "override": True}, timeout=20)
        assert r.status_code == 409
        # override explicite avec motif → remplacé + audit avant/après
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-vin/confirm", headers=h,
                          json={"vehicle_id": v["a_plate"], "override": True, "reason": "correction manuelle"}, timeout=20)
        assert r.status_code == 200 and r.json()["vehicle_id"] == v["a_plate"]
        assert r.json()["conflict_override"]["before"]["vehicle_id"] == v["a_vin"]
        a = _db.audit_logs.find_one({"entity": "legacy_vehicle_map", "action": "legacy_map_replace",
                                     "entity_id": f"{LEGACY_VEHICLE}-vin"})
        assert a and "correction manuelle" in a["detail"] and v["a_vin"] in a["detail"]

    def test_reject_requires_reason_and_audited(self, ctx):
        h = ctx["h"]["adm_a"]
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-none/reject", headers=h,
                          json={"reason": "  "}, timeout=20)
        assert r.status_code == 422
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-none/reject", headers=h,
                          json={"reason": "véhicule inconnu côté Documents"}, timeout=20)
        assert r.status_code == 200 and r.json()["status"] == "rejected"
        r = requests.post(f"{API}/legacy/vehicle-map/does-not-exist-{RUN}/reject", headers=h,
                          json={"reason": "x"}, timeout=20)
        assert r.status_code == 404
        a = _db.audit_logs.find_one({"entity": "legacy_vehicle_map", "action": "legacy_map_reject",
                                     "entity_id": f"{LEGACY_VEHICLE}-none"})
        assert a and "quarantaine" in a["detail"]

    def test_10_read_only_writes_403(self, ctx):
        ro, v = ctx["h"]["ro_a"], ctx["v"]
        before = _db.legacy_vehicle_map.find_one({"tenant_id": TA, "legacy_vehicle_id": f"{LEGACY_VEHICLE}-trk"})
        assert requests.get(f"{API}/legacy/vehicle-map", headers=ro, timeout=20).status_code == 200
        for url, body in [("/legacy/vehicle-map/candidates", self._payload(ctx)),
                          ("/legacy/vehicle-map/stage", self._payload(ctx)),
                          (f"/legacy/vehicle-map/{LEGACY_VEHICLE}-trk/confirm", {"vehicle_id": v["a_plate"], "override": True, "reason": "x"}),
                          (f"/legacy/vehicle-map/{LEGACY_VEHICLE}-trk/reject", {"reason": "x"})]:
            r = requests.post(f"{API}{url}", headers=ro, json=body, timeout=20)
            assert r.status_code == 403, (url, r.status_code, r.text)
        after = _db.legacy_vehicle_map.find_one({"tenant_id": TA, "legacy_vehicle_id": f"{LEGACY_VEHICLE}-trk"})
        assert before == after

    def test_11_cross_tenant_fail_closed(self, ctx):
        hb, v = ctx["h"]["adm_b"], ctx["v"]
        # B tente de confirmer une ligne de A vers un véhicule de A → 404 (véhicule hors tenant), rien n'est écrit chez A
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-trk/confirm", headers=hb,
                          json={"vehicle_id": v["a_trk"]}, timeout=20)
        assert r.status_code == 404
        # B confirme le même legacy id vers SON véhicule → ligne distincte chez B, celle de A intacte
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-trk/confirm", headers=hb,
                          json={"vehicle_id": v["b_veh"]}, timeout=20)
        assert r.status_code == 200 and r.json()["tenant_id"] == TB
        row_a = _db.legacy_vehicle_map.find_one({"tenant_id": TA, "legacy_vehicle_id": f"{LEGACY_VEHICLE}-trk"})
        assert row_a["vehicle_id"] == v["a_trk"]
        # A ne peut pas rejeter la ligne de B (404) ; A ne voit pas la ligne de B
        r = requests.post(f"{API}/legacy/vehicle-map/{LEGACY_VEHICLE}-trk/reject", headers=ctx["h"]["adm_a"],
                          json={"reason": "x"}, timeout=20)
        assert r.status_code == 200  # rejette SA propre ligne (tenant A), pas celle de B
        assert _db.legacy_vehicle_map.find_one({"tenant_id": TB, "legacy_vehicle_id": f"{LEGACY_VEHICLE}-trk"})["status"] == "confirmed"
        rows_a = requests.get(f"{API}/legacy/vehicle-map", headers=ctx["h"]["adm_a"], params={"status": "all"}, timeout=20)
        assert rows_a.status_code == 200
        assert all(r_["tenant_id"] == TA for r_ in requests.get(f"{API}/legacy/vehicle-map", headers=ctx["h"]["adm_a"], timeout=20).json()["rows"])
        # candidats depuis B : aucun véhicule de A
        r = requests.post(f"{API}/legacy/vehicle-map/candidates", headers=hb, json=self._payload(ctx), timeout=20)
        assert all(c["vehicle_id"] == v["b_veh"] for i in r.json()["items"] for c in i["candidates"])

    def test_no_real_legacy_data_migrated(self):
        """Preuve : aucun document / transaction métier portant legacy_source hors des tenants pytest."""
        for coll in ("documents", "fuel_transactions"):
            assert _db[coll].count_documents({"legacy_id": {"$exists": True},
                                              "tenant_id": {"$not": {"$regex": "^pytest-"}}}) == 0


class TestRequireRoles:
    def test_resolver_unchanged_422_without_criteria(self, ctx):
        r = requests.get(f"{API}/vehicles/resolve", headers=ctx["h"]["adm_a"], timeout=20)
        assert r.status_code == 422

    def test_superadmin_acting_tenant_passes_require_roles(self, ctx):
        sa = {**ctx["h"]["sa"], "X-Acting-Tenant": TA}
        r = requests.get(f"{API}/legacy/vehicle-map", headers=sa, timeout=20)
        assert r.status_code == 200 and all(row["tenant_id"] == TA for row in r.json()["rows"])
