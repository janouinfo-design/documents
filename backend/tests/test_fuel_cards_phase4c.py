"""Phase 4C — Lot E : cartes carburant (`fuel_cards`) + affectations datées (`fuel_card_assignments`).
D2 : (fournisseur, last4) NON unique (collision = avertissement + confirmation, aucune auto-fusion), aucun fingerprint HMAC ;
statuts Journal 1:1 déclarés (jamais automatiques), `expiration_state` dérivé (seuils Échéances tenant), soft-delete `is_deleted`,
1 affectation ouverte par type, 409 ASSIGNMENT_OVERLAP / replace+motif (règle Lot C, jour de passation), resolve lecture seule,
RBAC read_only, isolation tenant fail-closed, aucun effet fuel_transactions / Coûts / Amendes. Aucune donnée Journal réelle."""
import uuid
from datetime import datetime, timedelta, timezone

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

_BASE = (dotenv_values("/app/frontend/.env").get("REACT_APP_BACKEND_URL") or "").rstrip("/")
_ENV = dotenv_values("/app/backend/.env")
_RUN = uuid.uuid4().hex[:8]
TENANT_A, TENANT_B = f"pytest-fc-a-{_RUN}", f"pytest-fc-b-{_RUN}"
ADMIN_A = (f"fc-adm-a-{_RUN}@pytest.ch", f"FcAdmA-{_RUN}-1")
RO_A = (f"fc-ro-a-{_RUN}@pytest.ch", f"FcRoA-{_RUN}-1")
ADMIN_B = (f"fc-adm-b-{_RUN}@pytest.ch", f"FcAdmB-{_RUN}-1")
STATUSES = ["active", "suspendue", "expiree", "bloquee", "remplacee"]
JOURNAL = {"active": "active", "suspended": "suspendue", "expired": "expiree", "blocked": "bloquee", "replaced": "remplacee"}
_D = lambda n: (datetime.now(timezone.utc) + timedelta(days=n)).strftime("%Y-%m-%d")  # noqa: E731
TODAY = _D(0)
_S, _cache = {}, {}


def _mongo():
    return MongoClient(_ENV["MONGO_URL"])[_ENV["DB_NAME"]]


