import { useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  Pencil, Loader2, ScrollText, Calendar, Weight, Users,
  Fuel, Gauge, Zap, Leaf, Hash, TrendingUp, Database, Sparkles,
} from "lucide-react";
import { updateVehicle, getFieldMeta, revertTechnicalField } from "@/lib/api";
import { notifyNavixyPush } from "@/lib/navixyFeedback";
import { dateFr, fmtNum } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectValue, SelectContent, SelectItem } from "@/components/ui/select";
import DocFolderSection from "@/components/DocFolderSection";
import DocumentScanCard from "@/components/DocumentScanCard";
import TechnicalEnrichDialog from "@/components/TechnicalEnrichDialog";
import ReservoirSuggestDialog from "@/components/ReservoirSuggestDialog";
import ConsoSuggestDialog from "@/components/ConsoSuggestDialog";
import Co2SuggestDialog from "@/components/Co2SuggestDialog";
import { useAuth } from "@/context/AuthContext";

const CG_FIELDS = [
  "date_mise_circulation", "poids_total", "nombre_places", "couleur",
  "numero_matricule", "carrosserie", "charge_utile", "charge_remorquable",
  "charge_toit", "code_emissions", "detenteur", "adresse_detenteur",
  "date_emission", "lieu_emission",
];
const TECH_FIELDS = [
  "type_carburant", "cylindree_cm3", "puissance_kw", "poids_vide", "categorie",
  "co2_g_km", "co2_norme", "conso_officielle_l_100km", "conso_officielle_norme",
  "capacite_reservoir_l", "conso_reelle_l_100km", "variante", "numero_homologation",
  "conso_officielle_kwh_100km", "batterie_capacite_brute_kwh", "batterie_capacite_utile_kwh", "autonomie_km",
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
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(vehicle));
  const [saving, setSaving] = useState(false);
  const [techOpen, setTechOpen] = useState(false);
  const [reservoirOpen, setReservoirOpen] = useState(false);
  const [consoOpen, setConsoOpen] = useState(false);
  const [co2Open, setCo2Open] = useState(false);
  const [swissMeta, setSwissMeta] = useState(null);
  const [astraHistory, setAstraHistory] = useState([]);
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
        const astra = (metas || [])
          .filter((x) => ["astra_tas", "astra_tg", "astra_edatenblatt", "swisscarinfo"].includes(x.provider));
        const m = astra.sort((a, b) => (b.retrieved_at || "").localeCompare(a.retrieved_at || ""))[0];
        setSwissMeta(m || null);
        setAstraHistory(astra.filter((x) => Object.prototype.hasOwnProperty.call(x, "previous_value")));
      })
      .catch(() => {});
    return () => { on = false; };
  }, [vehicle.id, vehicle.updated_at]);

  const revertField = async (h) => {
    try {
      await revertTechnicalField(vehicle.id, h.field);
      toast.success(`${h.label} : valeur précédente rétablie`);
      onSaved?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Impossible de rétablir la valeur");
    }
  };

  const litres = vehicle.cylindree_cm3 ? `${fmtNum(vehicle.cylindree_cm3)} cm³ — ${(vehicle.cylindree_cm3 / 1000).toFixed(1)} L` : "—";
  const reelleFromCan = vehicle.conso_reelle_source === "can";
  const off = Number(vehicle.conso_officielle_l_100km) || 0;
  const offKwh = Number(vehicle.conso_officielle_kwh_100km) || 0;
  const battBrute = Number(vehicle.batterie_capacite_brute_kwh) || 0;
  const battUtile = Number(vehicle.batterie_capacite_utile_kwh) || 0;
  const autonomie = Number(vehicle.autonomie_km) || 0;
  const offTxt = [off > 0 ? `${off} L/100 km` : null, offKwh > 0 ? `${offKwh} kWh/100 km` : null]
    .filter(Boolean).join(" · ");
  const battTxt = battBrute > 0 || battUtile > 0
    ? [battBrute > 0 ? `${battBrute} kWh brute` : null, battUtile > 0 ? `${battUtile} kWh utile` : null].filter(Boolean).join(" · ")
    : "—";
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
      const res = await updateVehicle(vehicle.id, {
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
        conso_officielle_kwh_100km: Number(form.conso_officielle_kwh_100km) || null,
        batterie_capacite_brute_kwh: Number(form.batterie_capacite_brute_kwh) || null,
        batterie_capacite_utile_kwh: Number(form.batterie_capacite_utile_kwh) || null,
        autonomie_km: Number(form.autonomie_km) || null,
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
          couleur: form.couleur || null,
          numero_matricule: form.numero_matricule || null,
          carrosserie: form.carrosserie || null,
          charge_utile: Number(form.charge_utile) || null,
          charge_remorquable: Number(form.charge_remorquable) || null,
          charge_toit: Number(form.charge_toit) || null,
          code_emissions: form.code_emissions || null,
          detenteur: form.detenteur || null,
          adresse_detenteur: form.adresse_detenteur || null,
          date_emission: form.date_emission || null,
          lieu_emission: form.lieu_emission || null,
        },
      });
      toast.success("Données véhicule enregistrées");
      onSaved?.();
      setEdit(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Erreur lors de l'enregistrement");
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
              ["charge_utile", "Charge utile (kg)", "number"],
              ["charge_remorquable", "Charge remorquable (kg)", "number"],
              ["charge_toit", "Charge toit (kg)", "number"],
              ["nombre_places", "Nombre de places", "number"],
              ["couleur", "Couleur"],
              ["categorie", "Genre / catégorie"],
              ["carrosserie", "Carrosserie"],
              ["variante", "Variante / type"],
              ["numero_homologation", "Réception par type / homologation"],
              ["numero_matricule", "N° matricule"],
              ["code_emissions", "Code émissions"],
              ["detenteur", "Détenteur"],
              ["adresse_detenteur", "Adresse détenteur"],
              ["date_emission", "Date d'émission", "date"],
              ["lieu_emission", "Lieu d'émission"],
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
              ["conso_officielle_kwh_100km", "Conso officielle (kWh/100 km)", "number"],
              ["batterie_capacite_brute_kwh", "Batterie brute (kWh)", "number"],
              ["batterie_capacite_utile_kwh", "Batterie utile (kWh)", "number"],
              ["autonomie_km", "Autonomie de référence (km)", "number"],
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
            description="Données lues sur le permis de circulation — valeurs canoniques validées uniquement"
            testId="carte-grise-view"
            action={
              <Button variant="outline" size="sm" onClick={() => { setForm(pick(vehicle)); setEdit(true); }} data-testid="cg-edit-btn" className="gap-1.5">
                <Pencil className="h-3.5 w-3.5" /> Modifier
              </Button>
            }
          >
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="cg-group-identification">
              <Stat label="Plaque" value={vehicle.plaque} icon={ScrollText} />
              <Stat label="VIN" value={vehicle.vin} />
              <Stat label="N° matricule" value={c.numero_matricule || "—"} icon={Hash} />
              <Stat label="Réception par type / homologation" value={vehicle.numero_homologation || "—"} icon={Hash} />
            </div>
            <p className="mb-2 mt-5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Véhicule</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="cg-group-vehicule">
              <Stat label="Genre / catégorie" value={vehicle.categorie || "—"} />
              <Stat label="Carrosserie" value={c.carrosserie || "—"} />
              <Stat label="Couleur" value={c.couleur || "—"} />
              <Stat label="Variante / type" value={vehicle.variante || "—"} />
              <Stat label="Mise en circulation" value={dateFr(c.date_mise_circulation)} icon={Calendar} />
            </div>
            <p className="mb-2 mt-5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Technique</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="cg-group-technique">
              <Stat label="Poids à vide" value={vehicle.poids_vide ? `${fmtNum(vehicle.poids_vide)} kg` : "—"} icon={Weight} />
              <Stat label="Charge utile" value={c.charge_utile ? `${fmtNum(c.charge_utile)} kg` : "—"} icon={Weight} />
              <Stat label="Poids total" value={c.poids_total ? `${fmtNum(c.poids_total)} kg` : "—"} icon={Weight} />
              <Stat label="Charge remorquable" value={c.charge_remorquable ? `${fmtNum(c.charge_remorquable)} kg` : "—"} icon={Weight} />
              <Stat label="Charge sur le toit" value={c.charge_toit ? `${fmtNum(c.charge_toit)} kg` : "—"} icon={Weight} />
              <Stat label="Nombre de places" value={c.nombre_places || "—"} icon={Users} />
              <Stat label="Code émissions" value={c.code_emissions || "—"} />
            </div>
            <p className="mb-2 mt-5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400">Administratif</p>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3" data-testid="cg-group-administratif">
              <Stat label="Détenteur" value={c.detenteur || "—"} />
              <Stat label="Adresse détenteur" value={c.adresse_detenteur || "—"} />
              <Stat
                label="Émission du permis"
                value={c.date_emission ? `${c.lieu_emission ? `${c.lieu_emission}, ` : ""}${dateFr(c.date_emission)}` : (c.lieu_emission || "—")}
                icon={Calendar}
              />
              <Stat label="Dernière expertise" value={dateFr((vehicle.controle_technique || {}).date_dernier)} icon={Calendar} />
              <Stat label="Assureur" value={(vehicle.assurance || {}).compagnie || "—"} />
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
              <div className="relative" data-testid="co2-officiel-stat">
                <Stat
                  label="CO₂ officiel"
                  value={vehicle.co2_g_km ? `${vehicle.co2_g_km} g/km${vehicle.co2_norme ? ` · ${vehicle.co2_norme}` : ""}` : "—"}
                  icon={Leaf}
                />
                {!readOnly && (
                  <button
                    type="button"
                    data-testid="co2-suggest-btn"
                    onClick={() => setCo2Open(true)}
                    title="Base officielle ASTRA/OFROU d'abord, estimation IA en dernier recours — validation requise"
                    className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 transition-colors hover:border-slate-400 hover:bg-slate-50 hover:text-slate-700"
                  >
                    <Sparkles className="h-3 w-3" /> Suggérer
                  </button>
                )}
              </div>
              <div className="relative" data-testid="conso-officielle-stat">
                <Stat
                  label="Conso officielle"
                  value={offTxt ? `${offTxt}${vehicle.conso_officielle_norme ? ` · ${vehicle.conso_officielle_norme}` : ""}` : "—"}
                  icon={Fuel}
                />
                {!readOnly && !(vehicle.type_carburant || "").toLowerCase().startsWith("électr") && (
                  <button
                    type="button"
                    data-testid="conso-suggest-btn"
                    onClick={() => setConsoOpen(true)}
                    title="Base officielle ASTRA/OFROU d'abord, estimation IA en dernier recours — validation requise"
                    className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 transition-colors hover:border-slate-400 hover:bg-slate-50 hover:text-slate-700"
                  >
                    <Sparkles className="h-3 w-3" /> Suggérer
                  </button>
                )}
              </div>
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
              <div className="relative" data-testid="reservoir-stat">
                <Stat label="Capacité réservoir" value={cap > 0 ? `${cap} L` : "—"} />
                {!readOnly && !(vehicle.type_carburant || "").toLowerCase().startsWith("électr") && (
                  <button
                    type="button"
                    data-testid="reservoir-suggest-btn"
                    onClick={() => setReservoirOpen(true)}
                    title="Suggestion IA (donnée constructeur) — validation requise"
                    className="absolute right-2 top-2 flex items-center gap-1 rounded-md border border-slate-200 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500 transition-colors hover:border-slate-400 hover:bg-slate-50 hover:text-slate-700"
                  >
                    <Sparkles className="h-3 w-3" /> Suggérer
                  </button>
                )}
              </div>
              <Stat label="Batterie" value={battTxt} icon={Zap} />
              <Stat label="Autonomie (réf.)" value={autonomie > 0 ? `${fmtNum(autonomie)} km` : "—"} />
              <Stat label="Niveau carburant" value={niveauTxt} icon={Fuel} />
            </div>
            {swissMeta && (
              <p className="mt-4 border-t border-slate-100 pt-3 text-xs text-slate-400" data-testid="tech-provenance-note">
                Source : {swissMeta.provider === "swisscarinfo" ? "SwissCarInfo — données officielles OFROU" : "Base officielle ASTRA/OFROU (copie locale)"} · dernière récupération le {dateFr((swissMeta.retrieved_at || "").slice(0, 10))}
              </p>
            )}
            {astraHistory.length > 0 && (
              <div className="mt-2 space-y-1.5" data-testid="tech-history-list">
                {astraHistory.map((h) => (
                  <div key={h.field} className="flex items-center justify-between gap-3 text-xs">
                    <span className="min-w-0 text-slate-400">
                      {h.label} : <span className="line-through decoration-slate-300">{h.previous_value == null || h.previous_value === "" ? "—" : String(h.previous_value)}</span>
                      {" → "}
                      <span className="font-medium text-slate-600">{h.applied_value == null ? "—" : String(h.applied_value)}</span>
                    </span>
                    <button
                      type="button"
                      data-testid={`tech-revert-${h.field.replace(/\./g, "-")}`}
                      onClick={() => revertField(h)}
                      className="shrink-0 rounded-md border border-slate-200 px-2 py-0.5 text-[11px] font-medium text-slate-500 transition-colors hover:bg-slate-50 hover:text-slate-700"
                    >
                      Rétablir
                    </button>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </>
      )}

      <SectionCard title="Documents carte grise" description="Recto · Verso · Historique" testId="carte-grise-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Carte grise" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>

      <TechnicalEnrichDialog open={techOpen} onOpenChange={setTechOpen} vehicle={vehicle} onApplied={() => onSaved?.()} />
      <ReservoirSuggestDialog open={reservoirOpen} onOpenChange={setReservoirOpen} vehicle={vehicle} onSaved={() => onSaved?.()} />
      <ConsoSuggestDialog open={consoOpen} onOpenChange={setConsoOpen} vehicle={vehicle} onSaved={() => onSaved?.()} />
      <Co2SuggestDialog open={co2Open} onOpenChange={setCo2Open} vehicle={vehicle} onSaved={() => onSaved?.()} />
    </div>
  );
}
