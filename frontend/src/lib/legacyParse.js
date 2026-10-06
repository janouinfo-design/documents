// Analyse d'une liste de véhicules Journal (JSON ou CSV) — aucun identifiant n'est inventé côté client.
const ALIASES = {
  legacy_vehicle_id: ["legacy_vehicle_id", "id", "vehicle_id", "journal_id"],
  plate: ["plate", "plaque", "immatriculation"],
  vin: ["vin"],
  navixy_tracker_id: ["navixy_tracker_id", "tracker_id", "tracker"],
  navixy_vehicle_id: ["navixy_vehicle_id"],
  model: ["model", "modele", "modèle", "label", "name"],
};

const INT_FIELDS = new Set(["navixy_tracker_id", "navixy_vehicle_id"]);

function pick(row, field) {
  for (const a of ALIASES[field]) {
    const k = Object.keys(row).find((key) => key.trim().toLowerCase() === a);
    if (k !== undefined && row[k] !== null && String(row[k]).trim() !== "") return String(row[k]).trim();
  }
  return null;
}

function normalize(row) {
  const out = {};
  for (const field of Object.keys(ALIASES)) {
    const v = pick(row, field);
    if (v === null) continue;
    if (INT_FIELDS.has(field)) {
      const n = Number(v);
      if (Number.isInteger(n)) out[field] = n;
    } else out[field] = v;
  }
  return out;
}

export function parseLegacyVehicles(text) {
  const raw = (text || "").trim();
  if (!raw) return { vehicles: [], errors: ["Aucune donnée saisie"] };
  let rows;
  if (raw.startsWith("[") || raw.startsWith("{")) {
    try {
      const parsed = JSON.parse(raw);
      rows = Array.isArray(parsed) ? parsed : parsed.vehicles || [parsed];
    } catch {
      return { vehicles: [], errors: ["JSON invalide"] };
    }
  } else {
    const lines = raw.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const sep = (lines[0].match(/;/g) || []).length >= (lines[0].match(/,/g) || []).length ? ";" : ",";
    const header = lines[0].split(sep).map((h) => h.trim());
    rows = lines.slice(1).map((l) => {
      const cells = l.split(sep);
      return Object.fromEntries(header.map((h, i) => [h, (cells[i] ?? "").trim()]));
    });
  }
  const errors = [];
  const vehicles = [];
  rows.forEach((r, i) => {
    const v = normalize(r || {});
    if (!v.legacy_vehicle_id) errors.push(`Ligne ${i + 1} : legacy_vehicle_id manquant`);
    else vehicles.push(v);
  });
  return { vehicles, errors };
}
