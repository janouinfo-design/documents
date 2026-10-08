"""Lot G — inventaire READ-ONLY du tenant `lotg-ui-test` après testing agent (iteration 47). Aucune écriture."""
import json
import os
import sys
from collections import Counter
from pathlib import Path

from dotenv import load_dotenv
from pymongo import MongoClient

load_dotenv("/app/backend/.env")
db = MongoClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
T = "lotg-ui-test"
OUT = Path("/app/test_reports/lotg_inventory_post_agent.json")
P = {"_id": 0}

out = {"tenant": T, "collections": {}, "statements": [], "lines": {}, "transactions": {}, "reconciliations": [], "audit": {}, "locks_table": []}

for c in sorted(db.list_collection_names()):
    n = db[c].count_documents({"tenant_id": T}) if c != "tenants" else db[c].count_documents({"id": T})
    if n:
        out["collections"][c] = n

lines_by_st = Counter()
blockers_by_st = {}
for ln in db.fuel_statement_lines.find({"tenant_id": T}, P):
    lines_by_st[ln["statement_id"]] += 1
    blockers_by_st.setdefault(ln["statement_id"], Counter()).update(ln.get("blockers") or [])
out["lines"] = {"total": sum(lines_by_st.values()), "by_statement": dict(lines_by_st), "blockers_by_statement": {k: dict(v) for k, v in blockers_by_st.items()}}

txs = list(db.fuel_transactions.find({"tenant_id": T}, P))
locked = [t for t in txs if t.get("locked")]
unlocked = [t for t in txs if not t.get("locked")]
out["transactions"] = {
    "total": len(txs), "locked_true": len(locked), "locked_false": len(unlocked),
    "locked_list": [{"transaction_id": t["id"], "statement_id": t.get("statement_id"), "statement_number": t.get("statement_number"), "locked_at": t.get("locked_at"),
                     "document_id": t.get("source_document_id"), "vehicle_id": t.get("vehicle_id"), "date": t.get("date"), "montant": t.get("montant"), "devise": t.get("devise")} for t in sorted(locked, key=lambda x: (x.get("statement_number") or "", x.get("date") or ""))],
    "unlocked_list": [{"transaction_id": t["id"], "vehicle_id": t.get("vehicle_id"), "date": t.get("date"), "montant": t.get("montant"), "devise": t.get("devise"), "statement_id": t.get("statement_id")} for t in sorted(unlocked, key=lambda x: x.get("date") or "")],
}

sts = list(db.fuel_statements.find({"tenant_id": T}, P).sort("number", 1))
st_by_id = {s["id"]: s for s in sts}
for s in sts:
    tot = s.get("totals") or {}
    line_tx = [ln["transaction_id"] for ln in db.fuel_statement_lines.find({"tenant_id": T, "statement_id": s["id"]}, {"_id": 0, "transaction_id": 1})]
    tx_locked_by_this = [t for t in locked if t.get("statement_id") == s["id"]]
    kind = "correctif" if s.get("type") == "correctif" else ("cloture_exception" if s.get("close_exception") else ("cloture_normal" if s.get("status") == "cloture" else "brouillon"))
    out["statements"].append({
        "id": s["id"], "number": s.get("number"), "type": s.get("type"), "kind": kind, "parent_statement_id": s.get("parent_statement_id"), "parent_number": s.get("parent_number"),
        "period_month": s.get("period_month"), "scope": s.get("scope"), "status": s.get("status"), "lines_count": lines_by_st.get(s["id"], 0),
        "blocker_count": tot.get("blocker_count"), "blocked_line_count": tot.get("blocked_line_count"), "blockers_by_type": tot.get("blockers_by_type"),
        "close_exception": bool(s.get("close_exception")), "exception_reason": (s.get("exception") or {}).get("reason"), "declared": s.get("declared"),
        "closed_at": s.get("closed_at"), "closed_by": s.get("closed_by"), "snapshot_count": s.get("snapshot_count"), "history_events": [h.get("event") for h in s.get("history") or []],
    })
    # locks table
    if s.get("status") == "cloture":
        expect = set(line_tx)
        got = {t["id"] for t in tx_locked_by_this}
        verdict = "PASS" if expect == got and all(t.get("locked_at") and t.get("statement_id") for t in tx_locked_by_this) else "FAIL"
        detail = f"snapshot={len(expect)} locked_by_stmt={len(got)} missing={sorted(expect - got)} extra={sorted(got - expect)}"
    else:
        got = {t["id"] for t in locked if t["id"] in set(line_tx)}
        verdict = "PASS" if not got else "FAIL"
        detail = f"snapshot={len(line_tx)} tx_locked_in_snapshot={len(got)}"
    row = {"statement": s.get("number"), "type": s.get("type"), "status": s.get("status"), "close_exception": bool(s.get("close_exception")), "tx_snapshot": len(line_tx), "tx_locked": len(tx_locked_by_this) if s.get("status") == "cloture" else len(got), "verdict": verdict, "detail": detail}
    if s.get("type") == "correctif" and s.get("parent_statement_id"):
        parent_tx = {ln["transaction_id"] for ln in db.fuel_statement_lines.find({"tenant_id": T, "statement_id": s["parent_statement_id"]}, {"_id": 0, "transaction_id": 1})}
        inter = parent_tx & set(line_tx)
        row["parent_intersection"] = len(inter)
        if inter:
            row["verdict"] = "FAIL"
        row["detail"] += f" parent_intersection={len(inter)}"
    out["locks_table"].append(row)

