"""Tenant démo commercial `demo-logitrak` (« Démo LogiTrak ») — jeu de données réaliste et cohérent.

Toutes les écritures passent par l'API du compte admin de CE tenant (règles métier + isolation garanties) ;
la seule écriture DB directe est le MARQUAGE (`demo_seed`/version/group), strictement filtré `tenant_id="demo-logitrak"`.
`default` et les autres tenants ne sont JAMAIS touchés (guard + fingerprint avant/après).

Comptes : admin@demo-logitrak.ch (admin) · driver@demo-logitrak.ch (driver, lié à un conducteur actif) ·
readonly@demo-logitrak.ch (read_only). Mots de passe : générés, persistés UNIQUEMENT dans
`/app/memory/demo_logitrak_credentials.json` (gitignored) + section dédiée de `/app/memory/test_credentials.md`.
Jamais affichés en clair dans stdout ni dans le rapport.

Usage : python3 test_reports/demo_logitrak_seed.py [baseline|seed|mark|verify|inventory|report|all]
"""
import hashlib
import io
import json
import os
import secrets
import sys
from datetime import date, timedelta
from pathlib import Path

import requests
from dotenv import dotenv_values
from pymongo import MongoClient

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
T = "demo-logitrak"
TENANT_NAME = "Démo LogiTrak"
MARKERS = {"demo_seed": True, "demo_seed_version": "2026-10", "demo_seed_group": "commercial-demo"}
MARK_COLLECTIONS = ("users", "vehicles", "drivers", "driver_assignments", "fuel_cards",
                    "fuel_card_assignments", "fuel_transactions", "documents", "inspections",
                    "fuel_anomalies", "tenant_settings", "doc_categories", "doc_requirements")

REP = Path("/app/test_reports")
MEM = Path("/app/memory")
BASELINE = REP / "demo_logitrak_baseline.json"
RESULT = REP / "demo_logitrak_result.json"
INVENTORY = REP / "demo_logitrak_inventory.json"
VERIFY_OUT = REP / "demo_logitrak_verify.json"
REPORT = REP / "demo_logitrak_report.md"
CREDS = MEM / "demo_logitrak_credentials.json"
TESTCREDS = MEM / "test_credentials.md"

ACCOUNTS = {"ADMIN": ("admin@demo-logitrak.ch", "admin", "Administration Démo"),
            "DRIVER": ("driver@demo-logitrak.ch", "driver", "Marc Rochat"),
            "READONLY": ("readonly@demo-logitrak.ch", "read_only", "Consultation Démo")}

db = MongoClient(ENV["MONGO_URL"])[ENV["DB_NAME"]]
TODAY = date.today()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()  # noqa: E731
PASS, FAIL = "PASS", "FAIL"
VOLATILE = {"vehicles": ("updated_at", "kilometrage", "conso_moyenne_l_100km", "conso_source", "conso_updated_at",
                         "conso_reelle_l_100km", "conso_reelle_source")}
PNG = (b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
       b"\x00\x00\x00\rIDATx\x9cc\xf8\xff\xff?\x00\x05\xfe\x02\xfe\xa7V\xbd\xfa\x00\x00\x00\x00IEND\xaeB`\x82")
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF")


def die(msg):
    print(f"FAIL-FAST : {msg}")
    sys.exit(2)


def guard(tenant):
    if tenant != T:
        die(f"écriture hors tenant cible refusée ({tenant})")


def login(email, pwd):
    r = requests.post(f"{BASE}/api/auth/login", json={"email": email, "password": pwd}, timeout=30)
    if r.status_code != 200:
        die(f"login {email} → {r.status_code} {r.text[:200]}")
    return {"Authorization": f"Bearer {r.json()['token']}"}


def sa_headers():
    return login(ENV["SUPERADMIN_EMAIL"], ENV["SUPERADMIN_PASSWORD"])


def api(h, method, path, body=None, **kw):
    return requests.request(method, f"{BASE}/api{path}", json=body, headers=h, timeout=120, **kw)


def ok(r, *codes):
    if r.status_code not in (codes or (200,)):
        die(f"{r.request.method} {r.url} → {r.status_code} {r.text[:300]}")
    return r.json() if r.content else None


def load_result():
    return json.loads(RESULT.read_text()) if RESULT.exists() else {"tenant": T, "ids": {}, "notes": []}


def save_result(res):
    RESULT.write_text(json.dumps(res, indent=1, ensure_ascii=False, default=str))


# --- credentials -----------------------------------------------------------------------------------------------------
def load_or_make_passwords():
    if CREDS.exists():
        return json.loads(CREDS.read_text())
    pw = {k: (os.environ.get(f"DEMO_PW_{k}") or f"Demo-{secrets.token_urlsafe(9)}") for k in ACCOUNTS}
    CREDS.write_text(json.dumps(pw, indent=1))
    return pw


def write_test_credentials(pw):
    block = [
        "<!-- DEMO_LOGITRAK_START -->",
        f"## 6. Tenant démo commercial `demo-logitrak` (« {TENANT_NAME} »)",
        "> Fichier gitignored. Ces identifiants de DÉMONSTRATION sont volontairement consignés ici (exception "
        "explicite demandée par l'utilisateur) ; ne jamais les afficher dans un rapport ni les commiter.",
        "",
        "| Compte | Email | Mot de passe | Rôle |",
        "|---|---|---|---|",
    ]
    for k, (email, role, _) in ACCOUNTS.items():
        block.append(f"| {k.title()} | `{email}` | `{pw[k]}` | `{role}` |")
    block += [
        "",
        "- Tenant : `demo-logitrak`. Driver lié au conducteur actif « Marc Rochat » (affecté Tesla Model 3 GE 771 902).",
        "- Re-seed : `python3 test_reports/demo_logitrak_seed.py all` (mots de passe ré-appliqués via superadmin).",
        "<!-- DEMO_LOGITRAK_END -->",
    ]
    text = TESTCREDS.read_text() if TESTCREDS.exists() else "# Test credentials — LogiTrak (Documents)\n"
    start, end = "<!-- DEMO_LOGITRAK_START -->", "<!-- DEMO_LOGITRAK_END -->"
    if start in text and end in text:
        pre, rest = text.split(start, 1)
        _, post = rest.split(end, 1)
        text = pre + "\n".join(block) + post
    else:
        text = text.rstrip() + "\n\n" + "\n".join(block) + "\n"
    TESTCREDS.write_text(text)


# --- baseline / fingerprint (tous tenants SAUF T) --------------------------------------------------------------------
def fingerprint():
    fp = {"counts": {}, "hashes": {}}
    for c in sorted(x for x in db.list_collection_names() if not x.startswith("system.") and x != "login_attempts"):
        key = "id" if c == "tenants" else "tenant_id"
        for t in sorted(str(x) for x in db[c].distinct(key, {key: {"$ne": T}})):
            h, n = hashlib.sha256(), 0
            for d in db[c].find({key: t}, {"_id": 0}).sort("id", 1):
                n += 1
                d = {k: v for k, v in d.items() if k not in VOLATILE.get(c, ()) and not k.startswith("navixy_")}
                h.update(json.dumps(d, sort_keys=True, default=str).encode())
            fp["counts"][f"{c}|{t}"], fp["hashes"][f"{c}|{t}"] = n, h.hexdigest()
    fp["tenants_ids"] = sorted(t["id"] for t in db.tenants.find({"id": {"$ne": T}}, {"_id": 0, "id": 1}))
    return fp


