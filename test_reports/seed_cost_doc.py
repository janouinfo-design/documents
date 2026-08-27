import requests
from dotenv import dotenv_values
BASE = dotenv_values("/app/frontend/.env")["REACT_APP_BACKEND_URL"].rstrip("/")
s = requests.Session()
t = s.post(f"{BASE}/api/auth/login", json={"email": "admin@logitrak.ch", "password": "3a9218d1606b52e003383e52d7aea3d6"}).json()["token"]
s.headers.update({"Authorization": f"Bearer {t}"})

# revert the test document amount
r = s.patch(f"{BASE}/api/documents/aaebe0e2-4c5e-4bdf-b63b-ab7cfcf3800d", json={"montant": None, "frequence": None})
print("revert:", r.status_code, r.text[:200])
d = s.get(f"{BASE}/api/documents/aaebe0e2-4c5e-4bdf-b63b-ab7cfcf3800d").json()
print("after revert montant/frequence:", d.get("montant"), d.get("frequence"))

costs = s.get(f"{BASE}/api/costs").json()
print("totals:", costs["totals"], "year:", costs.get("year"))
print("items:", len(costs["items"]), "by_vehicle:", len(costs["by_vehicle"]))
print("sum all cout_annuel:", sum(i["cout_annuel"] for i in costs["items"]))
vehs = s.get(f"{BASE}/api/vehicles").json()
with_costs = {i["vehicle_id"] for i in costs["items"]}
empty = [v for v in vehs if v["id"] not in with_costs]
print("vehicles total:", len(vehs), "without any cost item:", [(v["id"], v.get("plaque")) for v in empty])
