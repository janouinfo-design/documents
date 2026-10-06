"""Preuve métier Phase 2 (preview) : ré-analyse réelle du ticket Migrol + validation CARBURANT + anti double comptage."""
import sys
import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
VEH = "6d00f932-d74d-4e1b-84ad-6116ffb0af33"
DOC = "94da14e8-2c37-4a59-9446-64cfad4ded92"

r = requests.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}, timeout=30)
r.raise_for_status()
H = {"Authorization": f"Bearer {r.json()['token']}"}


def costs():
    d = requests.get(f"{BASE}/api/costs", params={"vehicle_id": VEH}, headers=H, timeout=30).json()
    items = [i for i in d["items"] if i["vehicle_id"] == VEH]
    return items, round(sum(i["cout_annuel"] for i in items), 2)


step = sys.argv[1] if len(sys.argv) > 1 else "scan"
if step == "scan":
    items, total = costs()
    print("COSTS BEFORE: n =", len(items), "total =", total)
    for i in items:
        print("  ", i["key"][:16], i["category"], i["montant"], i["frequence"])
    r = requests.post(f"{BASE}/api/vehicles/{VEH}/documents/scan", headers=H, data={"document_id": DOC}, timeout=180)
    print("SCAN HTTP", r.status_code)
    d = r.json()
    print("type =", d.get("document_type"), d.get("type_confidence"), "| detected =", d.get("detected_type"),
          "| mismatch =", d.get("type_mismatch"))
    print("suggested_business_category =", d.get("suggested_business_category"))
    print("coherence_warnings =", d.get("coherence_warnings"))
    print("missing_fields =", d.get("missing_fields"))
    for f in d.get("fields", []):
        print(f"   {f['field']:16} = {f['value']!r:28} conf={f.get('confidence')} status={f.get('status')}")
elif step == "validate":
    items, before = costs()
    ext = requests.get(f"{BASE}/api/documents/{DOC}/extraction", headers=H, timeout=30).json()
    fields = {f["field"]: f["value"] for f in ext["fields"] if f["value"] not in (None, "")}
    print("fields envoyés (review humaine, valeurs OCR non modifiées):", fields)
    r = requests.post(f"{BASE}/api/documents/{DOC}/validate", headers=H, timeout=60,
                      json={"document_type": "ticket_carburant", "fields": fields, "business_category": "CARBURANT"})
    print("VALIDATE HTTP", r.status_code)
    res = r.json()
    print("warnings =", res.get("warnings"))
    print("cost =", res.get("cost"))
    print("fuel_transaction =", {k: res["fuel_transaction"].get(k) for k in
                                 ("id", "station", "date", "heure", "montant", "devise", "litres", "prix_litre",
                                  "type_carburant", "kilometrage", "carte_last4", "energie", "source_document_id")}
          if res.get("fuel_transaction") else None)
    print("conso_update =", res.get("conso_update"))
    items, after = costs()
    hits = [i for i in items if i["document_id"] == DOC]
    print(f"COSTS AFTER: n = {len(items)} total = {after} | delta = {round(after - before, 2)} | items for doc = {len(hits)}")
    en = requests.get(f"{BASE}/api/energy", headers=H, timeout=30).json()
    tx = [t for t in en["transactions"] if t["source_document_id"] == DOC]
    print("ENERGY page: transactions for doc =", len(tx), "| totals =", en["totals"])
    ve = requests.get(f"{BASE}/api/vehicles/{VEH}/energy", headers=H, timeout=30).json()
    print("ENERGY tab: transactions =", ve["totals"]["transactions"], "| derniere =", ve["totals"]["derniere"],
          "| conso_tickets =", ve["conso_tickets"], "| source fiche =", ve["conso_reelle_source"])
    print("DELETE source doc →", requests.delete(f"{BASE}/api/documents/{DOC}", headers=H, timeout=30).status_code)
