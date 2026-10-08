import { useState } from "react";
import { Loader2, AlertTriangle, Fuel } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { chfExact, dateFr } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import Pill from "@/components/energy/Pill";
import AnomalyDecisionDialog from "@/components/energy/AnomalyDecisionDialog";
import { ANOMALY_STATUS_META, SEVERITY_META, ANOMALY_TYPE_LABELS } from "@/lib/fuelImport";

const Row = ({ k, v, testId }) => (
  <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-slate-500">{k}</span><span className="text-right font-medium text-slate-800" data-testid={testId}>{v ?? "—"}</span></div>
);
const fmt = (v) => (v === null || v === undefined ? "—" : typeof v === "boolean" ? (v ? "oui" : "non") : Array.isArray(v) ? v.join(", ") : typeof v === "object" ? JSON.stringify(v) : String(v));

// Fiche anomalie (Sheet) : type, sévérité, statut, explication, contexte de détection (breakdown), transaction, décision humaine, historique
export default function AnomalyDrawer({ anomaly, onOpenChange, onOpenTransaction }) {
  const { user } = useAuth();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [decide, setDecide] = useState(false);
  const tx = anomaly?.transaction || {};
  return (
    <Sheet open={!!anomaly} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-2xl" data-testid="fuel-anomaly-drawer">
        {!anomaly ? <div className="p-8"><SheetTitle className="sr-only">Anomalie</SheetTitle><SheetDescription className="sr-only">Chargement</SheetDescription><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div> : (
          <div className="space-y-6 p-6">
            <header className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Pill map={SEVERITY_META} code={anomaly.severity} testId="fuel-anomaly-drawer-severity" />
                <Pill map={ANOMALY_STATUS_META} code={anomaly.status} testId="fuel-anomaly-drawer-status" />
                {anomaly.status === "justifiee" && <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-bold text-white" data-testid="fuel-anomaly-drawer-justified">Justifiée — conservée dans l'historique</span>}
              </div>
              <SheetTitle className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-slate-900" data-testid="fuel-anomaly-drawer-title">
                <AlertTriangle className="h-6 w-6 text-slate-400" /> {ANOMALY_TYPE_LABELS[anomaly.type] || anomaly.label}
              </SheetTitle>
              <SheetDescription className="text-sm text-slate-500">{anomaly.explanation}</SheetDescription>
            </header>
            {isAdmin && anomaly.status === "ouverte" && (
              <Button size="sm" onClick={() => setDecide(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-anomaly-justify-btn">Justifier / corriger / rejeter</Button>
            )}
            <section className="space-y-1" data-testid="fuel-anomaly-section-transaction">
              <h3 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide text-slate-500"><Fuel className="h-4 w-4" /> Transaction</h3>
              <Row k="Date" v={tx.date ? `${dateFr(tx.date)}${tx.heure ? ` ${tx.heure}` : ""}` : null} />
              <Row k="Station / fournisseur" v={[tx.station, tx.fournisseur].filter(Boolean).join(" · ") || null} />
              <Row k="Montant" v={tx.montant != null ? chfExact(tx.montant, tx.devise || "CHF") : null} />
              <Row k="Véhicule" v={anomaly.plaque || anomaly.vehicle_id} testId="fuel-anomaly-drawer-vehicle" />
              <Row k="Carte" v={anomaly.card_label || (tx.carte_last4 ? `••••${tx.carte_last4}` : null)} testId="fuel-anomaly-drawer-card" />
              {onOpenTransaction && tx.id && <Button variant="outline" size="sm" className="mt-1" onClick={() => onOpenTransaction(tx.id)} data-testid="fuel-anomaly-open-transaction-btn">Ouvrir la transaction</Button>}
            </section>
            <Separator />
            <section className="space-y-1" data-testid="fuel-anomaly-section-context">
              <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">Contexte de détection</h3>
              {Object.entries(anomaly.context || {}).map(([k, v]) => <Row key={k} k={k} v={fmt(v)} testId={`fuel-anomaly-context-${k}`} />)}
              <Row k="Détectée le" v={anomaly.detected_at ? new Date(anomaly.detected_at).toLocaleString("fr-CH") : null} />
            </section>
            <Separator />
            <section className="space-y-1" data-testid="fuel-anomaly-section-decision">
              <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">Décision</h3>
              {anomaly.status === "ouverte" ? <p className="text-sm text-slate-400" data-testid="fuel-anomaly-no-decision">Aucune décision — anomalie ouverte.</p> : (<>
                <Row k="Statut" v={anomaly.status_label} testId="fuel-anomaly-decision-status" />
                <Row k="Acteur" v={anomaly.decided_by} testId="fuel-anomaly-decision-by" />
                <Row k="Date" v={anomaly.decided_at ? new Date(anomaly.decided_at).toLocaleString("fr-CH") : null} testId="fuel-anomaly-decision-at" />
                <Row k="Motif" v={anomaly.decision_reason} testId="fuel-anomaly-decision-reason" />
              </>)}
              <details className="mt-2 text-xs text-slate-500" data-testid="fuel-anomaly-history">
                <summary className="cursor-pointer font-semibold">Historique ({(anomaly.history || []).length})</summary>
                <ul className="mt-1 space-y-0.5">{(anomaly.history || []).map((h, i) => <li key={i}>{new Date(h.at).toLocaleString("fr-CH")} · {h.by} · {h.status}{h.reason ? ` — ${h.reason}` : ""}</li>)}</ul>
              </details>
            </section>
            <AnomalyDecisionDialog anomaly={anomaly} open={decide} onOpenChange={setDecide} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
