import { useState } from "react";
import { Link } from "react-router-dom";
import { Scale, Fuel, Gauge, BookOpen, MessageSquareText } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import Pill from "@/components/energy/Pill";
import { JustifyDialog } from "@/components/energy/ReconciliationDialogs";
import { RECO_STATUS_META, CONSO_SOURCE_META, BLOCKER_META, na, signed, periodLabel, fmtDateTime } from "@/lib/fuelStatements";

const Row = ({ k, v, testId }) => (
  <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-slate-500">{k}</span><span className="text-right font-medium text-slate-800" data-testid={testId}>{v ?? "N/A"}</span></div>
);
const Block = ({ icon: Icon, title, hint, children, testId }) => (
  <section className="space-y-1 rounded-xl border border-slate-200 p-3" data-testid={testId}>
    <h3 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide text-slate-500"><Icon className="h-4 w-4" /> {title}</h3>
    {hint && <p className="text-[11px] text-slate-400">{hint}</p>}
    {children}
  </section>
);

// Fiche rapprochement : A. Achats · B. Consommation réelle (CAN) · C. Référence ASTRA — jamais mélangés ; écart, seuils, statut, justification, historique
export default function ReconciliationDrawer({ item, onOpenChange }) {
  const { user } = useAuth();
  const isAdmin = can(user, "reconciliations.justify");
  const [justify, setJustify] = useState(false);
  const c = item?.consommation || {};
  const a = item?.achats || {};
  const astra = item?.astra || {};
  const th = item?.thresholds || {};
  return (
    <Sheet open={!!item} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-2xl" data-testid="fuel-reconciliation-drawer">
        {!item ? <div className="p-8"><SheetTitle className="sr-only">Rapprochement</SheetTitle><SheetDescription className="sr-only">—</SheetDescription></div> : (
          <div className="space-y-5 p-6">
            <header className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Pill map={RECO_STATUS_META} code={item.status} testId="fuel-reconciliation-drawer-status" />
                <Pill map={CONSO_SOURCE_META} code={item.source_consumption} testId="fuel-reconciliation-drawer-source" />
                {item.justification && <span className="rounded-full bg-emerald-600 px-2 py-0.5 text-[10px] font-bold text-white" data-testid="fuel-reconciliation-drawer-justified">Justifié</span>}
              </div>
              <SheetTitle className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-slate-900" data-testid="fuel-reconciliation-drawer-title">
                <Scale className="h-6 w-6 text-slate-400" /> {item.plaque || item.vehicle_id} — {periodLabel(item.period_month)}
              </SheetTitle>
              <SheetDescription className="text-sm text-slate-500">{item.vehicule_label || "Véhicule"} · {item.period_from} → {item.period_to} · {item.status_reason}</SheetDescription>
            </header>
            {isAdmin && <Button size="sm" onClick={() => setJustify(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-reconciliation-justify-btn"><MessageSquareText className="h-4 w-4" /> Justifier l'écart</Button>}

            <Block icon={Fuel} title="A. Achats (Documents)" hint="Transactions carburant validées / saisies / importées — ce sont des achats, jamais une consommation réelle." testId="fuel-reconciliation-section-achats">
              <Row k="Litres achetés" v={na(a.litres, " L")} testId="fuel-reconciliation-drawer-purchased" />
              <Row k="kWh achetés" v={na(a.kwh, " kWh")} />
              <Row k="Montant compté (CHF)" v={na(a.chf, " CHF")} />
              <Row k="Transactions" v={`${a.n_tx ?? 0}${a.pending_fx ? ` · ${a.pending_fx} en attente FX` : ""}`} />
              <Row k="Fournisseurs" v={Object.entries(a.by_fournisseur || {}).map(([k, v]) => `${k} (${v})`).join(", ") || "—"} />
              <Link to={`/energie?vehicle=${item.vehicle_id}`} className="text-xs underline" data-testid="fuel-reconciliation-open-transactions">Voir les transactions du véhicule</Link>
            </Block>
            <Block icon={Gauge} title="B. Consommation réelle (CAN)" hint="Mesure embarquée (litres cumulés / odomètre). Source prioritaire ; si absente, aucune consommation réelle n'est inventée." testId="fuel-reconciliation-section-can">
              <Row k="Source" v={c.source === "can" ? "CAN mesuré" : "Aucune mesure CAN"} />
              <Row k="Litres consommés" v={na(c.litres, " L")} testId="fuel-reconciliation-drawer-can" />
              <Row k="Distance" v={na(c.km, " km", 0)} testId="fuel-reconciliation-drawer-distance" />
              <Row k="Consommation réelle" v={na(c.l_100km, " L/100 km", 1)} />
              {c.source === "can" && <Row k="Relevés" v={`${c.from_day} → ${c.to_day} (${c.snapshots} relevés)`} />}
              {item.estimation_tickets && <p className="rounded-lg bg-sky-50 px-2 py-1 text-[11px] text-sky-800" data-testid="fuel-reconciliation-drawer-estimation">Estimation tickets (indicatif, ≠ consommation réelle) : {item.estimation_tickets.litres} L / {item.estimation_tickets.km} km ≈ {item.estimation_tickets.l_100km} L/100 km</p>}
            </Block>
            <Block icon={BookOpen} title="C. Référence ASTRA (comparative)" hint="Consommation officielle constructeur — référence de comparaison, n'écrase jamais la mesure CAN." testId="fuel-reconciliation-section-astra">
              <Row k="Conso officielle" v={na(astra.conso_officielle_l_100km, " L/100 km", 1)} testId="fuel-reconciliation-drawer-astra" />
              <Row k="Norme" v={astra.norme || "—"} />
              <Row k="Réelle − officielle" v={signed(astra.ecart_l_100km, " L/100 km", 1)} />
              <Row k="Écart %" v={signed(astra.ecart_pct, " %", 1)} />
            </Block>
            <Separator />
            <section className="space-y-1" data-testid="fuel-reconciliation-section-ecart">
              <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">Écart achats − consommation CAN</h3>
              <Row k="Écart litres" v={signed(item.ecart_l, " L")} testId="fuel-reconciliation-drawer-delta-l" />
              <Row k="Écart %" v={signed(item.ecart_pct, " %", 1)} testId="fuel-reconciliation-drawer-delta-pct" />
              <Row k="Seuils tenant" v={th.configured ? `${na(th.threshold_pct, " %")} · ${na(th.threshold_l, " L")}` : "aucun seuil configuré → INDICATIF"} testId="fuel-reconciliation-drawer-thresholds" />
              <Row k="Statut" v={<Pill map={RECO_STATUS_META} code={item.status} />} />
              <p className="text-xs text-slate-500" data-testid="fuel-reconciliation-drawer-reason">{item.status_reason}</p>
              {item.blockers?.count > 0 && <div className="flex flex-wrap gap-1 pt-1" data-testid="fuel-reconciliation-drawer-blockers">{Object.entries(item.blockers.by_type).map(([k, v]) => <Pill key={k} map={BLOCKER_META} code={k} prefix={`${v} × `} />)}</div>}
            </section>
            <Separator />
            <section className="space-y-1" data-testid="fuel-reconciliation-section-justification">
              <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">Justification</h3>
              {item.justification ? (<>
                <Row k="Motif" v={item.justification.reason} testId="fuel-reconciliation-drawer-justification" />
                <Row k="Par" v={`${item.justification.by} · ${fmtDateTime(item.justification.at)}`} />
                <Row k="Écart au moment de la justification" v={`${signed(item.justification.ecart_l_at, " L")} (${signed(item.justification.ecart_pct_at, " %", 1)}) · ${item.justification.status_at}`} />
              </>) : <p className="text-sm text-slate-400" data-testid="fuel-reconciliation-drawer-no-justification">Aucune justification.</p>}
              <details className="mt-2 text-xs text-slate-500" data-testid="fuel-reconciliation-history">
                <summary className="cursor-pointer font-semibold">Historique ({(item.justification_history || []).length})</summary>
                <ul className="mt-1 space-y-0.5">{(item.justification_history || []).map((h, i) => <li key={i}>{fmtDateTime(h.at)} · {h.by} — {h.reason}</li>)}</ul>
              </details>
            </section>
            <details className="text-xs text-slate-500" data-testid="fuel-reconciliation-breakdown">
              <summary className="cursor-pointer font-semibold">Détail du calcul</summary>
              <ul className="mt-1 space-y-0.5">{(item.breakdown || []).map((b) => <li key={b.step}><b>{b.step}</b> — {b.detail}</li>)}</ul>
            </details>
            <JustifyDialog item={item} open={justify} onOpenChange={setJustify} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
