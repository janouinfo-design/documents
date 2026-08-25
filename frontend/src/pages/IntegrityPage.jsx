import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RefreshCw, Link2, PlusCircle, Loader2, AlertTriangle } from "lucide-react";
import { getIntegrity, getLinkSuggestions, linkNavixyVehicle, createNavixyVehicle } from "@/lib/api";
import { Button } from "@/components/ui/button";
import QueryErrorState from "@/components/QueryErrorState";
import { cn } from "@/lib/utils";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter, DialogDescription,
} from "@/components/ui/dialog";

const FILTERS = [
  { key: "tous", label: "Tous" },
  { key: "DIFFERENT", label: "Différences" },
  { key: "NON_LIE", label: "Non liés" },
  { key: "NON_DISPONIBLE", label: "Indisponibles" },
  { key: "erreurs", label: "Erreurs" },
];

const STATUS_STYLE = {
  IDENTIQUE: "bg-emerald-50 text-emerald-700 border-emerald-200",
  DIFFERENT: "bg-red-50 text-red-700 border-red-200",
  NON_DISPONIBLE: "bg-slate-50 text-slate-500 border-slate-200",
  NON_SUPPORTE: "bg-amber-50 text-amber-700 border-amber-200",
  NON_LIE: "bg-slate-100 text-slate-600 border-slate-300",
  ERREUR_INTEGRATION: "bg-red-50 text-red-700 border-red-200",
  INTEGRATION_ABSENTE: "bg-slate-50 text-slate-500 border-slate-200",
};

function StatusBadge({ status }) {
  return (
    <span className={cn("inline-block rounded-full border px-2 py-0.5 text-[11px] font-semibold",
      STATUS_STYLE[status] || "bg-slate-50 text-slate-500 border-slate-200")}>
      {status.replaceAll("_", " ")}
    </span>
  );
}

const FIELD_LABELS = {
  nom: "Nom", plaque: "Plaque", vin: "VIN", marque_modele: "Marque / Modèle",
  annee: "Année", couleur: "Couleur", type: "Type", garage: "Garage", departement: "Département",
};