def baseline():
    if BASELINE.exists():
        print("BASELINE déjà présente (conservée) :", BASELINE)
        return
    BASELINE.write_text(json.dumps(fingerprint(), indent=1))
    print("BASELINE écrite :", BASELINE)


# =====================================================================================================================
#  DONNÉES DÉMO
# =====================================================================================================================
def vehicle_specs():
    """10 véhicules : 4 thermiques · 3 électriques · 2 hybrides rechargeables · 1 utilitaire."""
    def leasing(soc, num, debut, fin, mens, duree):
        return {"societe": soc, "numero_contrat": num, "date_debut": debut, "date_fin": fin,
                "mensualite_chf": mens, "duree_mois": duree, "km_contractuel": 120000,
                "option_achat": False, "valeur_residuelle": round(mens * 11, -2), "cout_mensuel": mens,
                "cout_total": mens * duree, "commentaires": "Entretien inclus, pneus hiver fournis."}

    def ass(comp, pol, cov, prime, fr, ech):
        return {"compagnie": comp, "numero_police": pol, "type_couverture": cov, "prime_annuelle": prime,
                "franchise": fr, "assistance": True, "contact_sinistre": "+41 800 80 80 80",
                "date_debut": D(-365), "date_echeance": ech}

    def cg(circ, poids, places, couleur):
        return {"date_mise_circulation": circ, "poids_total": poids, "nombre_places": places, "couleur": couleur}

    def ct(dernier, prochain, centre):
        return {"date_dernier": dernier, "date_prochain": prochain, "centre": centre, "resultat": "Conforme"}

    return [
        # 1 — THERMIQUE diesel — SANS CONDUCTEUR (cas visible)
        {"key": "octavia", "payload": {
            "plaque": "GE 142 880", "marque": "Škoda", "modele": "Octavia Combi 2.0 TDI", "annee": 2021,
            "vin": "TMBJJ7NE1M0123456", "type_carburant": "Diesel", "cylindree_cm3": 1968, "puissance_kw": 110,
            "categorie": "Break", "poids_vide": 1480, "co2_g_km": 134, "conso_officielle_l_100km": 5.1,
            "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 50, "conso_reelle_l_100km": 5.8,
            "conso_reelle_source": "tickets", "kilometrage": 78450, "groupe": "Technique", "base": "Genève",
            "responsable": "Atelier GE", "tracker_gps": "LT-GPS-2101",
            "prochaine_maintenance": D(60), "prochaine_expertise": D(380),
            "leasing": leasing("Arval Suisse", "GE-LSG-2021-4471", D(-980), D(-170), 740, 48),
            "assurance": ass("AXA", "POL-784512", "Casco complète", 2140, 1000, D(165)),
            "carte_grise": cg(D(-1600), 1990, 5, "Gris Quartz"), "controle_technique": ct(D(-700), D(18), "OCV Genève")}},
        # 2 — THERMIQUE diesel
        {"key": "passat", "payload": {
            "plaque": "VD 391 204", "marque": "Volkswagen", "modele": "Passat Variant 2.0 TDI", "annee": 2022,
            "vin": "WVWZZZ3CZNE045789", "type_carburant": "Diesel", "cylindree_cm3": 1968, "puissance_kw": 110,
            "categorie": "Break", "poids_vide": 1520, "co2_g_km": 128, "conso_officielle_l_100km": 4.9,
            "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 66, "conso_reelle_l_100km": 5.4,
            "conso_reelle_source": "tickets", "kilometrage": 54300, "groupe": "Direction", "base": "Lausanne",
            "responsable": "Sophie Berger", "tracker_gps": "LT-GPS-2102",
            "prochaine_maintenance": D(120), "prochaine_expertise": D(520),
            "leasing": leasing("ALD Automotive", "VD-LSG-2022-1180", D(-700), D(240), 810, 48),
            "assurance": ass("Zurich Assurances", "POL-903221", "RC + Casco complète", 1980, 500, D(12)),
            "carte_grise": cg(D(-1300), 2010, 5, "Bleu Lapiz"), "controle_technique": ct(D(-400), D(330), "SAN Vaud")}},
        # 3 — THERMIQUE diesel — carte EXPIRÉE assignée + document CONTRÔLE expiré
        {"key": "bmw", "payload": {
            "plaque": "ZH 556 713", "marque": "BMW", "modele": "320d Touring", "annee": 2020,
            "vin": "WBA5E71080G234567", "type_carburant": "Diesel", "cylindree_cm3": 1995, "puissance_kw": 140,
            "categorie": "Break", "poids_vide": 1570, "co2_g_km": 142, "conso_officielle_l_100km": 5.4,
            "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 59, "conso_reelle_l_100km": 6.1,
            "conso_reelle_source": "tickets", "kilometrage": 96800, "groupe": "Commercial", "base": "Zürich",
            "responsable": "Daniel Keller", "tracker_gps": "LT-GPS-2103",
            "prochaine_maintenance": D(25), "prochaine_expertise": D(-10),
            "leasing": leasing("LeasePlan", "ZH-LSG-2020-3390", D(-1200), D(-60), 690, 48),
            "assurance": ass("La Mobilière", "POL-551204", "Casco partielle", 1620, 1000, D(210)),
            "carte_grise": cg(D(-1900), 1620, 5, "Noir Saphir"), "controle_technique": ct(D(-760), D(260), "StVA Zürich")}},
        # 4 — THERMIQUE essence
        {"key": "corolla", "payload": {
            "plaque": "BE 208 455", "marque": "Toyota", "modele": "Corolla 1.8", "annee": 2023,
            "vin": "SB1KYHE10PE098765", "type_carburant": "Essence", "cylindree_cm3": 1798, "puissance_kw": 103,
            "categorie": "Berline", "poids_vide": 1375, "co2_g_km": 119, "conso_officielle_l_100km": 5.2,
            "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 43, "conso_reelle_l_100km": 5.9,
            "conso_reelle_source": "tickets", "kilometrage": 31250, "groupe": "Pool", "base": "Berne",
            "responsable": "Pool Berne", "tracker_gps": "LT-GPS-2104",
            "prochaine_maintenance": D(200), "prochaine_expertise": D(600),
            "leasing": leasing("PostFinance Leasing", "BE-LSG-2023-7742", D(-300), D(620), 560, 48),
            "assurance": ass("Allianz Suisse", "POL-220417", "Casco complète", 1490, 500, D(300)),
            "carte_grise": cg(D(-600), 1800, 5, "Blanc Nacré"), "controle_technique": ct(D(-200), D(650), "Strassenverkehrsamt BE")}},
        # 5 — ÉLECTRIQUE — conducteur du compte driver (Marc Rochat), recharges + amende
        {"key": "tesla", "payload": {
            "plaque": "GE 771 902", "marque": "Tesla", "modele": "Model 3 Long Range", "annee": 2023,
            "vin": "5YJ3E7EB8PF345678", "type_carburant": "Électrique", "puissance_kw": 258,
            "categorie": "Berline", "poids_vide": 1844, "co2_g_km": 0, "batterie_capacite_brute_kwh": 82,
            "batterie_capacite_utile_kwh": 75, "conso_officielle_kwh_100km": 14.9, "autonomie_km": 491,
            "kilometrage": 41200, "groupe": "Direction", "base": "Genève", "responsable": "Marc Rochat",
            "tracker_gps": "LT-GPS-2105", "prochaine_maintenance": D(150), "prochaine_expertise": D(480),
            "leasing": leasing("AMAG Leasing", "GE-LSG-2023-9015", D(-250), D(680), 980, 48),
            "assurance": ass("Helvetia", "POL-771902", "Casco complète", 2360, 1000, D(240)),
            "carte_grise": cg(D(-500), 2200, 5, "Blanc Perle"), "controle_technique": ct(D(-120), D(620), "OCV Genève")}},
        # 6 — ÉLECTRIQUE — Camille Favre, recharges
        {"key": "megane", "payload": {
            "plaque": "VD 640 118", "marque": "Renault", "modele": "Mégane E-Tech EV60", "annee": 2024,
            "vin": "VF1RFB00X70567890", "type_carburant": "Électrique", "puissance_kw": 160,
            "categorie": "Compacte", "poids_vide": 1711, "co2_g_km": 0, "batterie_capacite_brute_kwh": 60,
            "batterie_capacite_utile_kwh": 60, "conso_officielle_kwh_100km": 16.1, "autonomie_km": 450,
            "kilometrage": 18600, "groupe": "Commercial", "base": "Lausanne", "responsable": "Camille Favre",
            "tracker_gps": "LT-GPS-2106", "prochaine_maintenance": D(260), "prochaine_expertise": D(700),
            "leasing": leasing("Arval Suisse", "VD-LSG-2024-2203", D(-120), D(810), 720, 48),
            "assurance": ass("Vaudoise", "POL-640118", "Casco complète", 1890, 500, D(280)),
            "carte_grise": cg(D(-150), 2140, 5, "Gris Schiste"), "controle_technique": ct(None, D(820), "SAN Vaud")}},
        # 7 — ÉLECTRIQUE — SANS CONDUCTEUR + aucun document (document requis manquant)
        {"key": "ioniq", "payload": {
            "plaque": "ZH 884 326", "marque": "Hyundai", "modele": "Ioniq 5 77 kWh", "annee": 2023,
            "vin": "KMHL341GFPA678901", "type_carburant": "Électrique", "puissance_kw": 168,
            "categorie": "SUV", "poids_vide": 2020, "co2_g_km": 0, "batterie_capacite_brute_kwh": 77.4,
            "batterie_capacite_utile_kwh": 74, "conso_officielle_kwh_100km": 16.7, "autonomie_km": 507,
            "kilometrage": 27400, "groupe": "Pool", "base": "Zürich", "responsable": "Pool Zürich",
            "tracker_gps": "LT-GPS-2107", "prochaine_maintenance": D(90), "prochaine_expertise": D(560),
            "leasing": leasing("LeasePlan", "ZH-LSG-2023-5521", D(-400), D(560), 860, 48),
            "assurance": ass("AXA", "POL-884326", "Casco complète", 2180, 1000, D(190)),
            "carte_grise": cg(D(-430), 2320, 5, "Gris Cyber"), "controle_technique": ct(D(-120), D(600), "StVA Zürich")}},
        # 8 — HYBRIDE RECHARGEABLE (PHEV) — Luca Moretti
        {"key": "xc60", "payload": {
            "plaque": "VD 512 667", "marque": "Volvo", "modele": "XC60 T6 Recharge", "annee": 2022,
            "vin": "YV1UZK5V9N1789012", "type_carburant": "Hybride rechargeable", "cylindree_cm3": 1969,
            "puissance_kw": 257, "categorie": "SUV", "poids_vide": 2070, "co2_g_km": 55,
            "conso_officielle_l_100km": 2.4, "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 60,
            "batterie_capacite_brute_kwh": 18.8, "batterie_capacite_utile_kwh": 14.9,
            "conso_officielle_kwh_100km": 21.0, "autonomie_km": 77, "conso_reelle_l_100km": 3.1,
            "conso_reelle_source": "tickets", "kilometrage": 62100, "groupe": "Technique", "base": "Lausanne",
            "responsable": "Luca Moretti", "tracker_gps": "LT-GPS-2108",
            "prochaine_maintenance": D(40), "prochaine_expertise": D(450),
            "leasing": leasing("ALD Automotive", "VD-LSG-2022-6680", D(-650), D(310), 920, 48),
            "assurance": ass("Zurich Assurances", "POL-512667", "Casco complète", 2240, 1000, D(150)),
            "carte_grise": cg(D(-800), 2480, 5, "Gris Osmium"), "controle_technique": ct(D(-300), D(440), "SAN Vaud")}},
        # 9 — HYBRIDE RECHARGEABLE (PHEV)
        {"key": "rav4", "payload": {
            "plaque": "FR 329 540", "marque": "Toyota", "modele": "RAV4 Plug-in Hybrid", "annee": 2023,
            "vin": "JTMEB3FV90D890123", "type_carburant": "Hybride rechargeable", "cylindree_cm3": 2487,
            "puissance_kw": 225, "categorie": "SUV", "poids_vide": 1945, "co2_g_km": 22,
            "conso_officielle_l_100km": 1.0, "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 55,
            "batterie_capacite_brute_kwh": 18.1, "batterie_capacite_utile_kwh": 17.0,
            "conso_officielle_kwh_100km": 18.0, "autonomie_km": 75, "conso_reelle_l_100km": 2.2,
            "conso_reelle_source": "tickets", "kilometrage": 23900, "groupe": "Commercial", "base": "Fribourg",
            "responsable": "Pool Fribourg", "tracker_gps": "LT-GPS-2109",
            "prochaine_maintenance": D(170), "prochaine_expertise": D(540),
            "leasing": leasing("Mobility Fleet", "FR-LSG-2023-3312", D(-280), D(620), 780, 48),
            "assurance": ass("Helvetia", "POL-329540", "Casco complète", 1760, 500, D(260)),
            "carte_grise": cg(D(-330), 2370, 5, "Rouge Nebula"), "controle_technique": ct(None, D(700), "OCN Fribourg")}},
        # 10 — UTILITAIRE diesel — Luca Moretti ? non : conducteur dédié (utilise carte suspendue)
        {"key": "sprinter", "payload": {
            "plaque": "VS 173 448", "marque": "Mercedes-Benz", "modele": "Sprinter 316 CDI", "annee": 2021,
            "vin": "WDB9066331S456012", "type_carburant": "Diesel", "cylindree_cm3": 2143, "puissance_kw": 120,
            "categorie": "Utilitaire", "poids_vide": 2100, "co2_g_km": 212, "conso_officielle_l_100km": 8.9,
            "conso_officielle_norme": "WLTP", "capacite_reservoir_l": 71, "conso_reelle_l_100km": 10.4,
            "conso_reelle_source": "tickets", "kilometrage": 118400, "groupe": "Livraison", "base": "Sion",
            "responsable": "Luca Moretti", "tracker_gps": "LT-GPS-2110",
            "prochaine_maintenance": D(15), "prochaine_expertise": D(350),
            "leasing": leasing("AMAG Leasing", "VS-LSG-2021-8809", D(-900), D(40), 880, 48),
            "assurance": ass("Allianz Suisse", "POL-173448", "RC + Casco partielle", 2460, 2000, D(120)),
            "carte_grise": cg(D(-1500), 3500, 3, "Blanc Arctique"), "controle_technique": ct(D(-560), D(280), "Service auto VS")}},
    ]


