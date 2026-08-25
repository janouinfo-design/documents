/* ============================================================================
   AUDIT MONGODB PRODUCTION — STRICTEMENT LECTURE SEULE
   LOGITRAK Documents · à exécuter SUR LE VPS :

     cd ~/documents/deploy
     docker exec -i logitrak-fleet_mongo mongosh logitrak_fleet --quiet < audit-mongo-prod-readonly.js

   Ce script n'effectue AUCUNE écriture : uniquement getCollectionNames, find,
   countDocuments, getIndexes et agrégations en lecture. Aucun insert/update/
   delete/createIndex/drop. Les plaques sont masquées, aucun numéro de contrat
   ni donnée personnelle n'est affiché en clair.
   ========================================================================== */

print("=== BASE ===");
print("db: " + db.getName());

print("\n=== COLLECTIONS & COMPTAGES ===");
const colls = db.getCollectionNames().sort();
colls.forEach(c => print(c + ": " + db.getCollection(c).estimatedDocumentCount()));

const business = ["vehicles", "documents", "files", "inspections", "alerts",
                  "audit_logs", "vehicle_field_meta", "fuel_snapshots", "users",
                  "tenants", "tenant_integrations", "login_attempts"];

print("\n=== INDEX (lecture seule) ===");
business.forEach(c => {
  if (!colls.includes(c)) { print(c + ": COLLECTION ABSENTE"); return; }
  db.getCollection(c).getIndexes().forEach(i =>
    print(c + " :: " + i.name + " -> " + JSON.stringify(i.key) + " unique=" + (!!i.unique)));
});

print("\n=== TENANT_ID / VEHICLE_ID ===");
["vehicles","documents","files","inspections","alerts","audit_logs","vehicle_field_meta","users"].forEach(c => {
  if (!colls.includes(c)) return;
  const col = db.getCollection(c);
  const total = col.countDocuments({});
  const noT = col.countDocuments({tenant_id: {$exists: false}});
  const nullT = col.countDocuments({tenant_id: null});
  const emptyT = col.countDocuments({tenant_id: ""});
  let vtxt = "";
  if (["documents","files","inspections","alerts","vehicle_field_meta"].includes(c)) {
    vtxt = " | vehicle_id absent=" + col.countDocuments({vehicle_id: {$exists: false}})
         + " null=" + col.countDocuments({vehicle_id: null})
         + " vide=" + col.countDocuments({vehicle_id: ""});
  }
  print(c + ": total=" + total + " sans_tenant=" + noT + " tenant_null=" + nullT
        + " tenant_vide=" + emptyT + vtxt);
});

print("\n=== VEHICLES — SIGNATURES DEMO (seed prouvé) & ASSURANCE/LEASING ===");
const vids = new Set();
let demoLsg = 0, demoPol = 0, demoCom = 0, unsplash = 0, leasingFilled = 0, assFilled = 0;
db.vehicles.find({}, {id:1, plaque:1, leasing:1, assurance:1, photo_url:1}).forEach(v => {
  vids.add(v.id);
  const lc = ((v.leasing||{}).numero_contrat||"") + "";
  const po = ((v.assurance||{}).numero_police||"") + "";
  const cm = (((v.leasing||{}).commentaires||"") + "").includes("Données de démonstration");
  if (lc.startsWith("LSG-2022-45")) demoLsg++;
  if (po.startsWith("POL-78")) demoPol++;
  if (cm) demoCom++;
  if (((v.photo_url||"")+"").includes("unsplash")) unsplash++;
  if ((v.leasing||{}).date_fin) leasingFilled++;
  if ((v.assurance||{}).date_echeance) assFilled++;
  const p = (v.plaque||"") + "";
  const masked = p.length > 5 ? p.slice(0,3) + "…" + p.slice(-2) : p.slice(0,2) + "…";
  const sig = [];
  if (lc.startsWith("LSG-2022-45")) sig.push("LSG-2022-45**");
  if (po.startsWith("POL-78")) sig.push("POL-78****");
  if (cm) sig.push("commentaire démo");
  print("  " + v.id + " | plaque: " + masked + " | "
        + (sig.length ? "DEMO_PROUVEE: " + sig.join("; ") : "aucune signature seed"));
});
print("TOTAUX — LSG-2022-45xx: " + demoLsg + " | POL-78xxxx: " + demoPol
      + " | commentaire démo: " + demoCom + " | photo unsplash: " + unsplash);
print("leasing.date_fin renseigné: " + leasingFilled + " | assurance.date_echeance: " + assFilled);

print("\n=== DOCUMENTS — structure & état ===");
if (colls.includes("documents")) {
  const dtot = db.documents.countDocuments({});
  print("total: " + dtot
        + " | actifs: " + db.documents.countDocuments({is_deleted: false})
        + " | soft-supprimés: " + db.documents.countDocuments({is_deleted: true}));
  ["folder", "document_type", "extraction_status", "source"].forEach(f => {
    const agg = db.documents.aggregate([{$group: {_id: "$" + f, n: {$sum: 1}}}]).toArray();
    print(f + ": " + agg.map(x => (x._id === null ? "null" : x._id) + "=" + x.n).join(", "));
  });
  print("avec validated_at: " + db.documents.countDocuments({validated_at: {$exists: true}}));
  print("avec extracted_fields: " + db.documents.countDocuments({extracted_fields: {$exists: true, $ne: []}}));
}

print("\n=== ORPHELINS (lecture seule) ===");
const vidArr = Array.from(vids);
["documents","files","inspections","vehicle_field_meta"].forEach(c => {
  if (!colls.includes(c)) return;
  const n = db.getCollection(c).countDocuments({vehicle_id: {$nin: vidArr.concat(["misc"])}});
  print(c + " orphelins (vehicle_id inexistant): " + n);
});
if (colls.includes("alerts"))
  print("alerts orphelines: " + db.alerts.countDocuments({vehicle_id: {$nin: vidArr, $ne: null, $exists: true}}));

print("\n=== ALERTES ===");
if (colls.includes("alerts")) {
  print("total: " + db.alerts.countDocuments({}));
  db.alerts.aggregate([{$group: {_id: "$status", n: {$sum: 1}}}]).toArray()
    .forEach(x => print("status " + x._id + ": " + x.n));
  db.alerts.aggregate([{$group: {_id: "$kind", n: {$sum: 1}}}]).toArray()
    .forEach(x => print("kind " + (x._id === null ? "null" : x._id) + ": " + x.n));
}

print("\n=== VEHICLE_FIELD_META (validations OCR/ASTRA) ===");
if (colls.includes("vehicle_field_meta")) {
  db.vehicle_field_meta.aggregate([{$group: {_id: "$source", n: {$sum: 1}}}]).toArray()
    .forEach(x => print("source " + x._id + ": " + x.n));
}

print("\n=== AUDIT_LOGS — actions ===");
if (colls.includes("audit_logs")) {
  db.audit_logs.aggregate([{$group: {_id: "$action", n: {$sum: 1}}}]).toArray()
    .forEach(x => print(x._id + ": " + x.n));
}

print("\n=== USERS (comptage uniquement, aucun email affiché) ===");
if (colls.includes("users")) print("users: " + db.users.countDocuments({}));
else print("users: COLLECTION ABSENTE (version pré-auth)");

print("\n=== FIN — AUCUNE ÉCRITURE EFFECTUÉE ===");
