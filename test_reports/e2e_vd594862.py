"""E2E RÉEL — VD 594 862 : upload simple -> analyse réelle -> review -> confirmation -> persistence -> réouverture -> ré-analyse."""
import json
import sys

import requests
from dotenv import dotenv_values

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
S = requests.Session()

r = S.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}, timeout=30)
r.raise_for_status()
S.headers["Authorization"] = f"Bearer {r.json()['token']}"

step = sys.argv[1]

if step == "setup":
    # Véhicule VD 594 862 — créé VIDE (aucune valeur de référence injectée)
    r = S.get(f"{BASE}/api/vehicles", timeout=30)
    existing = [v for v in r.json() if v.get("plaque") == "VD 594 862"]
    if existing:
        vid = existing[0]["id"]
    else:
        r = S.post(f"{BASE}/api/vehicles", json={"plaque": "VD 594 862"}, timeout=30)
        r.raise_for_status()
        vid = r.json()["id"]
    print("VEHICLE_ID:", vid)
    # Upload simple (sans analyse) dans le dossier Carte grise
    with open("/app/test_reports/594862.jpeg", "rb") as f:
        r = S.post(f"{BASE}/api/vehicles/{vid}/documents",
                   files={"file": ("594862.jpeg", f, "image/jpeg")},
                   data={"folder": "Carte grise"}, timeout=120)
    r.raise_for_status()
    doc = r.json()
    print("DOC_ID:", doc["id"])
    print("extraction_status apres upload simple:", doc.get("extraction_status"))
    r = S.get(f"{BASE}/api/documents/{doc['id']}/extraction", timeout=30)
    print("GET extraction avant analyse ->", r.status_code, "(attendu 404)")

elif step == "analyze":
    vid, doc_id = sys.argv[2], sys.argv[3]
    r = S.post(f"{BASE}/api/vehicles/{vid}/documents/scan",
               data={"document_id": doc_id, "document_type": "permis_circulation"}, timeout=180)
    print("scan status:", r.status_code)
    res = r.json()
    print("extraction_status:", res.get("extraction_status"), "| type:", res.get("document_type"),
          "| type_confidence:", res.get("type_confidence"), "| champs:", len(res.get("fields") or []))
    print(json.dumps(res.get("fields"), ensure_ascii=False, indent=1))
    if res.get("missing_fields"):
        print("MISSING:", res["missing_fields"])

elif step == "validate":
    doc_id = sys.argv[2]
    r = S.get(f"{BASE}/api/documents/{doc_id}/extraction", timeout=30)
    data = r.json()
    fields = {}
    for f in data["fields"]:
        if f.get("reason") == "VIN_BELONGS_TO_ANOTHER_VEHICLE":
            continue
        fields[f["field"]] = f["value"]
    # Simulation de la CORRECTION HUMAINE dans la review : le moteur a lu le VIN
    # en "uncertain" (WWW...) — l'utilisateur corrige manuellement d'après le document.
    if len(sys.argv) > 3:
        fields["vin"] = sys.argv[3]
    r = S.post(f"{BASE}/api/documents/{doc_id}/validate",
               json={"document_type": data["document_type"], "fields": fields}, timeout=60)
    print("validate:", r.status_code, "| applied:", r.json().get("applied"),
          "| skipped:", r.json().get("skipped_fields"))

elif step == "check":
    vid, doc_id = sys.argv[2], sys.argv[3]
    v = S.get(f"{BASE}/api/vehicles/{vid}", timeout=30).json()
    cg = v.get("carte_grise") or {}
    out = {"plaque": v.get("plaque"), "vin": v.get("vin"), "marque": v.get("marque"),
           "modele": v.get("modele"), "categorie": v.get("categorie"),
           "cylindree_cm3": v.get("cylindree_cm3"), "puissance_kw": v.get("puissance_kw"),
           "poids_vide": v.get("poids_vide"), "type_carburant": v.get("type_carburant"),
           "numero_homologation": v.get("numero_homologation"),
           "carte_grise": {k: cg.get(k) for k in ("numero_matricule", "carrosserie", "couleur",
                           "nombre_places", "charge_utile", "poids_total", "charge_remorquable",
                           "charge_toit", "code_emissions", "detenteur", "adresse_detenteur",
                           "date_emission", "lieu_emission", "date_mise_circulation")},
           "assurance.compagnie": (v.get("assurance") or {}).get("compagnie"),
           "controle_technique.date_dernier": (v.get("controle_technique") or {}).get("date_dernier")}
    print(json.dumps(out, ensure_ascii=False, indent=1))
    r = S.get(f"{BASE}/api/documents/{doc_id}/extraction", timeout=30)
    d = r.json()
    states = {}
    for f in d["fields"]:
        st = ("CONFLIT" if f["conflict"] else
              "CORRESPONDANCE" if f["current_value"] is not None else
              "INCERTAIN" if f["status"] == "uncertain" else "COMPLETER")
        states[f["field"]] = st
    print("REVIEW REOUVERTE (etats):", json.dumps(states, ensure_ascii=False))
    print("statut document:", d["extraction_status"])

elif step == "idempotence":
    vid, doc_id = sys.argv[2], sys.argv[3]
    before_docs = S.get(f"{BASE}/api/vehicles/{vid}/documents", timeout=30).json()
    before_vehicles = len(S.get(f"{BASE}/api/vehicles", timeout=30).json())
    r = S.post(f"{BASE}/api/vehicles/{vid}/documents/scan",
               data={"document_id": doc_id, "document_type": "permis_circulation"}, timeout=180)
    res = r.json()
    after_docs = S.get(f"{BASE}/api/vehicles/{vid}/documents", timeout=30).json()
    after_vehicles = len(S.get(f"{BASE}/api/vehicles", timeout=30).json())
    print("re-analyse:", r.status_code, res.get("extraction_status"), "| meme doc:", res.get("document_id") == doc_id)
    print("docs avant/apres:", len(before_docs), "/", len(after_docs), "| vehicules avant/apres:", before_vehicles, "/", after_vehicles)
    v = S.get(f"{BASE}/api/vehicles/{vid}", timeout=30).json()
    print("assurance.compagnie inchangee:", (v.get("assurance") or {}).get("compagnie"))
    print("controle.date_dernier inchangee:", (v.get("controle_technique") or {}).get("date_dernier"))
    print("vin inchange:", v.get("vin"))