for r in db.fuel_reconciliations.find({"tenant_id": T}, P):
    j = r.get("justification") or {}
    out["reconciliations"].append({"id": r["id"], "period_month": r.get("period_month"), "vehicle_id": r.get("vehicle_id"), "justification_reason": j.get("reason"), "justified_by": j.get("by"),
                                   "status_at": j.get("status_at"), "source_consumption_at": j.get("source_consumption_at"), "ecart_l_at": j.get("ecart_l_at"), "history_len": len(r.get("history") or [])})

auds = list(db.audit_logs.find({"tenant_id": T}, P))
by_action = Counter(a.get("action") for a in auds)
by_entity_action = Counter(f"{a.get('entity')}/{a.get('action')}" for a in auds)
downloads = [a for a in auds if a.get("action") == "download"]
sha_ok = [a for a in downloads if a.get("sha256")]
out["audit"] = {
    "total": len(auds), "by_action": dict(by_action), "by_entity_action": dict(sorted(by_entity_action.items())),
    "lot_g_events": {k: by_entity_action.get(k, 0) for k in sorted(by_entity_action) if k.split("/")[0] in ("fuel_statement", "fuel_reconciliation", "fuel_export", "tenant_settings", "fuel_statement_export", "fuel_reconciliations_export", "fuel_transactions_export") or k.split("/")[1] in ("close", "close_exception", "recalculate", "justify", "declared", "download", "settings")},
    "downloads": len(downloads), "downloads_with_sha256": len(sha_ok),
    "download_by_type_format": dict(Counter(f"{a.get('export_type')}:{a.get('format')}" for a in downloads)),
    "download_samples": [{"export_type": a.get("export_type"), "format": a.get("format"), "user": a.get("user"), "at": a.get("created_at"), "size": a.get("size"), "rows": a.get("rows"), "statement_id": a.get("statement_id"), "period_month": a.get("period_month"), "sha256_prefix": (a.get("sha256") or "")[:16]} for a in sorted(downloads, key=lambda x: x.get("created_at") or "")],
}

OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False, default=str))
print("INVENTORY →", OUT)
print(json.dumps(out["collections"], indent=1))
print("STATEMENTS:")
for s in out["statements"]:
    print(f"  {s['number']} | {s['type']} | {s['kind']} | parent={s['parent_number']} | {s['period_month']} | scope={s['scope']} | status={s['status']} | lines={s['lines_count']} | blockers={s['blocker_count']}/{s['blocked_line_count']} {s['blockers_by_type']} | exc={s['close_exception']} | declared={s['declared']} | closed_at={s['closed_at']} by={s['closed_by']}")
print("LINES:", out["lines"]["total"], out["lines"]["by_statement"])
print("BLOCKERS BY STATEMENT:", out["lines"]["blockers_by_statement"])
print("TX:", {k: v for k, v in out["transactions"].items() if k in ("total", "locked_true", "locked_false")})
print("LOCKED:")
for t in out["transactions"]["locked_list"]:
    print(f"  {t['transaction_id']} | {t['statement_number']} {t['statement_id']} | locked_at={t['locked_at']} | doc={t['document_id']} | veh={t['vehicle_id']} | {t['date']} {t['montant']} {t['devise']}")
print("UNLOCKED:")
for t in out["transactions"]["unlocked_list"]:
    print(f"  {t['transaction_id']} | veh={t['vehicle_id']} | {t['date']} {t['montant']} {t['devise']} | statement_id={t['statement_id']}")
print("LOCKS TABLE:")
for r in out["locks_table"]:
    print("  ", r)
print("RECONCILIATIONS:", json.dumps(out["reconciliations"], ensure_ascii=False, default=str))
print("AUDIT total:", out["audit"]["total"], "by_action:", out["audit"]["by_action"])
print("AUDIT by entity/action:", out["audit"]["by_entity_action"])
print("DOWNLOADS:", out["audit"]["downloads"], "with sha256:", out["audit"]["downloads_with_sha256"])
for d in out["audit"]["download_samples"]:
    print("   ", d)