DRIVERS = [
    {"key": "d_marc", "payload": {"nom": "Rochat", "prenom": "Marc", "email": "marc.rochat@demo-logitrak.ch",
     "telephone": "+41 79 410 22 18", "matricule_interne": "DEMO-C001", "actif": True, "date_debut": D(-900),
     "groupe": "Direction", "notes": "Référent flotte électrique."}},
    {"key": "d_sophie", "payload": {"nom": "Berger", "prenom": "Sophie", "email": "sophie.berger@demo-logitrak.ch",
     "telephone": "+41 78 221 09 54", "matricule_interne": "DEMO-C002", "actif": True, "date_debut": D(-720),
     "groupe": "Direction", "notes": "Véhicule de fonction."}},
    {"key": "d_daniel", "payload": {"nom": "Keller", "prenom": "Daniel", "email": "daniel.keller@demo-logitrak.ch",
     "telephone": "+41 76 553 71 02", "matricule_interne": "DEMO-C003", "actif": True, "date_debut": D(-1100),
     "groupe": "Commercial", "notes": "Secteur Suisse alémanique."}},
    {"key": "d_camille", "payload": {"nom": "Favre", "prenom": "Camille", "email": "camille.favre@demo-logitrak.ch",
     "telephone": "+41 79 884 33 61", "matricule_interne": "DEMO-C004", "actif": True, "date_debut": D(-400),
     "groupe": "Commercial", "notes": "Secteur Suisse romande."}},
    {"key": "d_luca", "payload": {"nom": "Moretti", "prenom": "Luca", "email": "luca.moretti@demo-logitrak.ch",
     "telephone": "+41 78 112 46 90", "matricule_interne": "DEMO-C005", "actif": True, "date_debut": D(-650),
     "groupe": "Livraison", "notes": "Livraisons Valais / Chablais."}},
    {"key": "d_elena", "payload": {"nom": "Schneider", "prenom": "Elena", "email": "elena.schneider@demo-logitrak.ch",
     "telephone": "+41 76 907 18 25", "matricule_interne": "DEMO-C006", "actif": True, "date_debut": D(-30),
     "groupe": "Direction", "notes": "Nouvelle arrivée — en attente d'affectation véhicule."}},
]