function LinkSection({ onDone }) {
  const { data, isLoading, error } = useQuery({ queryKey: ["link-suggestions"], queryFn: getLinkSuggestions, retry: false });
  const [busy, setBusy] = useState(null);
  const [simulation, setSimulation] = useState(null);

  if (error) {
    if (error?.response?.status === 503) return null; // intégration absente : bannière dédiée déjà affichée
    return (
      <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="link-suggestions-error">
        Impossible de charger les suggestions de liaison : {error?.response?.data?.detail || "erreur du serveur"}
      </div>
    );
  }
  if (isLoading || !data || data.unlinked === 0) return null;

  const doLink = async (vehicleId, extId) => {
    setBusy(vehicleId);
    try {
      const r = await linkNavixyVehicle(vehicleId, extId);
      toast.success(`Liaison validée (preuve : ${r.matched_by.join(", ")})`);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de la liaison");
    } finally {
      setBusy(null);
    }
  };

  const doSimulate = async (vehicleId) => {
    setBusy(vehicleId);
    try {
      const r = await createNavixyVehicle(vehicleId, false);
      setSimulation({ vehicleId, ...r });
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Simulation impossible");
    } finally {
      setBusy(null);
    }
  };

  const doCreate = async () => {
    setBusy(simulation.vehicleId);
    try {
      const r = await createNavixyVehicle(simulation.vehicleId, true);
      toast.success(`Objet véhicule créé chez le fournisseur (id ${r.external_vehicle_id})`);
      setSimulation(null);
      onDone();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de la création");
    } finally {
      setBusy(null);
    }
  };

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="link-assistant">
      <h3 className="font-display text-lg font-bold text-slate-900">
        Véhicules non liés au fournisseur télématique ({data.unlinked})
      </h3>
      <p className="mt-1 text-sm text-slate-500">
        Liaison uniquement sur preuve (VIN exact, plaque, tracker). Toute création d'objet chez le
        fournisseur passe par une simulation puis votre confirmation.
      </p>
      <div className="mt-4 space-y-3">
        {data.suggestions.map((s) => (
          <div key={s.vehicle_id} className="flex flex-col gap-2 rounded-xl border border-slate-200 p-3 sm:flex-row sm:items-center sm:justify-between"
               data-testid={`link-row-${s.vehicle_id}`}>
            <div>
              <p className="font-semibold text-slate-900">{s.plaque} <span className="font-normal text-slate-500">— {s.marque} {s.modele}</span></p>
              <p className="text-xs text-slate-500">
                {s.status === "aucun_candidat" && "Aucun candidat prouvable côté fournisseur"}
                {s.status === "candidat_unique" && `1 candidat (preuve : ${s.candidates[0].matched_by.join(", ")})`}
                {s.status === "plusieurs_candidats" && `${s.candidates.length} candidats — votre validation est requise`}
              </p>
            </div>
            <div className="flex flex-wrap items-center gap-2">
              {s.candidates.map((c) => (
                <Button key={c.external_vehicle_id} size="sm" variant="outline" className="gap-1.5"
                        data-testid={`link-btn-${s.vehicle_id}-${c.external_vehicle_id}`}
                        disabled={busy === s.vehicle_id}
                        onClick={() => doLink(s.vehicle_id, c.external_vehicle_id)}>
                  <Link2 className="h-3.5 w-3.5" /> Lier à « {c.label || c.reg_number || c.external_vehicle_id} »
                </Button>
              ))}
              <Button size="sm" variant="outline" className="gap-1.5 border-dashed"
                      data-testid={`simulate-create-btn-${s.vehicle_id}`}
                      disabled={busy === s.vehicle_id}
                      onClick={() => doSimulate(s.vehicle_id)}>
                {busy === s.vehicle_id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <PlusCircle className="h-3.5 w-3.5" />}
                Simuler la création
              </Button>
            </div>
          </div>
        ))}
      </div>
      <Dialog open={!!simulation} onOpenChange={(o) => !o && setSimulation(null)}>
        <DialogContent data-testid="create-simulation-dialog">
          <DialogHeader>
            <DialogTitle>Simulation — création d'un objet véhicule fournisseur</DialogTitle>
            <DialogDescription>
              Aperçu exact de ce qui serait créé chez le fournisseur télématique. Aucune écriture sans confirmation.
            </DialogDescription>
          </DialogHeader>
          {simulation && (
            <div className="space-y-3 text-sm">
              <div className="rounded-lg bg-slate-50 p-3 font-mono text-xs">
                {Object.entries(simulation.simulation).map(([k, v]) => (
                  <p key={k}><span className="text-slate-500">{k}:</span> {String(v)}</p>
                ))}
              </div>
              {simulation.notes?.map((n, i) => (
                <p key={i} className="flex items-start gap-2 text-xs text-amber-700">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" /> {n}
                </p>
              ))}
              <p className="text-xs text-slate-500">
                Opération sensible : rien n'est créé tant que vous ne confirmez pas.
              </p>
            </div>
          )}
          <DialogFooter>
            <Button variant="outline" data-testid="create-cancel-btn" onClick={() => setSimulation(null)}>Annuler</Button>
            <Button data-testid="create-confirm-btn" className="bg-slate-900 hover:bg-slate-800"
                    disabled={busy != null} onClick={doCreate}>
              {busy != null ? <Loader2 className="mr-1.5 h-4 w-4 animate-spin" /> : null}
              Confirmer la création
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}

