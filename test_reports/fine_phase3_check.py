"""Preuve métier Phase 3 (preview) : amende factice réaliste → OCR réel → review AMENDE → Coûts/Échéances → payée."""
import sys
import requests
from dotenv import dotenv_values
from PIL import Image, ImageDraw, ImageFont

BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
ENV = dotenv_values("/app/backend/.env")
VEH = "6d00f932-d74d-4e1b-84ad-6116ffb0af33"
IMG = "/app/test_reports/fixtures/amende_test.jpg"
NUMERO = "ORD-2026-0078-451"

r = requests.post(f"{BASE}/api/auth/login", json={"email": ENV["ADMIN_EMAIL"], "password": ENV["ADMIN_PASSWORD"]}, timeout=30)
r.raise_for_status()
H = {"Authorization": f"Bearer {r.json()['token']}"}


def make_image():
    W, Hh = 1240, 1754
    im = Image.new("RGB", (W, Hh), "white")
    d = ImageDraw.Draw(im)
    f = lambda s, b=False: ImageFont.truetype(f"/usr/share/fonts/truetype/freefont/FreeSans{'Bold' if b else ''}.ttf", s)
    y = 90
    d.text((90, y), "POLICE CANTONALE VAUDOISE", font=f(44, True), fill="black"); y += 60
    d.text((90, y), "Centre de traitement des amendes d'ordre — Centre Blécherette, 1014 Lausanne", font=f(24), fill="black"); y += 90
    d.text((90, y), "AMENDE D'ORDRE — ORDONNANCE PÉNALE", font=f(40, True), fill="black"); y += 80
    rows = [("N° de référence", NUMERO), ("Date de l'infraction", "02.06.2026 à 09:17"),
            ("Lieu", "Lausanne, Avenue de Rhodanie"), ("Infraction", "Dépassement de la vitesse maximale autorisée (+7 km/h)"),
            ("Véhicule (plaque)", "BE 579 928"), ("Détenteur", "LOGITRAK SA, Berne")]
    for k, v in rows:
        d.text((90, y), k, font=f(26), fill="#444"); d.text((520, y), v, font=f(28, True), fill="black"); y += 56
    y += 40
    d.rectangle([80, y, W - 80, y + 190], outline="black", width=3); y += 25
    d.text((110, y), "Amende", font=f(28), fill="black"); d.text((900, y), "CHF 100.00", font=f(28), fill="black"); y += 45
    d.text((110, y), "Frais administratifs", font=f(28), fill="black"); d.text((900, y), "CHF  20.00", font=f(28), fill="black"); y += 55
    d.text((110, y), "MONTANT TOTAL À PAYER", font=f(32, True), fill="black"); d.text((870, y), "CHF 120.00", font=f(34, True), fill="black"); y += 110
    d.text((90, y), "Délai de paiement : 30.11.2026", font=f(32, True), fill="black"); y += 60
    d.text((90, y), "Paiement par QR-facture ci-jointe. Passé ce délai, la procédure ordinaire est engagée.", font=f(22), fill="#333")
    im.save(IMG, "JPEG", quality=90)


def costs():
    d = requests.get(f"{BASE}/api/costs", params={"vehicle_id": VEH}, headers=H, timeout=30).json()
    items = [i for i in d["items"] if i["vehicle_id"] == VEH]
    return items, round(sum(i["cout_annuel"] for i in items), 2)


def deadlines(doc_id):
    d = requests.get(f"{BASE}/api/deadlines", headers=H, timeout=30).json()
    return next((i for i in d["items"] if i["key"] == f"doc:{doc_id}"), None), d["summary"]


step = sys.argv[1] if len(sys.argv) > 1 else "scan"
if step == "scan":
    make_image()
    items, total = costs()
    print("COSTS BEFORE: n =", len(items), "total =", total)
    with open(IMG, "rb") as fh:
        r = requests.post(f"{BASE}/api/vehicles/{VEH}/documents/scan", headers=H, timeout=180,
                          files={"files": ("amende_test.jpg", fh, "image/jpeg")})
    print("SCAN HTTP", r.status_code)
    d = r.json()
    print("document_id =", d.get("document_id"))
    print("type =", d.get("document_type"), d.get("type_confidence"), "| detected =", d.get("detected_type"),
          "| mismatch =", d.get("type_mismatch"))
    print("suggested_business_category =", d.get("suggested_business_category"), "| missing =", d.get("missing_fields"))
    for f in d.get("fields", []):
        print(f"   {f['field']:16} = {f['value']!r:36} conf={f.get('confidence')} status={f.get('status')} conflict={f.get('conflict')}")
elif step == "validate":
    doc_id = sys.argv[2]
    items, before = costs()
    ext = requests.get(f"{BASE}/api/documents/{doc_id}/extraction", headers=H, timeout=30).json()
    fields = {f["field"]: f["value"] for f in ext["fields"] if f["value"] not in (None, "")}
    print("fields envoyés (review humaine, OCR non modifié):", fields)
    r = requests.post(f"{BASE}/api/documents/{doc_id}/validate", headers=H, timeout=60,
                      json={"document_type": "amende", "fields": fields, "business_category": "AMENDE"})
    print("VALIDATE HTTP", r.status_code)
    res = r.json()
    print("warnings =", res.get("warnings"))
    print("cost =", res.get("cost"))
    items, after = costs()
    hits = [i for i in items if i["document_id"] == doc_id]
    print(f"COSTS AFTER: n = {len(items)} total = {after} | delta = {round(after - before, 2)} | items for doc = {len(hits)}")
    dl, summ = deadlines(doc_id)
    print("DEADLINE:", {k: dl.get(k) for k in ("label", "category", "type", "date", "days_remaining", "statut", "is_fine")} if dl else None)
    doc = next(x for x in requests.get(f"{BASE}/api/documents", params={"vehicle_id": VEH}, headers=H, timeout=30).json() if x["id"] == doc_id)
    print("DOC statut =", doc["statut"], "| payee =", doc.get("payee"), "| montant =", doc.get("montant"),
          "| numero =", doc.get("numero"), "| fournisseur =", doc.get("fournisseur"), "| date_expiration =", doc.get("date_expiration"))
    print("DELETE validated fine →", requests.delete(f"{BASE}/api/documents/{doc_id}", headers=H, timeout=30).status_code)
elif step == "pay":
    doc_id = sys.argv[2]
    items, before = costs()
    r = requests.post(f"{BASE}/api/documents/{doc_id}/paid", headers=H, json={"payee": True}, timeout=30)
    print("PAID HTTP", r.status_code, "| statut =", r.json().get("statut"), "| paid_at =", r.json().get("paid_at"))
    items, after = costs()
    print(f"COSTS: total before {before} → after {after} | items for doc = {len([i for i in items if i['document_id'] == doc_id])}")
    dl, summ = deadlines(doc_id)
    print("DEADLINE after paid:", dl)
    doc = next(x for x in requests.get(f"{BASE}/api/documents", params={"vehicle_id": VEH}, headers=H, timeout=30).json() if x["id"] == doc_id)
    print("DOC present =", True, "| statut =", doc["statut"], "| payee =", doc.get("payee"))