# =====================================================================================================================
#  SEED (API, compte admin du tenant)
# =====================================================================================================================
def ensure_tenant_and_users(res, ids):
    sa = sa_headers()
    ok(api(sa, "POST", "/admin/tenants", {"name": TENANT_NAME, "id": T}), 200, 409)
    pw = load_or_make_passwords()
    users = {u["email"]: u for u in ok(api(sa, "GET", f"/admin/tenants/{T}/users"))}
    for key, (email, role, name) in ACCOUNTS.items():
        if email not in users:
            users[email] = ok(api(sa, "POST", f"/admin/tenants/{T}/users",
                                  {"email": email, "password": pw[key], "role": role, "name": name}))
        else:
            ok(api(sa, "PUT", f"/admin/users/{users[email]['id']}", {"password": pw[key]}))
        ids[f"user_{key}"] = users[email]["id"]
    write_test_credentials(pw)
    return sa, pw


def ensure_vehicle(h, key, payload, ids):
    guard(T)
    cur = db.vehicles.find_one({"tenant_id": T, "plaque": payload["plaque"]}, {"_id": 0, "id": 1})
    ids[f"v_{key}"] = cur["id"] if cur else ok(api(h, "POST", "/vehicles", payload))["id"]


def ensure_driver(h, key, payload, ids):
    cur = db.drivers.find_one({"tenant_id": T, "matricule_interne": payload["matricule_interne"]}, {"_id": 0, "id": 1})
    ids[key] = cur["id"] if cur else ok(api(h, "POST", "/drivers", payload))["id"]


def ensure_assignment(h, key, vid, did, valid_from, valid_to=None, principal=True, motif=None, ids=None):
    cur = db.driver_assignments.find_one({"tenant_id": T, "vehicle_id": vid, "driver_id": did,
                                          "valid_from": valid_from}, {"_id": 0, "id": 1})
    body = {"driver_id": did, "valid_from": valid_from, "valid_to": valid_to, "principal": principal}
    if motif:
        body["motif"] = motif
    ids[key] = cur["id"] if cur else ok(api(h, "POST", f"/vehicles/{vid}/driver-assignments", body))["id"]


def ensure_card(h, key, fournisseur, last4, assigns, ids, **over):
    cur = db.fuel_cards.find_one({"tenant_id": T, "fournisseur": fournisseur, "last4": last4}, {"_id": 0, "id": 1})
    body = {"fournisseur": fournisseur, "last4": last4, "type_affectation": "vehicule", **over}
    cid = cur["id"] if cur else ok(api(h, "POST", "/fuel-cards", body))["id"]
    ids[key] = cid
    for vid, vf, vt in assigns:
        if not db.fuel_card_assignments.find_one({"tenant_id": T, "card_id": cid, "vehicle_id": vid, "valid_from": vf}):
            ok(api(h, "POST", f"/fuel-cards/{cid}/assignments",
                   {"type": "vehicule", "vehicle_id": vid, "valid_from": vf, "valid_to": vt}))
    return cid


def ensure_plein(h, key, vid, day, montant, ids, litres=None, kwh=None, station=None, driver_id=None,
                 carte_last4=None, km=None, heure="08:15", motif="Saisie manuelle — ticket conducteur"):
    cur = db.fuel_transactions.find_one({"tenant_id": T, "vehicle_id": vid, "date": day, "montant": montant,
                                         "is_deleted": False}, {"_id": 0, "id": 1, "source_document_id": 1})
    if cur:
        ids[key] = cur["id"]
        return
    electric = kwh is not None
    body = {"date": day, "heure": heure, "station": station, "montant": montant, "motif": motif,
            "business_category": "ENERGIE_ELECTRIQUE" if electric else "CARBURANT"}
    if electric:
        body.update({"energie_kwh": kwh, "prix_kwh": round(montant / kwh, 3)})
    else:
        body.update({"litres": litres, "prix_litre": round(montant / litres, 3)})
    if driver_id:
        body["driver_id"] = driver_id
    if carte_last4:
        body["carte_last4"] = carte_last4
    if km:
        body["kilometrage"] = km
    ids[key] = ok(api(h, "POST", f"/vehicles/{vid}/fuel-transactions", body))["fuel_transaction"]["id"]


