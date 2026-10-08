import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, FileCheck2, Lock, AlertTriangle, RefreshCw, GitBranchPlus } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getFuelStatement } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import Pill from "@/components/energy/Pill";
import ExportButtons from "@/components/energy/ExportButtons";
import DeclaredSection from "@/components/energy/DeclaredSection";
import StatementLines from "@/components/energy/StatementLines";
import { RecalculateDialog, CloseDialog, CloseExceptionDialog, CorrectiveDialog, BlockersSummary } from "@/components/energy/StatementDialogs";
import { STATEMENT_STATUS_META, STATEMENT_TYPE_META, na, periodLabel, fmtDateTime, apiError } from "@/lib/fuelStatements";

const Row = ({ k, v, testId }) => (
  <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-slate-500">{k}</span><span className="text-right font-medium text-slate-800" data-testid={testId}>{v ?? "N/A"}</span></div>
);

// Fiche décompte : A. informations · B. snapshot Documents · C. relevé déclaré + D. écarts · E. blockers · F. clôture · G. lignes — actions admin selon statut, aucun reopen
export default function StatementDrawer({ statementId, onOpenChange, onOpenTransaction, onOpenStatement }) {
  const { user } = useAuth();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const { data: st, isError, error } = useQuery({ queryKey: ["fuel-statement", statementId], queryFn: () => getFuelStatement(statementId), enabled: !!statementId });
  const [dlg, setDlg] = useState(null);
  const closed = st?.status === "cloture";
  const t = st?.totals || {};
  return (
    <Sheet open={!!statementId} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-4xl" data-testid="fuel-statement-drawer">
        {!st ? (
          <div className="p-8"><SheetTitle className="sr-only">Décompte</SheetTitle><SheetDescription className="sr-only">Chargement</SheetDescription>
            {isError ? <p className="text-sm text-red-600" data-testid="fuel-statement-drawer-error">{apiError(error, "Impossible de charger le décompte.")}</p> : <Loader2 className="h-6 w-6 animate-spin text-slate-400" />}
          </div>
        ) : (
          <div className="space-y-5 p-6">
            <header className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Pill map={STATEMENT_STATUS_META} code={st.status} testId="fuel-statement-drawer-status" />
                <Pill map={STATEMENT_TYPE_META} code={st.type} testId="fuel-statement-drawer-type" />
                {st.close_exception && <span className="inline-flex items-center gap-1 rounded-full bg-rose-700 px-2.5 py-0.5 text-[11px] font-bold text-white" data-testid="fuel-statement-exception-badge"><AlertTriangle className="h-3 w-3" /> Clôturé avec exception</span>}
                {closed && <span className="inline-flex items-center gap-1 rounded-full border border-slate-300 px-2 py-0.5 text-[10px] font-bold text-slate-700" data-testid="fuel-statement-locked-badge"><Lock className="h-3 w-3" /> Immuable — aucune réouverture</span>}
              </div>
              <SheetTitle className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-slate-900" data-testid="fuel-statement-drawer-title"><FileCheck2 className="h-6 w-6 text-slate-400" /> {st.number}</SheetTitle>
              <SheetDescription className="text-sm text-slate-500">{st.scope_label} · {periodLabel(st.period_month)} ({st.period_from} → {st.period_to}) · snapshot du {fmtDateTime(st.snapshot_at)} (v{st.snapshot_count})</SheetDescription>
            </header>

            <div className="flex flex-wrap items-center gap-2" data-testid="fuel-statement-actions">
              {isAdmin && !closed && (<>
                <Button size="sm" variant="outline" onClick={() => setDlg("recalc")} className="gap-1.5" data-testid="fuel-statement-recalculate-btn"><RefreshCw className="h-4 w-4" /> Recalculer le snapshot</Button>
                <Button size="sm" onClick={() => setDlg("close")} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-close-btn"><Lock className="h-4 w-4" /> Clôturer</Button>
                {t.blocker_count > 0 && <Button size="sm" variant="outline" onClick={() => setDlg("exception")} className="gap-1.5 border-rose-300 text-rose-800 hover:bg-rose-50" data-testid="fuel-statement-close-exception-btn"><AlertTriangle className="h-4 w-4" /> Clôturer avec exception</Button>}
              </>)}
              {isAdmin && closed && st.type === "regulier" && <Button size="sm" variant="outline" onClick={() => setDlg("corrective")} className="gap-1.5" data-testid="fuel-statement-corrective-btn"><GitBranchPlus className="h-4 w-4" /> Créer un correctif</Button>}
              <ExportButtons path={`/fuel/statements/${st.id}/export`} testIdPrefix="fuel-statement" />
            </div>

            <section className="grid grid-cols-1 gap-x-6 sm:grid-cols-2" data-testid="fuel-statement-info-section">
              <div>
                <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">A. Informations</h3>
                <Row k="Périmètre" v={st.scope_label} testId="fuel-statement-drawer-scope" />
                <Row k="Fournisseur" v={st.scope?.fournisseur || "—"} />
                <Row k="Période" v={st.period_month} testId="fuel-statement-drawer-period" />
                <Row k="Type" v={st.type_label} />
                {st.type === "correctif" && <Row k="Décompte parent" v={<button type="button" className="underline" onClick={() => onOpenStatement?.(st.parent_statement_id)} data-testid="fuel-statement-parent-link">{st.parent_number || st.parent_statement_id}</button>} />}
                {st.reason && <Row k="Motif" v={st.reason} testId="fuel-statement-drawer-reason" />}
                <Row k="Créé" v={`${st.created_by} · ${fmtDateTime(st.created_at)}`} />
              </div>
              <div>
                <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">B. Snapshot Documents</h3>
                <Row k="Montant compté (CHF)" v={na(t.montant_chf, " CHF")} testId="fuel-statement-drawer-amount" />
                <Row k="Volume" v={na(t.litres, " L")} testId="fuel-statement-drawer-volume" />
                <Row k="kWh" v={na(t.kwh, " kWh")} testId="fuel-statement-drawer-kwh" />
                <Row k="Transactions" v={`${t.n_lignes} (${t.n_vehicules} véhicule(s))`} testId="fuel-statement-drawer-lines" />
                <Row k="En attente FX (exclues du CHF)" v={t.pending_fx} />
              </div>
            </section>
            <Separator />
            <DeclaredSection st={st} editable={isAdmin && !closed} />
            <Separator />
            <section className="space-y-2" data-testid="fuel-statement-blockers">
              <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">E. Blockers</h3>
              {t.blocker_count ? <BlockersSummary data={{ ...t, lines: (st.lines || []).filter((l) => l.blockers?.length) }} testId="fuel-statement-blocker" />
                : <p className="text-sm text-emerald-700" data-testid="fuel-statement-blocker-count">0 blocker — clôture normale possible</p>}
            </section>
            <Separator />
            <section className="space-y-1" data-testid="fuel-statement-closure-section">
              <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">F. Clôture</h3>
              {!closed ? <p className="text-sm text-slate-400" data-testid="fuel-statement-not-closed">Brouillon — aucune transaction verrouillée. La clôture (normale ou par exception) est le point d'immutabilité.</p> : (<>
                <Row k="Clôturé le" v={fmtDateTime(st.closed_at)} testId="fuel-statement-closed-at" />
                <Row k="Clôturé par" v={st.closed_by} testId="fuel-statement-closed-by" />
                <Row k="Mode" v={st.close_exception ? "Clôturé avec exception" : "Clôture normale (0 blocker, intégrité PASS)"} testId="fuel-statement-close-mode" />
                {st.exception && (<>
                  <Row k="Motif de l'exception" v={st.exception.reason} testId="fuel-statement-exception-reason" />
                  <Row k="Blockers conservés" v={`${st.exception.blockers_snapshot?.blocker_count} sur ${st.exception.blockers_snapshot?.blocked_line_count} ligne(s)`} testId="fuel-statement-exception-blockers" />
                  <BlockersSummary data={st.exception.blockers_snapshot} testId="fuel-statement-exception-snapshot" />
                </>)}
              </>)}
              {(st.correctifs || []).length > 0 && <div className="pt-1 text-sm" data-testid="fuel-statement-correctifs"><span className="text-slate-500">Correctifs : </span>{st.correctifs.map((c) => <button key={c.id} type="button" className="mr-2 underline" onClick={() => onOpenStatement?.(c.id)} data-testid={`fuel-statement-correctif-link-${c.id}`}>{c.number} ({STATEMENT_STATUS_META[c.status]?.label || c.status})</button>)}</div>}
              {closed && st.type === "regulier" && st.corrective_eligible != null && <p className="text-[11px] text-slate-400" data-testid="fuel-statement-corrective-eligible-hint">{st.corrective_eligible} transaction(s) non verrouillée(s) éligible(s) à un correctif.</p>}
            </section>
            <Separator />
            <StatementLines st={st} onOpenTransaction={onOpenTransaction} />
            <details className="text-xs text-slate-500" data-testid="fuel-statement-history">
              <summary className="cursor-pointer font-semibold">Historique ({(st.history || []).length})</summary>
              <ul className="mt-1 space-y-0.5">{(st.history || []).map((h, i) => <li key={i}>{fmtDateTime(h.at)} · {h.by} · <b>{h.event}</b>{h.detail ? ` — ${h.detail}` : ""}{h.event === "recalculated" ? ` — ${h.lines_before} → ${h.lines_after} ligne(s)` : ""}{h.reason ? ` — ${h.reason}` : ""}</li>)}</ul>
            </details>
            <RecalculateDialog st={st} open={dlg === "recalc"} onOpenChange={(o) => !o && setDlg(null)} />
            <CloseDialog st={st} open={dlg === "close"} onOpenChange={(o) => !o && setDlg(null)} />
            <CloseExceptionDialog st={st} open={dlg === "exception"} onOpenChange={(o) => !o && setDlg(null)} />
            <CorrectiveDialog st={st} open={dlg === "corrective"} onOpenChange={(o) => !o && setDlg(null)} onCreated={(cor) => onOpenStatement?.(cor.id)} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
