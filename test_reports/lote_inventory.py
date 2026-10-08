"""Lot E — clôture : preuves READ-ONLY (resolve, RBAC read_only) + inventaire exact du tenant `lote-ui-test`
+ isolation des autres tenants. Aucune écriture applicative : seules des requêtes GET / mutations refusées (403)."""
import asyncio
import hashlib
import json
import os
import sys

import requests
from dotenv import load_dotenv
from motor.motor_asyncio import AsyncIOMotorClient

load_dotenv("/app/backend/.env")
API = [l.split("=", 1)[1].strip() for l in open("/app/frontend/.env") if l.startswith("REACT_APP_BACKEND_URL=")][0] + "/api"
TENANT = "lote-ui-test"
ADMIN = ("lote-admin@lote-ui-test.ch", sys.argv[1])
RO = ("lote-ro@lote-ui-test.ch", sys.argv[2])
SNAP_COLLS = ("fuel_cards", "fuel_card_assignments", "fuel_transactions", "audit_logs", "alerts", "vehicles", "drivers",
              "users", "documents", "driver_assignments", "tenant_settings")
INV_COLLS = ("tenants", "users", "vehicles", "drivers", "driver_assignments", "fuel_cards", "fuel_card_assignments",
             "audit_logs", "alerts", "documents", "fuel_transactions", "files", "inspections", "tenant_settings",
             "tenant_integrations", "legacy_vehicle_map", "legacy_tenant_map", "vehicles_archive", "document_transfers",
             "vehicle_field_meta", "doc_categories", "doc_requirements", "fuel_snapshots")

db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]


def login(creds):
    r = requests.post(f"{API}/auth/login", json={"email": creds[0], "password": creds[1]}, timeout=30)
    r.raise_for_status()
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def snapshot():
    out = {}
    for c in SNAP_COLLS:
        rows = await db[c].find({}, {"_id": 0}).to_list(None)
        rows.sort(key=lambda r: json.dumps(r, sort_keys=True, default=str))
        out[c] = (len(rows), hashlib.sha256(json.dumps(rows, sort_keys=True, default=str).encode()).hexdigest()[:16])
    return out


def diff(a, b):
    return {c: (a[c], b[c]) for c in a if a[c] != b[c]}


def req(method, path, headers, **kw):
    r = requests.request(method, f"{API}{path}", headers=headers, timeout=30, **kw)
    try:
        body = r.json()
    except ValueError:
        body = r.text
    return r.status_code, body