def ensure_fine(h, key, vid, numero, autorite, montant, delai, ids, driver_id=None, infraction="speeding",
                lieu=None, notes_internes=None, dossier=None, priorite="normal"):
    cur = db.documents.find_one({"tenant_id": T, "numero": numero, "is_deleted": False}, {"_id": 0, "id": 1})
    if cur:
        ids[key] = cur["id"]
        return ids[key]
    body = {"autorite": autorite, "numero_amende": numero, "date_infraction": D(-20), "montant": montant,
            "delai_paiement": delai, "type_infraction": infraction, "priorite": priorite,
            "motif": "Avis d'amende reçu par courrier", "lieu_infraction": lieu or {"ville": "Lausanne", "canton": "VD"}}
    if driver_id:
        body["driver_id"] = driver_id
    if notes_internes:
        body["notes_internes"] = notes_internes
    if dossier:
        body["dossier_interne"] = dossier
    ids[key] = ok(api(h, "POST", f"/vehicles/{vid}/fines", body))["document_id"]
    return ids[key]


def upload_doc(h, key, vid, filename, folder, ids, blob=PNG, ctype="image/png"):
    cur = db.documents.find_one({"tenant_id": T, "vehicle_id": vid, "original_filename": filename,
                                 "is_deleted": False}, {"_id": 0, "id": 1})
    if cur:
        ids[key] = cur["id"]
        return cur["id"]
    j = ok(requests.post(f"{BASE}/api/vehicles/{vid}/documents",
                         files={"file": (filename, io.BytesIO(blob), ctype)}, data={"folder": folder},
                         headers=h, timeout=60))
    ids[key] = j["id"]
    return j["id"]


def ensure_invoice(h, key, vid, filename, fournisseur, numero, montant, category, day, ids, frequence="unique"):
    """Facture = document fichier (dossier Factures) + PATCH montant/catégorie → coût canonique."""
    did = upload_doc(h, key, vid, filename, "Factures", ids, blob=PDF, ctype="application/pdf")
    ok(api(h, "PATCH", f"/documents/{did}", {"business_category": category, "montant": montant, "devise": "CHF",
                                             "frequence": frequence, "fournisseur": fournisseur, "numero": numero,
                                             "date_debut": day}))
    return did


