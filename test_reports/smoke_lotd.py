"""Smoke lecture seule Lot D sur le tenant default (aucune écriture)."""
from dotenv import dotenv_values
import requests

API = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
env = dotenv_values("/app/backend/.env")
tok = requests.post(f"{API}/api/auth/login", json={"email": env["ADMIN_EMAIL"], "password": env["ADMIN_PASSWORD"]}, timeout=30).json()["token"]
H = {"Authorization": f"Bearer {tok}"}
d = requests.get(f"{API}/api/fines", headers=H, timeout=30).json()
print("fines total", d["total"], "totals", d["totals"])
print([(i.get("numero"), i["fine_status"], i["statut"], i.get("montant"), i["payee"], i.get("days_remaining"), i["attachments_count"]) for i in d["items"]])
s = requests.get(f"{API}/api/fines/stats", headers=H, timeout=30).json()
print("stats counts", s["counts"]); print("stats montants", s["montants"])
c = requests.get(f"{API}/api/costs", headers=H, timeout=30).json()
print("fines in costs", [(i["montant"], i.get("fine_status")) for i in c["items"] if i["business_category"] == "AMENDE"], "total", c["totals"] if "totals" in c else "")
dl = requests.get(f"{API}/api/deadlines", headers=H, timeout=30).json()
print("fine deadlines", [(i["label"], i["fine_status"], i["date"], i["statut"]) for i in dl["items"] if i.get("is_fine")])
for fmt in ("csv", "xlsx", "pdf"):
    r = requests.get(f"{API}/api/reports/amendes.{fmt}", headers=H, timeout=60)
    print(fmt, r.status_code, r.headers.get("content-type"), len(r.content))