export default function IntegrityPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState("tous");
  const { data, isLoading, isFetching, refetch, isError: mainError, error: mainErrorObj } = useQuery({
    queryKey: ["integrity"], queryFn: () => getIntegrity(), retry: false,
  });

  const refreshAll = () => {
    refetch();
    qc.invalidateQueries({ queryKey: ["link-suggestions"] });
  };

  const rows = [];
  (data?.vehicles || []).forEach((v) => {
    if (!v.fields) {
      const st = v.link_status;
      if (filter === "tous" || (filter === "NON_LIE" && st === "NON_LIE") ||
          (filter === "erreurs" && (st === "ERREUR_INTEGRATION" || st === "INTEGRATION_ABSENTE"))) {
        rows.push({ key: v.vehicle_id, plaque: v.plaque, field: "—", doc: "présent",
                    nav: "—", status: st, note: v.note, vin_check: v.vin_check });
      }
      return;
    }
    Object.entries(v.fields).forEach(([fk, f]) => {
      const keep = filter === "tous" ? f.status !== "IDENTIQUE" || fk === "plaque"
        : filter === "DIFFERENT" ? f.status === "DIFFERENT"
        : filter === "NON_DISPONIBLE" ? f.status === "NON_DISPONIBLE"
        : filter === "erreurs" ? false
        : filter === "NON_LIE" ? false
        : true;
      if (keep) {
        rows.push({ key: `${v.vehicle_id}-${fk}`, plaque: v.plaque, field: FIELD_LABELS[fk] || fk,
                    doc: f.documents ?? "—", nav: f.navixy ?? "—", status: f.status, note: f.note,
                    vin_check: fk === "vin" ? f.vin_check : null });
      }
    });
  });

  return (
    <div className="space-y-6 animate-fade-in" data-testid="integrity-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
            Intégrité des données véhicules
          </h2>
          <p className="mt-1 text-sm text-slate-500">
            {data ? `${data.total} véhicule(s) · ${data.linked} lié(s) · ${data.divergences} divergence(s) · ${data.non_lies} non lié(s)` : "…"}
          </p>
        </div>
        <Button data-testid="integrity-refresh-btn" variant="outline" className="gap-2"
                onClick={refreshAll} disabled={isFetching}>
          <RefreshCw className={cn("h-4 w-4", isFetching && "animate-spin")} /> Re-vérifier
        </Button>
      </div>

      {mainError && <QueryErrorState error={mainErrorObj} testId="integrity-error" />}

      {data?.navixy_status === "not_configured" && (
        <div className="rounded-xl border border-slate-200 bg-slate-50 p-4 text-sm text-slate-600" data-testid="integration-absent-banner">
          Aucune intégration télématique configurée pour ce compte — la synchronisation est NON DISPONIBLE.
          Documents et Dashboard fonctionnent normalement sur le véhicule canonique.
        </div>
      )}
      {String(data?.navixy_status || "").startsWith("error") && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="integration-error-banner">
          Erreur d'intégration télématique : {data.navixy_status} — aucune donnée locale n'est perdue.
        </div>
      )}

      <div className="flex flex-wrap gap-2" data-testid="integrity-filters">
        {FILTERS.map((f) => (
          <button key={f.key} data-testid={`filter-${f.key}`}
                  onClick={() => setFilter(f.key)}
                  className={cn("rounded-full border px-4 py-1.5 text-sm font-medium transition-colors",
                    filter === f.key ? "border-slate-900 bg-slate-900 text-white"
                      : "border-slate-300 text-slate-600 hover:bg-slate-50")}>
            {f.label}
          </button>
        ))}
      </div>

      <LinkSection onDone={refreshAll} />

      <div className="overflow-x-auto rounded-2xl border border-slate-200 bg-white">
        <table className="w-full text-sm" data-testid="integrity-table">
          <thead>
            <tr className="border-b border-slate-200 text-left text-xs font-semibold uppercase tracking-wide text-slate-400">
              <th className="px-4 py-3">Véhicule</th>
              <th className="px-4 py-3">Champ</th>
              <th className="px-4 py-3">LOGITRAK</th>
              <th className="px-4 py-3">Télématique</th>
              <th className="px-4 py-3">Statut</th>
            </tr>
          </thead>
          <tbody>
            {isLoading ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400">
                <Loader2 className="mx-auto h-6 w-6 animate-spin" /></td></tr>
            ) : rows.length === 0 ? (
              <tr><td colSpan={5} className="px-4 py-10 text-center text-slate-400" data-testid="integrity-empty">
                Aucune ligne pour ce filtre.</td></tr>
            ) : rows.map((r) => (
              <tr key={r.key} className="border-b border-slate-100 last:border-0" data-testid="integrity-row">
                <td className="px-4 py-2.5 font-semibold text-slate-900">
                  {r.plaque}
                  {r.vin_check?.status === "a_verifier" && (
                    <span className="ml-2 inline-flex items-center gap-1 rounded-full border border-amber-200 bg-amber-50 px-2 py-0.5 text-[10px] font-semibold text-amber-700"
                          data-testid="vin-warning-badge" title={r.vin_check.motifs.join(" · ")}>
                      <AlertTriangle className="h-3 w-3" /> VIN à vérifier
                    </span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-slate-600">{r.field}</td>
                <td className="px-4 py-2.5 text-slate-700">{String(r.doc)}</td>
                <td className="px-4 py-2.5 text-slate-700">{String(r.nav)}</td>
                <td className="px-4 py-2.5"><StatusBadge status={r.status} />
                  {r.note && <p className="mt-0.5 text-[11px] text-slate-400">{r.note}</p>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