def seed():
    if not BASELINE.exists():
        die("baseline absente : exécuter `baseline` AVANT le seed (ou le mode `all`)")
    res = load_result()
    ids = res["ids"]
    sa, pw = ensure_tenant_and_users(res, ids)
    hA = login(ACCOUNTS["ADMIN"][0], pw["ADMIN"])

    # --- véhicules ---
    for spec in vehicle_specs():
        ensure_vehicle(hA, spec["key"], spec["payload"], ids)
    V = {k[2:]: v for k, v in ids.items() if k.startswith("v_")}

    # --- conducteurs ---
    for d in DRIVERS:
        ensure_driver(hA, d["key"], d["payload"], ids)

    # --- affectations : actives + 1 ancienne terminée + Elena sans véhicule + Octavia/Ioniq sans conducteur ---
    ensure_assignment(hA, "a_marc_tesla", V["tesla"], ids["d_marc"], D(-220), ids=ids)
    ensure_assignment(hA, "a_sophie_passat", V["passat"], ids["d_sophie"], D(-300), ids=ids)
    ensure_assignment(hA, "a_daniel_bmw", V["bmw"], ids["d_daniel"], D(-150), ids=ids)
    ensure_assignment(hA, "a_daniel_corolla_old", V["corolla"], ids["d_daniel"], D(-520), D(-160),
                      motif="Changement de véhicule (reprise par le pool)", ids=ids)
    ensure_assignment(hA, "a_camille_megane", V["megane"], ids["d_camille"], D(-110), ids=ids)
    ensure_assignment(hA, "a_luca_sprinter", V["sprinter"], ids["d_luca"], D(-640), ids=ids)
    ensure_assignment(hA, "a_luca_xc60", V["xc60"], ids["d_luca"], D(-200), ids=ids)

    # --- cartes carburant : Migrol (valide) · Shell (valide) · Tamoil (EXPIRÉE) · Avia (SUSPENDUE) ---
    ensure_card(hA, "card_migrol", "Migrol", "1182", [(V["octavia"], D(-400), None)], ids,
                expire_le=D(520), activee_le=D(-700), plafond_mois=1500, produits_autorises=["Diesel", "AdBlue"],
                notes="Carte site Genève.")
    ensure_card(hA, "card_shell", "Shell", "4473", [(V["passat"], D(-280), None)], ids,
                expire_le=D(610), activee_le=D(-280), plafond_mois=1200, produits_autorises=["Diesel"],
                notes="Carte véhicule de fonction.")
    ensure_card(hA, "card_tamoil", "Tamoil", "7290", [(V["bmw"], D(-500), None)], ids,
                expire_le=D(-20), activee_le=D(-900), plafond_mois=1000, produits_autorises=["Diesel"],
                notes="Carte arrivée à expiration — à renouveler.")
    ensure_card(hA, "card_avia", "Avia", "3651", [(V["sprinter"], D(-600), None)], ids,
                statut="suspendue", expire_le=D(300), activee_le=D(-600), plafond_mois=2000,
                produits_autorises=["Diesel", "AdBlue"], notes="Carte suspendue (perte signalée).")

    # --- transactions carburant (thermiques / utilitaire / PHEV) ---
    ensure_plein(hA, "tx_octavia1", V["octavia"], D(-6), 86.40, ids, litres=48, station="Migrol Genève-Carouge",
                 carte_last4="1182", km=78200)
    ensure_plein(hA, "tx_octavia2", V["octavia"], D(-34), 92.10, ids, litres=51, station="Migrol Genève-Carouge",
                 carte_last4="1182", km=77400, heure="17:40")
    ensure_plein(hA, "tx_passat1", V["passat"], D(-4), 101.20, ids, litres=56, station="Shell Lausanne-Sébeillon",
                 driver_id=ids["d_sophie"], carte_last4="4473", km=54200)
    ensure_plein(hA, "tx_passat2", V["passat"], D(-29), 96.75, ids, litres=53, station="Shell Vevey",
                 driver_id=ids["d_sophie"], carte_last4="4473", km=53600)
    ensure_plein(hA, "tx_bmw1", V["bmw"], D(-3), 98.30, ids, litres=52, station="Tamoil Zürich-Altstetten",
                 driver_id=ids["d_daniel"], carte_last4="7290", km=96700)
    ensure_plein(hA, "tx_sprinter1", V["sprinter"], D(-5), 138.90, ids, litres=68, station="Avia Sion",
                 driver_id=ids["d_luca"], carte_last4="3651", km=118200)
    ensure_plein(hA, "tx_xc60_fuel", V["xc60"], D(-9), 72.40, ids, litres=40, station="BP Lausanne-Crissier",
                 driver_id=ids["d_luca"], km=61900)
    # transaction NON RAPPROCHÉE : Corolla (aucune carte assignée)
    ensure_plein(hA, "tx_corolla_unmatched", V["corolla"], D(-7), 64.80, ids, litres=36, station="Coop Pronto Berne",
                 km=31100, motif="Plein pool — ticket sans carte")

    # --- recharges EV (historique multi-mois) ---
    ensure_plein(hA, "ev_tesla1", V["tesla"], D(-8), 18.60, ids, kwh=42.0, station="Ionity Nyon",
                 driver_id=ids["d_marc"], km=41050)
    ensure_plein(hA, "ev_tesla2", V["tesla"], D(-38), 15.20, ids, kwh=38.5, station="Tesla Supercharger Genève",
                 driver_id=ids["d_marc"], km=39800, heure="07:20")
    ensure_plein(hA, "ev_tesla3", V["tesla"], D(-69), 21.40, ids, kwh=48.0, station="Move Lausanne",
                 driver_id=ids["d_marc"], km=38200)
    ensure_plein(hA, "ev_tesla4", V["tesla"], D(-98), 16.90, ids, kwh=40.0, station="Ionity Nyon",
                 driver_id=ids["d_marc"], km=36900)
    ensure_plein(hA, "ev_megane1", V["megane"], D(-12), 14.30, ids, kwh=35.0, station="Move Lausanne",
                 driver_id=ids["d_camille"], km=18500)
    ensure_plein(hA, "ev_megane2", V["megane"], D(-45), 12.80, ids, kwh=31.0, station="Migrol EV Morges",
                 driver_id=ids["d_camille"], km=17600)
    ensure_plein(hA, "ev_xc60", V["xc60"], D(-18), 6.40, ids, kwh=15.0, station="Volvo Charge Lausanne",
                 driver_id=ids["d_luca"], km=61700)
    ensure_plein(hA, "ev_rav4", V["rav4"], D(-22), 7.10, ids, kwh=16.5, station="Groupe E Move Fribourg", km=23800)

    # --- amendes : ouverte (D1/Tesla) · payée (D2/Passat) · en retard (D3/BMW) · contestée (D4/Mégane) ---
    ensure_fine(hA, "fine_open", V["tesla"], "GE-2026-114502", "Fondation sécurité routière Genève", 120.0, D(22), ids,
                driver_id=ids["d_marc"], infraction="speeding", lieu={"ville": "Genève", "canton": "GE", "lieu": "Pont du Mont-Blanc"},
                notes_internes="À régler avant échéance.", dossier="DOS-2026-0145")
    fid_paid = ensure_fine(hA, "fine_paid", V["passat"], "VD-2026-088211", "Police cantonale vaudoise", 40.0, D(10), ids,
                           driver_id=ids["d_sophie"], infraction="parking", lieu={"ville": "Lausanne", "canton": "VD"},
                           dossier="DOS-2026-0132")
    fid_late = ensure_fine(hA, "fine_late", V["bmw"], "ZH-2026-203994", "Stadtpolizei Zürich", 250.0, D(-6), ids,
                           driver_id=ids["d_daniel"], infraction="red_light", lieu={"ville": "Zürich", "canton": "ZH"},
                           priorite="high", notes_internes="Relance reçue — traiter en priorité.", dossier="DOS-2026-0118")
    fid_disp = ensure_fine(hA, "fine_disputed", V["megane"], "VD-2026-090877", "Police municipale Lausanne", 60.0, D(18), ids,
                           driver_id=ids["d_camille"], infraction="forbidden_zone", lieu={"ville": "Lausanne", "canton": "VD"},
                           dossier="DOS-2026-0150")
    # transitions métier (idempotentes)
    if (db.documents.find_one({"id": fid_paid}, {"_id": 0, "fine_status": 1}) or {}).get("fine_status") != "payee":
        ok(api(hA, "POST", f"/documents/{fid_paid}/paid", {"payee": True, "paid_on": D(-2),
                                                           "payment_ref": "EBILL-2026-77120", "motif": "Réglée par e-banking"}))
    if (db.documents.find_one({"id": fid_disp}, {"_id": 0, "fine_status": 1}) or {}).get("fine_status") != "contestee":
        ok(api(hA, "POST", f"/documents/{fid_disp}/fine-status",
               {"fine_status": "contestee", "motif": "Contestation déposée : signalisation non conforme."}))

    # --- documents véhicule (cartes grises, assurances, leasing, contrôles) + cas visibles ---
    upload_doc(hA, "doc_cg_octavia", V["octavia"], "carte-grise-octavia.png", "Carte grise", ids)
    upload_doc(hA, "doc_leasing_passat", V["passat"], "contrat-leasing-passat.pdf", "Leasing", ids, blob=PDF, ctype="application/pdf")
    upload_doc(hA, "doc_cg_tesla", V["tesla"], "carte-grise-tesla.png", "Carte grise", ids)
    upload_doc(hA, "doc_leasing_tesla", V["tesla"], "contrat-leasing-tesla.pdf", "Leasing", ids, blob=PDF, ctype="application/pdf")
    # document EXPIRÉ (contrôle technique BMW, échéance passée)
    did_ct = upload_doc(hA, "doc_ct_bmw", V["bmw"], "expertise-bmw-2024.pdf", "Contrôle technique", ids, blob=PDF, ctype="application/pdf")
    ok(api(hA, "PATCH", f"/documents/{did_ct}", {"date_expiration": D(-15), "fournisseur": "StVA Zürich",
                                                 "numero": "EXP-ZH-2024-5521"}))
    # document < 30 JOURS (assurance Passat, bientôt échue)
    did_as = upload_doc(hA, "doc_assurance_passat", V["passat"], "police-assurance-passat.pdf", "Assurance", ids, blob=PDF, ctype="application/pdf")
    ok(api(hA, "PATCH", f"/documents/{did_as}", {"date_expiration": D(20), "fournisseur": "Zurich Assurances",
                                                 "numero": "POL-903221", "preavis_jours": 30}))
    # document EN ATTENTE de validation (a_verifier)
    did_av = upload_doc(hA, "doc_a_verifier", V["megane"], "document-a-verifier-megane.png", "Divers", ids)
    ok(api(hA, "PATCH", f"/documents/{did_av}", {"a_verifier": True, "notes": "À vérifier : classer dans la bonne catégorie."}))
    # (Ioniq 5 volontairement SANS document → document requis manquant)

    # --- factures / coûts ---
    ensure_invoice(hA, "inv_entretien", V["octavia"], "facture-entretien-octavia.pdf", "Garage Rondo SA",
                   "F-2026-3380", 480.50, "ENTRETIEN", D(-40), ids)
    ensure_invoice(hA, "inv_pneus", V["bmw"], "facture-pneus-bmw.pdf", "PneuStock Zürich",
                   "F-2026-9921", 1180.00, "PNEUS", D(-25), ids)
    ensure_invoice(hA, "inv_reparation", V["passat"], "facture-reparation-passat.pdf", "Carrosserie Léman",
                   "F-2026-4471", 1240.90, "REPARATION", D(-18), ids)
    ensure_invoice(hA, "inv_assurance", V["sprinter"], "facture-assurance-sprinter.pdf", "Allianz Suisse",
                   "F-2026-7781", 2460.00, "ASSURANCE", D(-60), ids, frequence="annuel")
    ensure_invoice(hA, "inv_leasing", V["tesla"], "facture-leasing-tesla.pdf", "AMAG Leasing",
                   "F-2026-9015", 980.00, "LEASING", D(-10), ids, frequence="mensuel")
    ensure_invoice(hA, "inv_recharge", V["ioniq"], "facture-recharge-ioniq.pdf", "Groupe E Move",
                   "F-2026-6620", 214.30, "ENERGIE_ELECTRIQUE", D(-15), ids)

    # --- états des lieux ---
    if not db.inspections.find_one({"tenant_id": T, "vehicle_id": V["sprinter"]}):
        ok(api(hA, "POST", f"/vehicles/{V['sprinter']}/inspections",
               {"date": D(-30), "responsable": "Luca Moretti", "kilometrage": 117800,
                "commentaire": "État général bon. Rayure latérale droite signalée.", "photos": []}))

    # --- liaison compte driver → conducteur actif Marc Rochat ---
    ok(api(sa, "PUT", f"/admin/users/{ids['user_DRIVER']}", {"driver_id": ids["d_marc"]}))

    save_result(res)
    print("SEED OK — tenant", T, "| véhicules", len(vehicle_specs()), "| conducteurs", len(DRIVERS))
    return True


