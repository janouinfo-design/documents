import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Pencil, Loader2, ScrollText, Calendar, Weight, Users,
  Fuel, Gauge, Zap, Leaf, Hash, TrendingUp, Database,
} from "lucide-react";
import { updateVehicle, getFieldMeta } from "@/lib/api";
import { dateFr, fmtNum } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import DocFolderSection from "@/components/DocFolderSection";
import DocumentScanCard from "@/components/DocumentScanCard";
import TechnicalEnrichDialog from "@/components/TechnicalEnrichDialog";

const CG_FIELDS = ["date_mise_circulation", "poids_total", "nombre_places"];
const TECH_FIELDS = [
  "type_carburant", "cylindree_cm3", "puissance_kw", "poids_vide", "categorie",
  "co2_g_km", "co2_norme", "conso_officielle_l_100km", "conso_officielle_norme",
  "capacite_reservoir_l", "conso_reelle_l_100km", "variante", "numero_homologation",
];

const NORMES = ["WLTP", "NEDC"];
const REELLE_SOURCES = {
  can: "CAN",
  fms: "FMS",
  obd: "OBD",
  fuel_transactions: "Pleins carburant",
  manual: "Manuelle",
};

const pick = (vehicle) => ({
  ...Object.fromEntries(CG_FIELDS.map((k) => [k, (vehicle.carte_grise || {})[k] ?? ""])),
  ...Object.fromEntries(TECH_FIELDS.map((k) => [k, vehicle[k] ?? ""])),
});