def _h(creds=ADMIN_A):
    if creds not in _cache:
        r = requests.post(f"{_BASE}/api/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
        assert r.status_code == 200, r.text
        _cache[creds] = {"Authorization": f"Bearer {r.json()['token']}"}
    return _cache[creds]


def sa():
    return _h((_ENV["SUPERADMIN_EMAIL"], _ENV["SUPERADMIN_PASSWORD"]))


def _req(method, path, body=None, creds=ADMIN_A, **kw):
    return requests.request(method, f"{_BASE}/api{path}", json=body, headers=_h(creds), timeout=60, **kw)


def _card(creds=ADMIN_A, **over):
    body = {"fournisseur": "Migrol", "last4": "1234", "type_affectation": "vehicule", "expire_le": _D(400), **over}
    return _req("POST", "/fuel-cards", body, creds)


def _mk(**over):
    r = _card(**over)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _get(card_id, creds=ADMIN_A):
    r = _req("GET", f"/fuel-cards/{card_id}", creds=creds)
    assert r.status_code == 200, r.text
    return r.json()


def _assign(card_id, creds=ADMIN_A, **over):
    return _req("POST", f"/fuel-cards/{card_id}/assignments", {"type": "vehicule", "valid_from": TODAY, **over}, creds)


def _db(coll, **q):
    return _mongo()[coll].find_one(q, {"_id": 0})


def _audits(entity, entity_id, action=None, tenant=TENANT_A):
    q = {"tenant_id": tenant, "entity": entity, "entity_id": entity_id}
    if action:
        q["action"] = action
    return list(_mongo().audit_logs.find(q, {"_id": 0}).sort("created_at", 1))


def _snapshot():
    db = _mongo()
    return {"ftx": db.fuel_transactions.count_documents({}), "docs": db.documents.count_documents({}),
            "costs_a": _req("GET", "/costs").json(), "fines_a": _req("GET", "/fines").json()["total"],
            "energy_a": _req("GET", "/energy").json()["totals"]}


def setup_module():
    for tenant, admin in ((TENANT_A, ADMIN_A), (TENANT_B, ADMIN_B)):
        assert requests.post(f"{_BASE}/api/admin/tenants", json={"name": tenant, "id": tenant}, headers=sa(), timeout=30).status_code == 200
        assert requests.post(f"{_BASE}/api/admin/tenants/{tenant}/users", json={"email": admin[0], "password": admin[1], "role": "admin"},
                             headers=sa(), timeout=30).status_code == 200
    assert requests.post(f"{_BASE}/api/admin/tenants/{TENANT_A}/users", json={"email": RO_A[0], "password": RO_A[1], "role": "read_only"},
                         headers=sa(), timeout=30).status_code == 200
    for key, plaque, creds in (("veh_a", f"VD {_RUN[:6].upper()}", ADMIN_A), ("veh_a2", f"FR {_RUN[:6].upper()}", ADMIN_A), ("veh_b", f"BE {_RUN[:6].upper()}", ADMIN_B)):
        r = _req("POST", "/vehicles", {"plaque": plaque, "kilometrage": 1000}, creds)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    for key, nom, creds in (("drv_a", "Favre", ADMIN_A), ("drv_a2", "Morel", ADMIN_A), ("drv_b", "Bieri", ADMIN_B)):
        r = _req("POST", "/drivers", {"nom": nom, "prenom": "Test", "matricule_interne": f"{nom[:2].upper()}-{_RUN[:4]}"}, creds)
        assert r.status_code == 200, r.text
        _S[key] = r.json()["id"]
    _S["snap"] = _snapshot()
    _h(RO_A), _h(ADMIN_B)  # connexions préalables (aucun effet de bord de login pendant les tests d'absence d'écriture)


def teardown_module():
    db = _mongo()
    for tenant in (TENANT_A, TENANT_B):
        for coll in ("users", "vehicles", "documents", "files", "audit_logs", "alerts", "vehicle_field_meta", "tenant_integrations",
                     "doc_categories", "doc_requirements", "tenant_settings", "fuel_transactions", "drivers", "driver_assignments",
                     "fuel_cards", "fuel_card_assignments"):
            db[coll].delete_many({"tenant_id": tenant})
        db.tenants.delete_many({"id": tenant})


class TestReferentiel:
    def test_01_creation_identite_humaine_aucun_fingerprint(self):
        r = _card(compte_fournisseur="ACC-1", external_card_id="EXT-1", produits_autorises=["diesel", "adblue"], pays_autorises=["CH", "FR"],
                  plafond_tx=200.0, numero_masque="**** **** 1234", notes="Carte principale")
        assert r.status_code == 200, r.text
        c = r.json()
        _S["c1"] = c["id"]
        assert c["label"] == "Migrol ••••1234" and c["statut"] == "active" and c["statut_label"] == "Active" and c["created"] is True
        assert c["expiration_state"] == "valide" and c["utilisable"] is True and c["is_deleted"] is False
        assert c["affectations_courantes"] == {} and c["vehicule_courant"] is None and c["conducteur_courant"] is None
        assert [w["code"] for w in c["warnings"]] == ["CARD_UNASSIGNED"]
        db = _db("fuel_cards", id=c["id"])
        assert db["tenant_id"] == TENANT_A and db["last4"] == "1234" and db["produits_autorises"] == ["diesel", "adblue"]
        assert not any(k in db for k in ("fingerprint", "hmac", "numero", "numero_complet", "card_number", "pan"))  # D2
        assert db["created_at"] and db["updated_at"] and db["created_by"] == ADMIN_A[0]
        a = _audits("fuel_card", c["id"], "create")
        assert len(a) == 1 and "Migrol ••••1234" in a[0]["detail"] and a[0]["user"] == ADMIN_A[0]

    def test_02_fingerprint_refuse_et_validations(self):
        r = _card(fingerprint="a" * 64)
        assert r.status_code == 422  # champ inconnu interdit (extra=forbid) : jamais stocké
        assert _card(last4="12345").status_code == 422 and _card(last4="12a4").status_code == 422
        assert _card(fournisseur=" ").status_code == 422
        assert _card(numero_masque="1234 5678 9012 3456").status_code == 422  # jamais un numéro complet
        assert _card(expire_le="31.12.2027").status_code == 422
        assert _card(activee_le=_D(10), expire_le=_D(5)).status_code == 422
        assert _card(statut="inconnu").status_code == 422 and _card(type_affectation="camion").status_code == 422
        assert _card(plafond_tx=-1).status_code == 422
        assert _mongo().fuel_cards.count_documents({"tenant_id": TENANT_A}) == 1

    def test_03_meme_fournisseur_last4_autorise_apres_confirmation_aucune_fusion(self):
        r = _card(external_card_id="EXT-2")
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["code"] == "LAST4_COLLISION" and [c["id"] for c in d["cards"]] == [_S["c1"]] and "aucune fusion" in d["message"].lower()
        assert _mongo().fuel_cards.count_documents({"tenant_id": TENANT_A}) == 1  # rien écrit sans confirmation
        r = _card(external_card_id="EXT-2", collision_confirmed=True)
        assert r.status_code == 200, r.text
        _S["c2"] = r.json()["id"]
        assert _S["c2"] != _S["c1"] and r.json()["collision_with"] == [_S["c1"]] and r.json()["label"] == "Migrol ••••1234"
        assert _mongo().fuel_cards.count_documents({"tenant_id": TENANT_A, "fournisseur": "Migrol", "last4": "1234"}) == 2
        assert "collision (fournisseur, last4) confirmée" in _audits("fuel_card", _S["c2"], "create")[0]["detail"]
        idx = _mongo().fuel_cards.index_information()
        assert idx["fuel_card_identity_non_unique"].get("unique") is not True
        assert idx["uniq_fuel_card_tenant_id"]["unique"] is True

    def test_04_legacy_idempotence_tenant_scopee(self):
        body = {"source": "legacy_import", "legacy_source": "journal", "legacy_id": f"CARD-{_RUN}", "fournisseur": "Shell", "last4": "9876",
                "external_card_id": "J-1", "statut": "suspended", "expire_le": "2027-12-31", "created_at": "2026-07-31T08:29:07Z"}
        r = _req("POST", "/fuel-cards", body)
        assert r.status_code == 200 and r.json()["created"] is True and r.json()["statut"] == "suspendue"
        cid = r.json()["id"]
        _S["legacy"] = cid
        db = _db("fuel_cards", id=cid)
        assert db["legacy_source"] == "journal" and db["legacy_id"] == f"CARD-{_RUN}" and db["migration_version"] and db["legacy_payload_sha256"]
        assert db["created_at"] == "2026-07-31T08:29:07Z" and db["created_by"] == "import" and "fingerprint" not in db
        assert _req("POST", "/fuel-cards/" + cid + "/status", {"statut": "active", "motif": "réactivée après vérification"}).status_code == 200
        r = _req("POST", "/fuel-cards", {**body, "statut": "blocked", "notes": "rejeu"})
        assert r.status_code == 200 and r.json()["created"] is False and r.json()["id"] == cid
        db = _db("fuel_cards", id=cid)
        assert db["statut"] == "active" and db["notes"] == "rejeu"  # rejeu : données mises à jour, cycle de vie courant jamais écrasé
        assert _mongo().fuel_cards.count_documents({"tenant_id": TENANT_A, "legacy_id": f"CARD-{_RUN}"}) == 1
        assert _audits("fuel_card", cid, "legacy_replay")
        r = _req("POST", "/fuel-cards", {**body, "fournisseur": "Shell"}, creds=ADMIN_B)  # même legacy_id, autre tenant = autre carte
        assert r.status_code == 200 and r.json()["created"] is True and r.json()["id"] != cid
        _S["legacy_b"] = r.json()["id"]
        assert _req("POST", "/fuel-cards", {"source": "legacy_import", "fournisseur": "X", "last4": "0000"}).status_code == 422

    def test_05_lecture_liste_filtres_et_referentiels(self):
        r = _req("GET", "/fuel-cards")
        assert r.status_code == 200
        body = r.json()
        assert {c["id"] for c in body["items"]} == {_S["c1"], _S["c2"], _S["legacy"]} and body["total"] == 3
        assert [s["code"] for s in body["statuses"]] == STATUSES and [t["code"] for t in body["assignment_types"]] == ["vehicule", "conducteur", "pool", "autre"]
        assert [e["code"] for e in body["expiration_states"]] == ["valide", "bientot", "expiree", "sans_date"]
        assert body["fournisseurs"] == ["Migrol", "Shell"] and body["thresholds"]["urgent_days"] == 30 and body["thresholds"]["warning_days"] == 90
        assert body["stats"]["total"] == 3 and body["stats"]["sans_affectation"] == 3 and body["stats"]["archivees"] == 0
        g = lambda **p: {c["id"] for c in _req("GET", "/fuel-cards", params=p).json()["items"]}  # noqa: E731
        assert g(fournisseur="Shell") == {_S["legacy"]} and g(q="9876") == {_S["legacy"]} and g(q="ext-2") == {_S["c2"]}
        assert g(statut="active") == {_S["c1"], _S["c2"], _S["legacy"]} and g(statut="suspended") == set()
        assert g(affectation="sans") == {_S["c1"], _S["c2"], _S["legacy"]} and g(affectation="avec") == set()
        assert _req("GET", "/fuel-cards", params={"statut": "zzz"}).status_code == 422
        assert _req("GET", "/fuel-cards", params={"archived": "maybe"}).status_code == 422
        assert _req("GET", "/fuel-cards", params={"expiration_state": "x"}).status_code == 422
        one = _get(_S["c1"])
        assert one["assignments"] == [] and one["label"] == "Migrol ••••1234"

    def test_06_modification_auditee_avant_apres_et_collision_en_edition(self):
        r = _req("PATCH", f"/fuel-cards/{_S['legacy']}", {"notes": "note 2", "plafond_jour": 500, "type_affectation": "driver"})
        assert r.status_code == 200 and r.json()["plafond_jour"] == 500 and r.json()["type_affectation"] == "conducteur"
        a = _audits("fuel_card", _S["legacy"], "modify")
        assert len(a) == 1 and "notes: rejeu → note 2" in a[0]["detail"] and "plafond_jour: — → 500" in a[0]["detail"]
        assert _req("PATCH", f"/fuel-cards/{_S['legacy']}", {"fingerprint": "x"}).status_code == 422
        assert _req("PATCH", f"/fuel-cards/{_S['legacy']}", {"last4": "12"}).status_code == 422
        assert _req("PATCH", f"/fuel-cards/{_S['legacy']}", {}).status_code == 422
        r = _req("PATCH", f"/fuel-cards/{_S['legacy']}", {"fournisseur": "Migrol", "last4": "1234"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "LAST4_COLLISION" and len(r.json()["detail"]["cards"]) == 2
        assert _db("fuel_cards", id=_S["legacy"])["fournisseur"] == "Shell"
        r = _req("PATCH", f"/fuel-cards/{_S['legacy']}", {"fournisseur": "Migrol", "last4": "1234", "collision_confirmed": True})
        assert r.status_code == 200 and r.json()["label"] == "Migrol ••••1234"
        assert _req("PATCH", f"/fuel-cards/{_S['legacy']}", {"fournisseur": "Shell", "last4": "9876"}).status_code == 200


class TestStatutEtExpiration:
    def test_07_statut_declare_motif_obligatoire_audit_avant_apres(self):
        cid = _S["c1"]
        assert _req("POST", f"/fuel-cards/{cid}/status", {"statut": "suspendue"}).status_code == 422
        assert _req("POST", f"/fuel-cards/{cid}/status", {"statut": "suspendue", "motif": "ab"}).status_code == 422
        assert _req("POST", f"/fuel-cards/{cid}/status", {"statut": "gelee", "motif": "motif ok"}).status_code == 422
        assert _db("fuel_cards", id=cid)["statut"] == "active"
        for j, code in JOURNAL.items():
            if code == "active":
                continue
            r = _req("POST", f"/fuel-cards/{cid}/status", {"statut": j, "motif": f"test {j}"})
            assert r.status_code == 200 and r.json()["statut"] == code, (j, r.text)
        r = _req("POST", f"/fuel-cards/{cid}/status", {"statut": "remplacee", "motif": "déjà"})
        assert r.status_code == 409 and r.json()["detail"]["code"] == "STATUS_UNCHANGED"
        r = _req("POST", f"/fuel-cards/{cid}/status", {"statut": "active", "motif": "réactivation", "remplacee_par": cid})
        assert r.status_code == 422
        r = _req("POST", f"/fuel-cards/{cid}/status", {"statut": "active", "motif": "réactivation", "remplacee_par": "zzz"})
        assert r.status_code == 422
        r = _req("POST", f"/fuel-cards/{cid}/status", {"statut": "active", "motif": "réactivation après test"})
        assert r.status_code == 200 and r.json()["statut"] == "active" and r.json()["utilisable"] is True
        a = _audits("fuel_card", cid, "status")
        assert len(a) == 5 and "active (Active) → suspendue (Suspendue) — motif : test suspended" in a[0]["detail"]
        assert "remplacee (Remplacée) → active (Active) — motif : réactivation après test" in a[-1]["detail"] and "expire_le inchangé" in a[-1]["detail"]
        db = _db("fuel_cards", id=cid)
        assert db["statut_motif"] == "réactivation après test" and db["statut_changed_by"] == ADMIN_A[0]
        assert db["expire_le"] == _D(400)  # jamais touché par un changement de statut

    def test_08_expiration_derivee_sans_changement_automatique_de_statut(self):
        future, past, soon, nodate = _mk(last4="1001", expire_le=_D(400)), _mk(last4="1002", expire_le=_D(-1)), _mk(last4="1003", expire_le=_D(45)), _mk(last4="1004", expire_le=None)
        _S.update({"exp_future": future, "exp_past": past, "exp_soon": soon, "exp_nodate": nodate})
        f, p, s, n = _get(future), _get(past), _get(soon), _get(nodate)
        assert f["expiration_state"] == "valide" and f["utilisable"] is True and f["expiration_statut"] == "OK"
        assert p["expiration_state"] == "expiree" and p["utilisable"] is False and p["statut"] == "active" and p["expiration_statut"] == "EXPIRE"
        assert p["expiration_days"] == -1 and [w["code"] for w in p["warnings"]][0] == "CARD_EXPIRED"
        assert s["expiration_state"] == "bientot" and s["utilisable"] is True and s["expiration_statut"] == "A_PLANIFIER" and s["expiration_days"] == 45
        assert [w["code"] for w in s["warnings"]][0] == "CARD_EXPIRING_SOON"
        urgent = _get(_mk(last4="1005", expire_le=_D(10)))
        assert urgent["expiration_state"] == "bientot" and urgent["expiration_statut"] == "URGENT"
        assert n["expiration_state"] == "sans_date" and n["utilisable"] is True and n["expiration_days"] is None
        assert _db("fuel_cards", id=past)["statut"] == "active"  # recalcul = lecture seule, aucune écriture
        for _ in range(2):
            _req("GET", "/fuel-cards")
        assert _db("fuel_cards", id=past)["statut"] == "active" and "expiration_state" not in _db("fuel_cards", id=past)
        # expiree déclarée + date future → non utilisable (statut prime), état dérivé reste `valide`
        r = _req("POST", f"/fuel-cards/{future}/status", {"statut": "expiree", "motif": "retournée au fournisseur"})
        assert r.status_code == 200 and r.json()["utilisable"] is False and r.json()["expiration_state"] == "valide"
        assert _req("POST", f"/fuel-cards/{future}/status", {"statut": "active", "motif": "erreur de saisie"}).status_code == 200
        # changement de la date = modification auditée, statut déclaré inchangé
        r = _req("PATCH", f"/fuel-cards/{past}", {"expire_le": _D(200)})
        assert r.status_code == 200 and r.json()["expiration_state"] == "valide" and r.json()["utilisable"] is True and r.json()["statut"] == "active"
        a = _audits("fuel_card", past, "modify")
        assert f"expiration {_D(-1)} → {_D(200)} (statut déclaré inchangé : active)" in a[-1]["detail"]
        assert _req("PATCH", f"/fuel-cards/{past}", {"expire_le": _D(-1)}).status_code == 200

    def test_09_echeance_expiration_dans_deadlines_memes_seuils(self):
        dl = _req("GET", "/deadlines").json()
        cards = {i["card_id"]: i for i in dl["items"] if i["type"] == "carte_carburant"}
        assert dl["thresholds"]["urgent_days"] == 30 and dl["thresholds"]["warning_days"] == 90
        assert cards[_S["exp_past"]]["statut"] == "EXPIRE" and cards[_S["exp_soon"]]["statut"] == "A_PLANIFIER" and cards[_S["exp_future"]]["statut"] == "OK"
        assert _S["exp_nodate"] not in cards  # sans date = pas d'échéance
        it = cards[_S["exp_past"]]
        assert it["category"] == "Carte carburant" and it["source"] == "fuel_card" and it["is_document_deadline"] is False and it["document_id"] is None
        assert it["label"].startswith("Carte carburant Migrol ••••1002") and it["vehicle_id"] is None and it["card_statut"] == "active"
        assert _S["exp_past"] not in {i.get("card_id") for i in _req("GET", "/alerts").json()["items"]}  # pas de moteur d'alertes supplémentaire
        r = _req("GET", "/deadlines", params={"category": "Carte carburant"})
        assert r.status_code == 200 and all(i["type"] == "carte_carburant" for i in r.json()["items"]) and r.json()["count"] >= 3
        # statut remplacee / bloquee → hors Échéances (spec §2.8)
        assert _req("POST", f"/fuel-cards/{_S['exp_soon']}/status", {"statut": "bloquee", "motif": "carte volée"}).status_code == 200
        assert _S["exp_soon"] not in {i.get("card_id") for i in _req("GET", "/deadlines").json()["items"]}
        assert _req("POST", f"/fuel-cards/{_S['exp_soon']}/status", {"statut": "active", "motif": "retrouvée"}).status_code == 200


class TestArchivage:
    def test_10_archivage_soft_delete_motif_masque_restauration(self):
        cid = _mk(last4="2001")
        assert _req("POST", f"/fuel-cards/{cid}/archive", {}).status_code == 422
        assert _req("POST", f"/fuel-cards/{cid}/archive", {"motif": "ab"}).status_code == 422
        r = _req("POST", f"/fuel-cards/{cid}/archive", {"motif": "Carte rendue au fournisseur"})
        assert r.status_code == 200 and r.json()["is_deleted"] is True and r.json()["statut"] == "active"
        db = _db("fuel_cards", id=cid)
        assert db["is_deleted"] is True and db["archive_motif"] == "Carte rendue au fournisseur" and db["archived_by"] == ADMIN_A[0] and db["statut"] == "active"
        ids = lambda **p: {c["id"] for c in _req("GET", "/fuel-cards", params=p).json()["items"]}  # noqa: E731
        assert cid not in ids() and cid in ids(archived="true") and cid in ids(archived="all") and cid not in ids(archived="false")
        assert _req("GET", "/fuel-cards").json()["stats"]["archivees"] == 1
        assert _get(cid)["is_deleted"] is True  # fiche toujours lisible
        assert _req("POST", f"/fuel-cards/{cid}/archive", {"motif": "encore"}).status_code == 409
        assert _req("PATCH", f"/fuel-cards/{cid}", {"notes": "x"}).status_code == 409
        assert _req("POST", f"/fuel-cards/{cid}/status", {"statut": "bloquee", "motif": "test"}).status_code == 409
        assert _assign(cid, vehicle_id=_S["veh_a"]).status_code == 409
        r = _req("POST", f"/fuel-cards/{cid}/restore", {})
        assert r.status_code == 200 and r.json()["is_deleted"] is False and r.json()["statut"] == "active"
        assert cid in ids() and _req("POST", f"/fuel-cards/{cid}/restore", {}).status_code == 409
        actions = [h["action"] for h in _req("GET", f"/fuel-cards/{cid}/history").json()]
        assert actions == ["create", "archive", "restore"]
        a = _audits("fuel_card", cid, "archive")[0]
        assert "is_deleted false → true" in a["detail"] and "motif : Carte rendue au fournisseur" in a["detail"] and "statut métier conservé : active" in a["detail"]
        assert _mongo().fuel_cards.count_documents({"id": cid}) == 1  # aucune suppression physique
        _S["arch"] = cid


class TestAffectations:
    def test_11_affectation_vehicule_valide(self):
        cid = _S["c1"]
        r = _assign(cid, vehicle_id=_S["veh_a"], motif="Véhicule de service")
        assert r.status_code == 200, r.text
        a = r.json()
        _S["asg_v"] = a["id"]
        assert a["type"] == "vehicule" and a["vehicle_id"] == _S["veh_a"] and a["driver_id"] is None and a["valid_from"] == TODAY and a["valid_to"] is None
        assert a["active"] is True and a["created"] is True and a["replaced"] == [] and a["plaque"] == f"VD {_RUN[:6].upper()}" and a["cible"] == a["plaque"]
        c = _get(cid)
        assert c["vehicule_courant"]["vehicle_id"] == _S["veh_a"] and c["conducteur_courant"] is None and c["warnings"] == []
        assert c["affectations_courantes"]["vehicule"]["id"] == a["id"] and c["assignments_count"] == 1
        db = _db("fuel_card_assignments", id=a["id"])
        assert db["tenant_id"] == TENANT_A and db["card_id"] == cid and db["created_by"] == ADMIN_A[0] and db["motif"] == "Véhicule de service"
        au = _audits("fuel_card_assignment", a["id"], "create")
        assert len(au) == 1 and f"Migrol ••••1234 → Véhicule {a['plaque']} du {TODAY} (en cours)" in au[0]["detail"]
        assert {c["id"] for c in _req("GET", "/fuel-cards", params={"vehicle_id": _S["veh_a"]}).json()["items"]} == {cid}

    def test_12_affectation_conducteur_valide_coexiste_avec_vehicule(self):
        cid = _S["c1"]
        r = _assign(cid, type="conducteur", driver_id=_S["drv_a"], valid_from=_D(-5))
        assert r.status_code == 200, r.text  # type différent : aucun conflit avec l'affectation véhicule ouverte
        a = r.json()
        _S["asg_d"] = a["id"]
        assert a["type"] == "conducteur" and a["driver_id"] == _S["drv_a"] and a["vehicle_id"] is None and a["driver_nom"].startswith("Test Favre")
        c = _get(cid)
        assert c["vehicule_courant"]["vehicle_id"] == _S["veh_a"] and c["conducteur_courant"]["driver_id"] == _S["drv_a"]
        assert set(c["affectations_courantes"]) == {"vehicule", "conducteur"} and c["assignments_count"] == 2
        assert {x["id"] for x in _req("GET", "/fuel-cards", params={"driver_id": _S["drv_a"]}).json()["items"]} == {cid}
        r = _assign(cid, type="pool", valid_from=TODAY)
        assert r.status_code == 200 and r.json()["type"] == "pool" and r.json()["cible"] == "Pool"
        assert set(_get(cid)["affectations_courantes"]) == {"vehicule", "conducteur", "pool"}
        _S["asg_pool"] = r.json()["id"]

    def test_13_validations_et_refus_cross_tenant_fail_closed(self):
        cid = _S["c2"]
        assert _assign(cid, vehicle_id=None).status_code == 422  # vehicule sans vehicle_id
        assert _assign(cid, type="conducteur", driver_id=None).status_code == 422
        assert _assign(cid, type="conducteur", driver_id=_S["drv_a"], vehicle_id=_S["veh_a"]).status_code == 422  # XOR
        assert _assign(cid, type="pool", vehicle_id=_S["veh_a"]).status_code == 422
        assert _assign(cid, type="camion", vehicle_id=_S["veh_a"]).status_code == 422
        assert _assign(cid, vehicle_id=_S["veh_a"], valid_from=None).status_code == 422  # manuel : valid_from obligatoire
        assert _assign(cid, vehicle_id=_S["veh_a"], valid_from="07.10.2026").status_code == 422
        assert _assign(cid, vehicle_id=_S["veh_a"], valid_to=_D(-1)).status_code == 422
        assert _assign(cid, vehicle_id=_S["veh_b"]).status_code == 404  # véhicule d'un autre tenant
        assert _assign(cid, type="conducteur", driver_id=_S["drv_b"]).status_code == 404  # conducteur d'un autre tenant
        assert _assign(_S["legacy_b"], vehicle_id=_S["veh_a"]).status_code == 404  # carte d'un autre tenant
        assert _assign(cid, vehicle_id=_S["veh_a"], creds=ADMIN_B).status_code == 404
        assert _mongo().fuel_card_assignments.count_documents({"tenant_id": TENANT_A, "card_id": cid}) == 0
        for path in (f"/fuel-cards/{cid}", f"/fuel-cards/{cid}/assignments", f"/fuel-cards/{cid}/history"):
            assert _req("GET", path, creds=ADMIN_B).status_code == 404, path
        assert _req("PATCH", f"/fuel-cards/{cid}", {"notes": "intrus"}, creds=ADMIN_B).status_code == 404
        assert _req("POST", f"/fuel-cards/{cid}/status", {"statut": "bloquee", "motif": "intrus"}, creds=ADMIN_B).status_code == 404
        assert _req("POST", f"/fuel-cards/{cid}/archive", {"motif": "intrus"}, creds=ADMIN_B).status_code == 404
        assert _req("POST", f"/fuel-card-assignments/{_S['asg_v']}/close", {}, creds=ADMIN_B).status_code == 404
        assert _db("fuel_cards", id=cid)["statut"] == "active" and _db("fuel_card_assignments", id=_S["asg_v"])["valid_to"] is None
        assert {c["id"] for c in _req("GET", "/fuel-cards", creds=ADMIN_B).json()["items"]} == {_S["legacy_b"]}

    def test_14_conflit_meme_type_409_puis_replace_motif_regle_lot_c(self):
        cid = _S["c1"]
        r = _assign(cid, vehicle_id=_S["veh_a2"], valid_from=_D(3))
        assert r.status_code == 409, r.text
        d = r.json()["detail"]
        assert d["code"] == "ASSIGNMENT_OVERLAP" and [c["id"] for c in d["conflicts"]] == [_S["asg_v"]] and "Véhicule" in d["message"]
        assert _assign(cid, vehicle_id=_S["veh_a2"], valid_from=_D(3), replace=True).status_code == 422  # motif obligatoire
        assert _mongo().fuel_card_assignments.count_documents({"tenant_id": TENANT_A, "card_id": cid, "type": "vehicule"}) == 1
        r = _assign(cid, vehicle_id=_S["veh_a2"], valid_from=_D(3), replace=True, motif="Changement de véhicule")
        assert r.status_code == 200, r.text
        new = r.json()
        assert new["created"] is True and [x["id"] for x in new["replaced"]] == [_S["asg_v"]] and new["replaced"][0]["valid_to"] == _D(2)
        old = _db("fuel_card_assignments", id=_S["asg_v"])
        assert old["valid_to"] == _D(2) and old["replaced"] is True and old["closed_by"] == ADMIN_A[0] and old["close_motif"] == "Changement de véhicule"
        assert _audits("fuel_card_assignment", _S["asg_v"], "replace")[0]["detail"].endswith("motif : Changement de véhicule")
        c = _get(cid)
        assert c["vehicule_courant"]["vehicle_id"] == _S["veh_a"]  # aujourd'hui : l'ancienne reste courante jusqu'à J+2
        assert c["assignments_count"] == 4 and len([a for a in c["assignments"] if a["type"] == "vehicule"]) == 2
        # fermée + chevauchement d'une affectation déjà close → remplacement impossible, clôture explicite requise
        r = _assign(cid, vehicle_id=_S["veh_a"], valid_from=_D(1), replace=True, motif="test fermé")
        assert r.status_code == 409 and r.json()["detail"]["code"] == "ASSIGNMENT_OVERLAP"
        _S["asg_v2"] = new["id"]

    def test_15_remplacement_le_meme_jour_une_seule_affectation_courante(self):
        cid = _mk(last4="3001")
        a = _assign(cid, vehicle_id=_S["veh_a"], valid_from=TODAY).json()
        assert _get(cid)["vehicule_courant"]["vehicle_id"] == _S["veh_a"]
        r = _assign(cid, vehicle_id=_S["veh_a2"], valid_from=TODAY)
        assert r.status_code == 409 and r.json()["detail"]["code"] == "ASSIGNMENT_OVERLAP"
        r = _assign(cid, vehicle_id=_S["veh_a2"], valid_from=TODAY, replace=True, motif="Passation le jour même")
        assert r.status_code == 200, r.text
        b = r.json()
        old = _db("fuel_card_assignments", id=a["id"])
        assert old["valid_to"] == TODAY and old["replaced"] is True  # jour de passation : l'ancienne se termine le jour de son début
        c = _get(cid)
        cur = c["affectations_courantes"]["vehicule"]
        assert cur["id"] == b["id"] and cur["vehicle_id"] == _S["veh_a2"] and cur["ambiguous"] is False
        assert c["vehicule_courant"]["vehicle_id"] == _S["veh_a2"] and c["assignments_count"] == 2
        assert sum(1 for x in c["assignments"] if x["id"] == a["id"]) == 1  # historique conservé
        hist = [h["action"] for h in _req("GET", f"/fuel-cards/{cid}/history").json()]
        assert hist == ["create", "create", "replace", "create"]
        res = _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Migrol", "last4": "3001"}).json()
        assert res["status"] == "found" and res["card"]["affectations_courantes"]["vehicule"]["id"] == b["id"]
        dl = {i["card_id"]: i for i in _req("GET", "/deadlines").json()["items"] if i["type"] == "carte_carburant"}
        assert dl[cid]["vehicle_id"] == _S["veh_a2"]  # Échéances : véhicule courant sans ambiguïté
        _S["sameday"] = cid

    def test_16_fermeture_affectation_historique_conserve(self):
        aid = _S["asg_d"]
        r = _req("POST", f"/fuel-card-assignments/{aid}/close", {"valid_to": "bad"})
        assert r.status_code == 422
        r = _req("POST", f"/fuel-card-assignments/{aid}/close", {"valid_to": _D(-10)})
        assert r.status_code == 422  # antérieure à valid_from (J-5)
        r = _req("POST", f"/fuel-card-assignments/{aid}/close", {"motif": "Conducteur parti"})
        assert r.status_code == 200 and r.json()["valid_to"] == TODAY and r.json()["active"] is True  # inclusif : encore valable aujourd'hui
        db = _db("fuel_card_assignments", id=aid)
        assert db["valid_to"] == TODAY and db["closed_by"] == ADMIN_A[0] and db["close_motif"] == "Conducteur parti" and db["replaced"] is False
        assert _req("POST", f"/fuel-card-assignments/{aid}/close", {}).status_code == 409
        assert _audits("fuel_card_assignment", aid, "close")[0]["detail"].endswith("motif : Conducteur parti")
        r = _req("POST", f"/fuel-card-assignments/{_S['asg_pool']}/close", {"valid_to": _D(-1)})
        assert r.status_code == 422  # pool commence aujourd'hui
        r = _req("POST", f"/fuel-card-assignments/{_S['asg_pool']}/close", {"valid_to": TODAY})
        assert r.status_code == 200
        assert _mongo().fuel_card_assignments.count_documents({"tenant_id": TENANT_A, "card_id": _S["c1"]}) == 4  # rien supprimé
        assert _req("POST", "/fuel-card-assignments/zzz/close", {}).status_code == 404

    def test_17_legacy_assignment_valid_from_null_et_rejeu(self):
        cid = _S["legacy"]
        body = {"type": "vehicle", "vehicle_id": _S["veh_a2"], "valid_from": None, "source": "legacy_import", "legacy_source": "journal",
                "legacy_id": f"ASG-{_RUN}", "motif": "import"}
        r = _req("POST", f"/fuel-cards/{cid}/assignments", body)
        assert r.status_code == 200, r.text
        a = r.json()
        assert a["type"] == "vehicule" and a["valid_from"] is None and a["active"] is True and a["created"] is True
        assert "depuis toujours (legacy valid_from null)" in _audits("fuel_card_assignment", a["id"], "create")[0]["detail"]
        assert _get(cid)["vehicule_courant"]["vehicle_id"] == _S["veh_a2"]
        assert _req("POST", f"/fuel-card-assignments/{a['id']}/close", {"valid_to": _D(-1)}).status_code == 200  # fermeture sans valid_from
        r = _req("POST", f"/fuel-cards/{cid}/assignments", {**body, "motif": "rejeu"})
        assert r.status_code == 200 and r.json()["created"] is False and r.json()["id"] == a["id"]
        db = _db("fuel_card_assignments", id=a["id"])
        assert db["valid_to"] == _D(-1) and db["motif"] == "rejeu"  # rejeu : ne rouvre pas
        assert _mongo().fuel_card_assignments.count_documents({"tenant_id": TENANT_A, "legacy_id": f"ASG-{_RUN}"}) == 1
        assert _assign(cid, type="conducteur", driver_id=_S["drv_a2"], valid_from=TODAY).status_code == 200
        c = _get(cid)
        assert c["vehicule_courant"] is None and c["conducteur_courant"]["driver_id"] == _S["drv_a2"]

    def test_18_affectation_incoherente_conducteur_archive(self):
        cid = _S["legacy"]
        assert _req("POST", f"/drivers/{_S['drv_a2']}/archive").status_code == 200
        c = _get(cid)
        assert "ASSIGNMENT_INCONSISTENT" in [w["code"] for w in c["warnings"]]
        assert _req("POST", f"/drivers/{_S['drv_a2']}/restore").status_code == 200
        assert "ASSIGNMENT_INCONSISTENT" in [w["code"] for w in _get(cid)["warnings"]]  # restauré mais désactivé (règle Lot C) → toujours incohérent
        assert _req("PATCH", f"/drivers/{_S['drv_a2']}", {"actif": True}).status_code == 200
        assert "ASSIGNMENT_INCONSISTENT" not in [w["code"] for w in _get(cid)["warnings"]]


class TestResolveRbacIsolation:
    def test_19_resolve_lecture_seule_found_ambiguous_not_found(self):
        before = {"cards": _mongo().fuel_cards.count_documents({}), "asg": _mongo().fuel_card_assignments.count_documents({}),
                  "audit": _mongo().audit_logs.count_documents({}), "ftx": _mongo().fuel_transactions.count_documents({})}
        r = _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Migrol", "last4": "1234"})
        assert r.status_code == 200 and r.json()["status"] == "ambiguous" and r.json()["card"] is None and r.json()["written"] == 0
        assert {c["id"] for c in r.json()["candidates"]} == {_S["c1"], _S["c2"]}  # décision humaine requise
        assert all("fingerprint" not in c for c in r.json()["candidates"])
        r = _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Shell", "last4": "9876", "date": TODAY})
        assert r.json()["status"] == "found" and r.json()["card"]["id"] == _S["legacy"] and r.json()["card"]["affectations_courantes"]["conducteur"]["driver_id"] == _S["drv_a2"]
        r = _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Shell", "last4": "9876", "date": _D(-30)})
        assert r.json()["status"] == "found" and r.json()["card"]["affectations_courantes"]["vehicule"]["vehicle_id"] == _S["veh_a2"]  # à date
        r = _req("GET", "/fuel-cards/resolve", params={"last4": "1234"})
        assert r.json()["status"] == "ambiguous" and len(r.json()["candidates"]) == 2  # sans fournisseur : tous les last4
        r = _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Migrol", "last4": "0000"})
        assert r.json()["status"] == "not_found" and r.json()["candidates"] == []
        assert _req("GET", "/fuel-cards/resolve", params={"last4": "12"}).status_code == 422
        assert _req("GET", "/fuel-cards/resolve", params={"last4": "1234", "date": "x"}).status_code == 422
        assert _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Migrol", "last4": "1234"}, creds=ADMIN_B).json()["status"] == "not_found"
        assert _req("GET", "/fuel-cards/resolve", params={"fournisseur": "Shell", "last4": "9876"}, creds=RO_A).json()["status"] == "found"
        after = {"cards": _mongo().fuel_cards.count_documents({}), "asg": _mongo().fuel_card_assignments.count_documents({}),
                 "audit": _mongo().audit_logs.count_documents({}), "ftx": _mongo().fuel_transactions.count_documents({})}
        assert before == after  # aucune écriture provoquée par resolve
        assert _mongo().fuel_transactions.count_documents({"card_id": {"$exists": True}}) == 0

    def test_20_read_only_lecture_200_mutations_403(self):
        cid = _S["c1"]
        for path in ("/fuel-cards", f"/fuel-cards/{cid}", f"/fuel-cards/{cid}/assignments", f"/fuel-cards/{cid}/history", "/deadlines"):
            assert _req("GET", path, creds=RO_A).status_code == 200, path
        assert "ip" not in _req("GET", f"/fuel-cards/{cid}/history", creds=RO_A).json()[0] and "ip" in _req("GET", f"/fuel-cards/{cid}/history").json()[0]
        assert _card(creds=RO_A, last4="7777").status_code == 403
        assert _req("PATCH", f"/fuel-cards/{cid}", {"notes": "ro"}, creds=RO_A).status_code == 403
        assert _req("POST", f"/fuel-cards/{cid}/status", {"statut": "bloquee", "motif": "ro"}, creds=RO_A).status_code == 403
        assert _req("POST", f"/fuel-cards/{cid}/archive", {"motif": "ro"}, creds=RO_A).status_code == 403
        assert _req("POST", f"/fuel-cards/{cid}/restore", {}, creds=RO_A).status_code == 403
        assert _assign(cid, vehicle_id=_S["veh_a"], creds=RO_A).status_code == 403
        assert _req("POST", f"/fuel-card-assignments/{_S['asg_v2']}/close", {}, creds=RO_A).status_code == 403
        assert _db("fuel_cards", id=cid)["statut"] == "active" and _db("fuel_card_assignments", id=_S["asg_v2"])["valid_to"] is None

    def test_21_historique_complet_carte(self):
        rows = _req("GET", f"/fuel-cards/{_S['c1']}/history").json()
        actions = [r["action"] for r in rows]
        assert actions[0] == "create" and actions.count("status") == 5 and "replace" in actions and "close" in actions
        assert sum(1 for r in rows if r["entity"] == "fuel_card_assignment" and r["action"] == "create") == 4
        assert rows == sorted(rows, key=lambda r: r["created_at"]) and all(r["user"] == ADMIN_A[0] for r in rows)
        assert any("remplacee (Remplacée) → active (Active)" in r["detail"] for r in rows)
        assert _req("GET", f"/fuel-cards/{_S['c1']}/history", creds=ADMIN_B).status_code == 404

    def test_22_aucun_effet_fuel_transactions_couts_amendes_lots_a_d(self):
        snap = _snapshot()
        assert snap["ftx"] == _S["snap"]["ftx"] and snap["docs"] == _S["snap"]["docs"]
        assert snap["costs_a"]["items"] == _S["snap"]["costs_a"]["items"] and snap["fines_a"] == _S["snap"]["fines_a"] == 0
        assert snap["energy_a"] == _S["snap"]["energy_a"]
        assert _mongo().fuel_transactions.count_documents({"tenant_id": TENANT_A}) == 0
        assert _mongo().documents.count_documents({"tenant_id": TENANT_A}) == 0
        src = open("/app/backend/server.py", encoding="utf-8").read()
        block = src[src.index("# Phase 4C — Lot E"):src.index("# Inspections (état des lieux)")]
        assert "fuel_transactions" not in block and "CARD_VEHICLE_MISMATCH" not in src and "CARD_INACTIVE" not in src
        import sys
        sys.path.insert(0, "/app/backend")
        import fuel_cards as fcm
        assert "fingerprint" not in fcm.CARD_FIELDS and "fingerprint" in fcm.FORBIDDEN_KEYS and fcm.STATUSES == tuple(STATUSES)
        for word in ("import csv", "openpyxl", "def _upsert_fuel_transaction", "import_job"):
            assert word not in block.lower(), word
        # Lots A-D intacts : échéances documentaires, amendes, conducteurs répondent et aucune collection touchée hors Lot E
        assert _req("GET", "/fines/stats").status_code == 200 and _req("GET", "/drivers").status_code == 200
        touched = {c for c in _mongo().list_collection_names() if _mongo()[c].count_documents({"tenant_id": TENANT_A})}
        assert touched <= {"users", "vehicles", "drivers", "fuel_cards", "fuel_card_assignments", "audit_logs", "alerts"}, touched