# =====================================================================================================================
#  MARQUAGE (DB, strictement tenant-scopé)
# =====================================================================================================================
def mark():
    guard(T)
    db.tenants.update_one({"id": T}, {"$set": MARKERS})
    total = 1
    for c in MARK_COLLECTIONS:
        r = db[c].update_many({"tenant_id": T}, {"$set": MARKERS})
        total += r.modified_count
    print(f"MARQUAGE OK — {total} enregistrement(s) tagué(s) demo_seed=true (tenant {T} uniquement)")
    return total


# =====================================================================================================================
#  VERIFY (API + isolation)
# =====================================================================================================================
def verify():
    pw = load_or_make_passwords()
    hA = login(ACCOUNTS["ADMIN"][0], pw["ADMIN"])
    hD = login(ACCOUNTS["DRIVER"][0], pw["DRIVER"])
    hR = login(ACCOUNTS["READONLY"][0], pw["READONLY"])
    checks = []

    def chk(name, passed, detail=""):
        checks.append({"check": name, "result": PASS if passed else FAIL, "detail": str(detail)[:400]})
        print(f"[{PASS if passed else FAIL}] {name}{' — ' + str(detail)[:160] if detail else ''}")

    # logins
    chk("login admin/driver/read_only", bool(hA and hD and hR))
    me_a, me_d, me_r = ok(api(hA, "GET", "/auth/me")), ok(api(hD, "GET", "/auth/me")), ok(api(hR, "GET", "/auth/me"))
    chk("rôles corrects (admin/driver/read_only) + tenant demo-logitrak",
        me_a["role"] == "admin" and me_d["role"] == "driver" and me_r["role"] == "read_only"
        and me_a.get("tenant_id") == T, {"admin": me_a["role"], "driver": me_d["role"], "ro": me_r["role"]})

    vehs = ok(api(hA, "GET", "/vehicles"))
    types = {}
    for v in vehs:
        types.setdefault(v.get("type_carburant"), 0)
        types[v["type_carburant"]] += 1
    chk("véhicules : 10 au total (4 thermiques · 3 électriques · 2 hybrides · 1 utilitaire)",
        len(vehs) == 10, {"total": len(vehs), "par_carburant": types})

    drivers = ok(api(hA, "GET", "/drivers"))
    sans_veh = [d for d in drivers if not d.get("affectations")]
    chk("conducteurs : 6, dont au moins 1 sans véhicule", len(drivers) == 6 and len(sans_veh) >= 1,
        {"total": len(drivers), "sans_vehicule": [d.get("nom") for d in sans_veh]})

    cards = ok(api(hA, "GET", "/fuel-cards"))
    citems = cards["items"]
    expired = [c for c in citems if c.get("expiration_state") == "expiree"]
    suspended = [c for c in citems if c.get("statut") != "active"]
    chk("cartes carburant : 4, dont ≥1 expirée et ≥1 non-active (suspendue)",
        len(citems) == 4 and len(expired) >= 1 and len(suspended) >= 1,
        {"total": len(citems), "expirees": len(expired), "non_actives": len(suspended)})

    energy = ok(api(hA, "GET", "/energy"))
    ev_tx = [x for x in energy["transactions"] if x.get("energie_kwh")]
    no_card = [x for x in energy["transactions"] if not x.get("card_id")]
    chk("énergie : ≥4 recharges EV + ≥1 transaction non rapprochée (sans carte)",
        len(ev_tx) >= 4 and len(no_card) >= 1 and energy["totals"]["transactions"] >= 15,
        {"transactions": energy["totals"]["transactions"], "recharges_ev": len(ev_tx), "sans_carte": len(no_card)})

    fines = ok(api(hA, "GET", "/fines"))
    fstatuses = {}
    for f in fines["items"]:
        fstatuses[f.get("fine_status")] = fstatuses.get(f.get("fine_status"), 0) + 1
    has_states = {"a_payer", "payee", "contestee"} <= set(fstatuses)
    late = [f for f in fines["items"] if f.get("statut_badge") == "EN_RETARD" or f.get("badge") == "EN_RETARD"]
    chk("amendes : payée + ouverte + contestée présentes (en retard dérivée du délai)",
        fines["total"] >= 4 and has_states, {"total": fines["total"], "par_statut": fstatuses})

    costs = ok(api(hA, "GET", "/costs"))
    cats = {i.get("business_category") for i in costs.get("items", [])}
    chk("coûts/factures : plusieurs catégories présentes (entretien/pneus/réparation/assurance/leasing/énergie)",
        len(costs.get("items", [])) >= 6, {"items": len(costs.get("items", [])), "categories": sorted(c for c in cats if c)})

    dash = ok(api(hA, "GET", "/dashboard"))
    chk("dashboard : KPIs calculés (véhicules + échéances)",
        dash.get("total_vehicles") == 10, {"total_vehicles": dash.get("total_vehicles")})

    # cas visibles documentaires
    # document expiré + <30j via /deadlines
    dls = ok(api(hA, "GET", "/deadlines"))
    doc_dls = [i for i in dls.get("items", []) if i.get("is_document_deadline")]
    expired_doc = [i for i in doc_dls if i.get("statut") == "EXPIRE"]
    urgent_doc = [i for i in doc_dls if i.get("statut") == "URGENT"]
    chk("échéances documentaires : ≥1 expirée et ≥1 urgente (<30j)",
        len(expired_doc) >= 1 and len(urgent_doc) >= 1,
        {"doc_deadlines": len(doc_dls), "expirees": len(expired_doc), "urgentes": len(urgent_doc)})

    # vues chauffeur
    mv = ok(api(hD, "GET", "/me/vehicles"))
    mf = ok(api(hD, "GET", "/me/fuel-transactions"))
    mfi = ok(api(hD, "GET", "/me/fines"))
    chk("vue chauffeur : ≥1 véhicule, ≥1 plein, ≥1 amende visibles",
        mv["total"] >= 1 and mf["total"] >= 1 and mfi["total"] >= 1,
        {"vehicules": mv["total"], "pleins": mf["total"], "amendes": mfi["total"]})

    # read_only : lecture OK, mutation 403
    ro_list = api(hR, "GET", "/vehicles").status_code
    ro_mut = api(hR, "PUT", f"/vehicles/{vehs[0]['id']}", {"modele": "X"}).status_code
    ro_fine = api(hR, "POST", f"/vehicles/{vehs[0]['id']}/fines", {"autorite": "X", "montant": 10}).status_code
    chk("read_only : lecture 200, mutations 403", ro_list == 200 and ro_mut == 403 and ro_fine == 403,
        {"list": ro_list, "put": ro_mut, "post_fine": ro_fine})

    # ISOLATION
    if BASELINE.exists():
        before, after = json.loads(BASELINE.read_text()), fingerprint()
        keys = sorted(set(before["counts"]) | set(after["counts"]))
        diff = {k: (before["counts"].get(k), after["counts"].get(k)) for k in keys
                if before["counts"].get(k) != after["counts"].get(k) or before["hashes"].get(k) != after["hashes"].get(k)}
        diff_default = {k: v for k, v in diff.items() if k.endswith("|default")}
        diff_others = {k: v for k, v in diff.items() if not k.endswith("|default")}
        chk("DEFAULT_UNCHANGED (default identique avant/après)", not diff_default, diff_default or "aucune différence")
        chk("OTHER_TENANTS_UNCHANGED (26 autres tenants identiques)",
            not diff_others and before["tenants_ids"] == after["tenants_ids"], diff_others or "aucune différence")
    else:
        chk("ISOLATION (baseline absente)", False, "baseline manquante — exécuter baseline avant seed")

    chk("TARGET_TENANT_PRESENT (demo-logitrak existe)", db.tenants.count_documents({"id": T}) == 1)
    # marquage
    marked = db.vehicles.count_documents({"tenant_id": T, "demo_seed": True})
    chk("MARQUAGE demo_seed appliqué aux véhicules", marked == 10, {"vehicles_marked": marked})

    verdict = all(c["result"] == PASS for c in checks)
    VERIFY_OUT.write_text(json.dumps({"checks": checks, "verdict": PASS if verdict else FAIL}, indent=1, ensure_ascii=False, default=str))
    print(f"\nDEMO TENANT VERIFY = {PASS if verdict else FAIL}  →", VERIFY_OUT)
    return verdict