export default function CarteGriseTab({ vehicle, onSaved, docs, refetchDocs }) {
  const c = vehicle.carte_grise || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(vehicle));
  const [saving, setSaving] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const [swissMeta, setSwissMeta] = useState(null);
  const scanValidatedRef = useRef(false);

  useEffect(() => {
    if (scanValidatedRef.current && vehicle.numero_homologation) {
      scanValidatedRef.current = false;
      toast.info("N° d'homologation détecté — recherche dans la base officielle ASTRA/OFROU…");
      setTechOpen(true);
    }
  }, [vehicle.numero_homologation]);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  useEffect(() => {
    let on = true;
    getFieldMeta(vehicle.id)
      .then((metas) => {
        if (!on) return;
        const m = (metas || [])
          .filter((x) => ["astra_tas", "astra_tg", "astra_edatenblatt", "swisscarinfo"].includes(x.provider))
          .sort((a, b) => (b.retrieved_at || "").localeCompare(a.retrieved_at || ""))[0];
        setSwissMeta(m || null);
      })
      .catch(() => {});
    return () => { on = false; };
  }, [vehicle.id, vehicle.updated_at]);

  const litres = vehicle.cylindree_cm3 ? `${fmtNum(vehicle.cylindree_cm3)} cm³ — ${(vehicle.cylindree_cm3 / 1000).toFixed(1)} L` : "—";
  const reelleFromCan = vehicle.conso_reelle_source === "can";
  const off = Number(vehicle.conso_officielle_l_100km) || 0;
  const reelle = Number(vehicle.conso_reelle_l_100km) || 0;
  const ecart = off > 0 && reelle > 0 ? ((reelle - off) / off) * 100 : null;
  const cap = Number(vehicle.capacite_reservoir_l) || 0;
  const niveau = vehicle.carburant_niveau_pct;
  const niveauTxt = niveau != null
    ? `${niveau} %${cap > 0 ? ` ≈ ${((niveau / 100) * cap).toFixed(1)} L` : ""}${vehicle.carburant_niveau_date ? ` (${dateFr(vehicle.carburant_niveau_date)})` : ""}`
    : "—";

  const save = async () => {
    setSaving(true);
    try {
      const reelleForm = Number(form.conso_reelle_l_100km) || 0;
      await updateVehicle(vehicle.id, {
        type_carburant: form.type_carburant || "",
        cylindree_cm3: Number(form.cylindree_cm3) || 0,
        puissance_kw: Number(form.puissance_kw) || 0,
        poids_vide: Number(form.poids_vide) || 0,
        categorie: form.categorie || "",
        co2_g_km: Number(form.co2_g_km) || 0,
        co2_norme: form.co2_norme || "",
        conso_officielle_l_100km: Number(form.conso_officielle_l_100km) || 0,
        conso_officielle_norme: form.conso_officielle_norme || "",
        capacite_reservoir_l: Number(form.capacite_reservoir_l) || 0,
        ...(!reelleFromCan
          ? {
              conso_reelle_l_100km: reelleForm,
              conso_reelle_source: reelleForm > 0 ? "manual" : "unavailable",
            }
          : {}),
        variante: form.variante || "",
        numero_homologation: form.numero_homologation || "",
        carte_grise: {
          date_mise_circulation: form.date_mise_circulation || null,
          poids_total: Number(form.poids_total) || 0,
          nombre_places: Number(form.nombre_places) || 0,
        },
      });
      toast.success("Données véhicule enregistrées");
      onSaved?.();
      setEdit(false);
    } catch {
      toast.error("Erreur lors de l'enregistrement");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="space-y-5">
      <DocumentScanCard
        vehicle={vehicle}
        docType="permis_circulation"
        testIdPrefix="cg-scan"
        title="Scan intelligent — Permis de circulation"
        description="Photographiez ou importez le permis : plaque, VIN, carburant, cylindrée, puissance, poids… sont extraits puis soumis à votre validation."
        onValidated={() => { scanValidatedRef.current = !vehicle.numero_homologation; onSaved?.(); refetchDocs?.(); }}
      />

      {edit ? (
        <SectionCard title="Modifier carte grise & données moteur" testId="carte-grise-edit">
          <p className="mb-3 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Carte grise</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              ["date_mise_circulation", "Mise en circulation", "date"],
              ["poids_vide", "Poids à vide (kg)", "number"],
              ["poids_total", "Poids total (kg)", "number"],
              ["nombre_places", "Nombre de places", "number"],
              ["categorie", "Catégorie"],
              ["variante", "Variante / type"],
              ["numero_homologation", "N° homologation"],
            ].map(([k, label, type]) => (
              <FormRow key={k} label={label}>
                <Input data-testid={`cg-${k}`} type={type || "text"} value={form[k] || ""} onChange={(e) => set(k, e.target.value)} />
              </FormRow>
            ))}
          </div>
          <p className="mb-3 mt-6 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Moteur & consommation</p>
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
            {[
              ["type_carburant", "Carburant"],
              ["cylindree_cm3", "Cylindrée (cm³)", "number"],
              ["puissance_kw", "Puissance (kW)", "number"],
              ["co2_g_km", "CO₂ (g/km)", "number"],
              ["conso_officielle_l_100km", "Conso officielle (L/100 km)", "number"],
              ["capacite_reservoir_l", "Capacité réservoir (L)", "number"],
            ].map(([k, label, type]) => (
              <FormRow key={k} label={label}>
                <Input data-testid={`cg-${k}`} type={type || "text"} value={form[k] || ""} onChange={(e) => set(k, e.target.value)} />
              </FormRow>
            ))}
            <FormRow label="Norme conso officielle">
              <Select value={form.conso_officielle_norme || undefined} onValueChange={(v) => set("conso_officielle_norme", v)}>
                <SelectTrigger data-testid="cg-conso_officielle_norme"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{NORMES.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
            <FormRow label="Norme CO₂">
              <Select value={form.co2_norme || undefined} onValueChange={(v) => set("co2_norme", v)}>
                <SelectTrigger data-testid="cg-co2_norme"><SelectValue placeholder="—" /></SelectTrigger>
                <SelectContent>{NORMES.map((n) => <SelectItem key={n} value={n}>{n}</SelectItem>)}</SelectContent>
              </Select>
            </FormRow>
            <FormRow label={reelleFromCan ? "Conso réelle — mesurée via CAN" : "Conso réelle (L/100 km) — saisie manuelle"}>
              <Input
                data-testid="cg-conso_reelle_l_100km"
                type="number"
                disabled={reelleFromCan}
                value={form.conso_reelle_l_100km || ""}
                onChange={(e) => set("conso_reelle_l_100km", e.target.value)}
                placeholder={reelleFromCan ? "Gérée automatiquement" : ""}
              />
            </FormRow>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
            <Button data-testid="cg-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
            </Button>
          </div>
        </SectionCard>
      ) : (
        <>
          <SectionCard
            title="Carte grise"
            description="Données lues sur le permis de circulation"
            testId="carte-grise-view"
            action={
              <Button variant="outline" size="sm" onClick={() => { setForm(pick(vehicle)); setEdit(true); }} data-testid="cg-edit-btn" className="gap-1.5">
                <Pencil className="h-3.5 w-3.5" /> Modifier
              </Button>
            }
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Plaque" value={vehicle.plaque} icon={ScrollText} />
              <Stat label="VIN" value={vehicle.vin} />
              <Stat label="Mise en circulation" value={dateFr(c.date_mise_circulation)} icon={Calendar} />
              <Stat label="Poids à vide" value={vehicle.poids_vide ? `${fmtNum(vehicle.poids_vide)} kg` : "—"} icon={Weight} />
              <Stat label="Poids total" value={c.poids_total ? `${fmtNum(c.poids_total)} kg` : "—"} icon={Weight} />
              <Stat label="Nombre de places" value={c.nombre_places || "—"} icon={Users} />
              <Stat label="Catégorie" value={vehicle.categorie || "—"} />
              <Stat label="Variante / type" value={vehicle.variante || "—"} />
              <Stat label="N° homologation" value={vehicle.numero_homologation || "—"} icon={Hash} />
            </div>
          </SectionCard>

          <SectionCard
            title="Données moteur & consommation"
            description="Officielle = homologation · Réelle = uniquement mesurée (CAN/OBD) ou saisie manuelle marquée"
            testId="moteur-conso"
            action={
              <Button variant="outline" size="sm" onClick={() => setTechOpen(true)} data-testid="tech-enrich-btn" className="gap-1.5">
                <Database className="h-3.5 w-3.5" /> Base technique
              </Button>
            }
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Stat label="Carburant" value={vehicle.type_carburant || "—"} icon={Fuel} />
              <Stat label="Cylindrée" value={litres} icon={Gauge} />
              <Stat label="Puissance" value={vehicle.puissance_kw ? `${vehicle.puissance_kw} kW` : "—"} icon={Zap} />
              <Stat
                label="CO₂ officiel"
                value={vehicle.co2_g_km ? `${vehicle.co2_g_km} g/km${vehicle.co2_norme ? ` · ${vehicle.co2_norme}` : ""}` : "—"}
                icon={Leaf}
              />
              <Stat
                label="Conso officielle"
                value={off > 0 ? `${off} L/100 km${vehicle.conso_officielle_norme ? ` · ${vehicle.conso_officielle_norme}` : ""}` : "—"}
                icon={Fuel}
              />
              <div data-testid="conso-reelle-stat">
                <Stat
                  label="Conso réelle"
                  value={reelle > 0 ? `${reelle} L/100 km · Source : ${REELLE_SOURCES[vehicle.conso_reelle_source] || "—"}` : "Données insuffisantes"}
                  icon={Gauge}
                />
              </div>
              <Stat
                label="Écart officielle / réelle"
                value={ecart != null ? `${ecart > 0 ? "+" : ""}${ecart.toFixed(1)} %` : "—"}
                icon={TrendingUp}
              />
              <Stat label="Capacité réservoir" value={cap > 0 ? `${cap} L` : "—"} />
              <Stat label="Niveau carburant" value={niveauTxt} icon={Fuel} />
            </div>
            {swissMeta && (
              <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-400" data-testid="tech-provenance-note">
                Source : {swissMeta.provider === "swisscarinfo" ? "SwissCarInfo — données officielles OFROU" : "Base officielle ASTRA/OFROU (copie locale)"} · dernière récupération le {dateFr((swissMeta.retrieved_at || "").slice(0, 10))}
              </p>
            )}
          </SectionCard>
        </>
      )}

      <SectionCard title="Documents carte grise" description="Recto · Verso · Historique" testId="carte-grise-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Carte grise" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>

      <TechnicalEnrichDialog open={techOpen} onOpenChange={setTechOpen} vehicle={vehicle} onApplied={() => onSaved?.()} />
    </div>
  );
}