async def main():
    print("=" * 100)
    print("A. PREUVE `GET /api/fuel-cards/resolve` = LECTURE SEULE")
    print("=" * 100)
    s0 = await snapshot()
    adm = login(ADMIN)
    for params in ({"fournisseur": "Shell", "last4": "5678"}, {"last4": "9012"}, {"fournisseur": "Agrola", "last4": "4242"},
                   {"last4": "0000"}, {"fournisseur": "Shell", "last4": "5678", "date": "2026-01-15"}, {"last4": "12"}):
        code, body = req("GET", "/fuel-cards/resolve", adm, params=params)
        if code == 200:
            print(f"  {params} -> HTTP {code} status={body['status']} candidates={len(body['candidates'])} written={body['written']}"
                  + (f" card={body['card']['label']} utilisable={body['card']['utilisable']}" if body.get("card") else "")
                  + (" | " + " ; ".join(f"{c['label']} [{c['id'][:8]}] {c['statut']}/{c['expiration_state']}" for c in body["candidates"])
                     if body["status"] == "ambiguous" else ""))
        else:
            print(f"  {params} -> HTTP {code} {body.get('detail') if isinstance(body, dict) else body}")
    s1 = await snapshot()
    d = diff(s0, s1)
    print(f"  Snapshot DB avant/après resolve ({len(SNAP_COLLS)} collections, count+sha256) : {'IDENTIQUE' if not d else 'DIFFÉRENT ' + str(d)}")
    print(f"  fuel_transactions avec champ card_id (toute la base) : {await db.fuel_transactions.count_documents({'card_id': {'$exists': True}})}")
    print(f"  RESOLVE READ-ONLY = {'PASS' if not d else 'FAIL'}")

    print("\n" + "=" * 100)
    print("B. PREUVE RBAC read_only — 8 mutations Lot E refusées côté serveur")
    print("=" * 100)
    ro = login(RO)
    code, me = req("GET", "/auth/me", ro)
    print(f"  compte : role={me.get('role')} tenant={me.get('tenant_id')}")
    code, lst = req("GET", "/fuel-cards", ro, params={"archived": "all"})
    print(f"  GET /fuel-cards (read_only) -> HTTP {code} items={lst.get('total')}")
    cards = lst["items"]
    live = next(c for c in cards if not c["is_deleted"])
    archived = next(c for c in cards if c["is_deleted"])
    code, det = req("GET", f"/fuel-cards/{live['id']}", ro)
    open_a = next((a for a in det["assignments"] if a["valid_to"] is None), None) or det["assignments"][0]
    veh = (await db.vehicles.find_one({"tenant_id": TENANT}, {"_id": 0, "id": 1}))["id"]
    s2 = await snapshot()
    checks = [
        ("création carte", "POST", "/fuel-cards", {"fournisseur": "RO", "last4": "0001"}),
        ("modification carte", "PATCH", f"/fuel-cards/{live['id']}", {"notes": "ro"}),
        ("changement statut", "POST", f"/fuel-cards/{live['id']}/status", {"statut": "suspendue", "motif": "test ro"}),
        ("archivage", "POST", f"/fuel-cards/{live['id']}/archive", {"motif": "test ro"}),
        ("restauration", "POST", f"/fuel-cards/{archived['id']}/restore", {"motif": "test ro"}),
        ("création affectation", "POST", f"/fuel-cards/{live['id']}/assignments", {"type": "vehicule", "vehicle_id": veh, "valid_from": "2026-06-01"}),
        ("remplacement affectation", "POST", f"/fuel-cards/{live['id']}/assignments", {"type": "vehicule", "vehicle_id": veh, "valid_from": "2026-06-01", "replace": True, "motif": "test ro"}),
        ("clôture affectation", "POST", f"/fuel-card-assignments/{open_a['id']}/close", {"motif": "test ro"}),
    ]
    ok = True
    for label, m, p, body in checks:
        code, resp = req(m, p, ro, json=body)
        ok &= code == 403
        print(f"  {label:26s} {m:5s} {p:60s} -> HTTP {code} {'PASS' if code == 403 else 'FAIL'} ({resp.get('detail') if isinstance(resp, dict) else resp})")
    s3 = await snapshot()
    d = diff(s2, s3)
    print(f"  Snapshot DB avant/après tentatives read_only : {'IDENTIQUE' if not d else 'DIFFÉRENT ' + str(d)}")
    print(f"  RBAC READ_ONLY = {'PASS' if ok and not d else 'FAIL'}")

    print("\n" + "=" * 100)
    print(f"C. INVENTAIRE TENANT `{TENANT}`")
    print("=" * 100)
    for c in INV_COLLS:
        key = "id" if c == "tenants" else "tenant_id"
        n = await db[c].count_documents({key: TENANT})
        print(f"  {c:24s} {n}")
    print("\n  -- users --")
    for u in await db.users.find({"tenant_id": TENANT}, {"_id": 0, "id": 1, "email": 1, "role": 1, "disabled": 1}).to_list(None):
        print(f"    {u['id']} {u['email']} role={u['role']} disabled={u.get('disabled')}")
    print("  -- vehicles --")
    for v in await db.vehicles.find({"tenant_id": TENANT}, {"_id": 0, "id": 1, "plaque": 1, "marque": 1, "modele": 1}).to_list(None):
        print(f"    {v['id']} {v.get('plaque')} {v.get('marque')} {v.get('modele')}")
    print("  -- drivers --")
    for dr in await db.drivers.find({"tenant_id": TENANT}, {"_id": 0, "id": 1, "nom": 1, "prenom": 1, "matricule_interne": 1, "actif": 1, "is_deleted": 1}).to_list(None):
        print(f"    {dr['id']} {dr.get('prenom')} {dr.get('nom')} [{dr.get('matricule_interne')}] actif={dr.get('actif')} is_deleted={dr.get('is_deleted')}")
    print("  -- fuel_cards (via API admin, archived=all : expiration_state/utilisable dérivés) --")
    code, lst = req("GET", "/fuel-cards", adm, params={"archived": "all"})
    for c in sorted(lst["items"], key=lambda c: (c["fournisseur"], c["last4"], c["id"])):
        print(f"    {c['id']} | {c['fournisseur']:8s} last4={c['last4']} | statut={c['statut']:9s} | expire_le={c.get('expire_le') or '—':10s} "
              f"| expiration_state={c['expiration_state']:9s} | utilisable={str(c['utilisable']):5s} | is_deleted={c['is_deleted']} "
              f"| type={c.get('type_affectation')} | source={c.get('source')} | created_by={c.get('created_by')}")
    print("  -- fuel_card_assignments --")
    for a in await db.fuel_card_assignments.find({"tenant_id": TENANT}, {"_id": 0}).sort([("card_id", 1), ("valid_from", 1)]).to_list(None):
        print(f"    {a['id']} | card={a['card_id'][:8]} | type={a['type']:10s} | vehicle_id={(a.get('vehicle_id') or '—')[:8]:8s} "
              f"| driver_id={(a.get('driver_id') or '—')[:8]:8s} | valid_from={a.get('valid_from') or 'null':10s} | valid_to={a.get('valid_to') or 'null':10s} "
              f"| {'OUVERTE' if a.get('valid_to') is None else 'FERMÉE'} | replaced={a.get('replaced')} | source={a.get('source')} | created_by={a.get('created_by')}")
    print("  -- audit_logs --")
    q_cards = {"tenant_id": TENANT, "entity": {"$in": ["fuel_card", "fuel_card_assignment"]}}
    print(f"    total tenant : {await db.audit_logs.count_documents({'tenant_id': TENANT})}")
    print(f"    liés cartes/affectations : {await db.audit_logs.count_documents(q_cards)}")
    pipe = [{"$match": q_cards}, {"$group": {"_id": {"e": "$entity", "a": "$action"}, "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]
    for g in await db.audit_logs.aggregate(pipe).to_list(None):
        print(f"      {g['_id']['e']:22s} {g['_id']['a']:14s} {g['n']}")
    other = await db.audit_logs.aggregate([{"$match": {"tenant_id": TENANT, "entity": {"$nin": ["fuel_card", "fuel_card_assignment"]}}},
                                           {"$group": {"_id": {"e": "$entity", "a": "$action"}, "n": {"$sum": 1}}}, {"$sort": {"_id": 1}}]).to_list(None)
    print("    autres entités : " + ", ".join(f"{g['_id']['e']}/{g['_id']['a']}={g['n']}" for g in other))
    print(f"  -- alerts : {await db.alerts.count_documents({'tenant_id': TENANT})}")

    print("\n" + "=" * 100)
    print("D. ISOLATION — counts par tenant (tous les tenants connus + tout tenant_id présent dans les 2 collections Lot E)")
    print("=" * 100)
    tenants = {t["id"] for t in await db.tenants.find({}, {"_id": 0, "id": 1}).to_list(None)}
    tenants |= set(await db.fuel_cards.distinct("tenant_id")) | set(await db.fuel_card_assignments.distinct("tenant_id"))
    tenants |= set(await db.audit_logs.distinct("tenant_id", {"entity": {"$in": ["fuel_card", "fuel_card_assignment"]}}))
    print(f"  {'tenant_id':24s} {'fuel_cards':>10s} {'fc_assign':>10s} {'audit_fc':>9s} {'alerts':>7s} {'fuel_tx':>8s} {'tx.card_id':>10s}")
    for t in sorted(tenants, key=lambda x: (x != "default", x != TENANT, str(x))):
        fcn = await db.fuel_cards.count_documents({"tenant_id": t})
        fan = await db.fuel_card_assignments.count_documents({"tenant_id": t})
        aun = await db.audit_logs.count_documents({"tenant_id": t, "entity": {"$in": ["fuel_card", "fuel_card_assignment"]}})
        aln = await db.alerts.count_documents({"tenant_id": t})
        txn = await db.fuel_transactions.count_documents({"tenant_id": t})
        txc = await db.fuel_transactions.count_documents({"tenant_id": t, "card_id": {"$exists": True}})
        print(f"  {str(t):24s} {fcn:10d} {fan:10d} {aun:9d} {aln:7d} {txn:8d} {txc:10d}")
    print(f"  fuel_cards sans tenant_id : {await db.fuel_cards.count_documents({'tenant_id': {'$exists': False}})}"
          f" · fuel_card_assignments sans tenant_id : {await db.fuel_card_assignments.count_documents({'tenant_id': {'$exists': False}})}")
    print(f"  TOTAL fuel_cards={await db.fuel_cards.count_documents({})} fuel_card_assignments={await db.fuel_card_assignments.count_documents({})}"
          f" fuel_transactions={await db.fuel_transactions.count_documents({})}")
    polluted = [t for t in sorted(tenants, key=str) if t != TENANT
                and (await db.fuel_cards.count_documents({"tenant_id": t}) or await db.fuel_card_assignments.count_documents({"tenant_id": t}))]
    print(f"  tenants hors `{TENANT}` avec données Lot E : {polluted}")
    print(f"  TENANT ISOLATION = {'PASS' if not polluted else 'FAIL'}")
    print("  -- baselines historiques `default` (lecture seule) --")
    mig = await db.fuel_transactions.find_one({"tenant_id": "default", "montant": 74.17}, {"_id": 0, "fournisseur": 1, "montant": 1, "card_id": 1})
    print(f"    transaction Migrol 74.17 : {mig}")
    print(f"    facture démo 510.77 : {await db.documents.count_documents({'tenant_id': 'default', 'montant': 510.77, 'is_deleted': False})} document(s)")
    print(f"    amende démo 120 : {await db.documents.count_documents({'tenant_id': 'default', 'montant': 120, 'is_deleted': False})} document(s)")


asyncio.run(main())