# =====================================================================================================================
#  INVENTORY + REPORT
# =====================================================================================================================
def inventory():
    out = {"tenant": {"id": T, "name": TENANT_NAME, "markers": MARKERS},
           "counts": {c: db[c].count_documents({"tenant_id": T}) for c in sorted(db.list_collection_names())
                      if c not in ("tenants", "login_attempts") and db[c].count_documents({"tenant_id": T})},
           "users": [{k: u.get(k) for k in ("email", "role", "driver_id")} for u in db.users.find({"tenant_id": T}, {"_id": 0}).sort("email", 1)],
           "vehicles_by_fuel": {s["_id"]: s["n"] for s in db.vehicles.aggregate(
               [{"$match": {"tenant_id": T}}, {"$group": {"_id": "$type_carburant", "n": {"$sum": 1}}}])},
           "fuel_cards": [{k: c.get(k) for k in ("fournisseur", "last4", "statut", "expire_le")} for c in db.fuel_cards.find({"tenant_id": T}, {"_id": 0})],
           "fines_by_status": {s["_id"]: s["n"] for s in db.documents.aggregate(
               [{"$match": {"tenant_id": T, "business_category": "AMENDE"}}, {"$group": {"_id": "$fine_status", "n": {"$sum": 1}}}])}}
    INVENTORY.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
    print("INVENTORY →", INVENTORY)
    print(json.dumps(out["counts"], ensure_ascii=False))
    return out


def report():
    inv = inventory()
    ver = json.loads(VERIFY_OUT.read_text()) if VERIFY_OUT.exists() else {"checks": [], "verdict": "N/A"}
    lines = [f"# Tenant démo commercial `demo-logitrak` — rapport", "",
             f"- Tenant : **{TENANT_NAME}** (`{T}`) · marquage `demo_seed=true`, `demo_seed_version=2026-10`, `demo_seed_group=commercial-demo`",
             "- Méthode : création via l'API du compte admin du tenant (règles métier + isolation). Aucun déploiement. Aucune migration.",
             "", "## Counts par entité"]
    for c, n in inv["counts"].items():
        lines.append(f"- `{c}` : {n}")
    lines += ["", "## Comptes créés (mots de passe : voir `memory/test_credentials.md`, non affichés)"]
    for u in inv["users"]:
        lines.append(f"- `{u['email']}` · rôle `{u['role']}`" + (" · lié à un conducteur" if u.get("driver_id") else ""))
    lines += ["", f"## Véhicules par carburant", f"- {json.dumps(inv['vehicles_by_fuel'], ensure_ascii=False)}",
              "", "## Cartes carburant"]
    for c in inv["fuel_cards"]:
        lines.append(f"- {c['fournisseur']} ••{c['last4']} · statut `{c['statut']}` · expire {c['expire_le']}")
    lines += ["", "## Amendes par statut", f"- {json.dumps(inv['fines_by_status'], ensure_ascii=False)}",
              "", "## Scénarios démo disponibles",
              "- EV avec recharges (Tesla Model 3, historique multi-mois) · véhicule sans conducteur (Škoda Octavia, Hyundai Ioniq 5)",
              "- Ancienne affectation terminée (Daniel Keller · Toyota Corolla) · conducteur sans véhicule (Elena Schneider)",
              "- Carte Tamoil expirée · carte Avia suspendue · transaction non rapprochée (Toyota Corolla)",
              "- Document expiré (contrôle BMW) · échéance <30j (assurance Passat) · document en attente (Mégane) · document requis manquant (Ioniq 5)",
              "- Amendes : ouverte · payée · en retard · contestée · plusieurs factures (entretien/pneus/réparation/assurance/leasing/énergie)",
              "", "## Vérification API", f"- Verdict : **{ver['verdict']}**"]
    for c in ver["checks"]:
        lines.append(f"  - [{c['result']}] {c['check']}")
    lines += ["", "## Isolation", "- `default` inchangé · 26 autres tenants inchangés (fingerprint avant/après, cf. verify).",
              "", f"## VERDICT : DEMO TENANT = {'READY' if ver['verdict'] == PASS else 'NON READY'}"]
    REPORT.write_text("\n".join(lines))
    print("REPORT →", REPORT)
    return ver["verdict"]


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "inventory"
    if cmd == "baseline":
        baseline()
    elif cmd == "seed":
        sys.exit(0 if seed() else 1)
    elif cmd == "mark":
        mark()
    elif cmd == "verify":
        sys.exit(0 if verify() else 1)
    elif cmd == "inventory":
        inventory()
    elif cmd == "report":
        sys.exit(0 if report() == PASS else 1)
    elif cmd == "all":
        baseline()
        seed()
        mark()
        v = verify()
        report()
        sys.exit(0 if v else 1)
    else:
        die(f"mode inconnu {cmd} (baseline | seed | mark | verify | inventory | report | all)")
