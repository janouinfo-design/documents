import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle, Lock } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Checkbox } from "@/components/ui/checkbox";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { createFuelStatement, recalculateFuelStatement, closeFuelStatement, closeFuelStatementException } from "@/lib/api";
import { errCode } from "@/lib/fuelCards";
import Pill from "@/components/energy/Pill";
import { BLOCKER_META, periodLabel, periodOptions, currentPeriod, na, apiError, FormError } from "@/lib/fuelStatements";

export const invalidateStatements = (qc, id) => {
  qc.invalidateQueries({ queryKey: ["fuel-statements"] });
  if (id) qc.invalidateQueries({ queryKey: ["fuel-statement", id] });
  qc.invalidateQueries({ queryKey: ["energy"] });
  qc.invalidateQueries({ queryKey: ["fuel-tx"] });
};

// Détail des blockers renvoyé par le serveur (409 CLOSE_BLOCKED) ou snapshoté à l'exception — jamais un simple toast
export function BlockersSummary({ data, testId }) {
  if (!data) return null;
  return (
    <div className="space-y-2 rounded-lg border border-rose-200 bg-rose-50 p-3 text-xs text-rose-900" data-testid={testId}>
      <p className="font-semibold" data-testid={`${testId}-count`}>{data.blocker_count ?? 0} blocker(s) sur {data.blocked_line_count ?? 0} ligne(s)</p>
      <div className="flex flex-wrap gap-1">{Object.entries(data.blockers_by_type || {}).map(([k, v]) => <Pill key={k} map={BLOCKER_META} code={k} prefix={`${v} × `} />)}</div>
      {(data.lines || []).length > 0 && <ul className="max-h-40 space-y-0.5 overflow-y-auto">{data.lines.map((ln) => <li key={ln.transaction_id} data-testid={`${testId}-line-${ln.transaction_id}`}>{ln.date} · {ln.plaque || "—"} · {ln.montant} {ln.devise} — {ln.blockers.map((b) => BLOCKER_META[b]?.label || b).join(", ")}</li>)}</ul>}
      {(data.integrity_errors || []).length > 0 && <ul className="space-y-0.5 border-t border-rose-200 pt-1" data-testid={`${testId}-integrity`}>{data.integrity_errors.map((e, i) => <li key={i}><b>{e.code}</b> — {e.detail}</li>)}</ul>}
    </div>
  );
}

// Nouveau décompte régulier : période + périmètre (tenant ou fournisseur) → snapshot de travail, rien n'est verrouillé
export function CreateStatementDialog({ open, onOpenChange, fournisseurs = [], onCreated }) {
  const qc = useQueryClient();
  const [period, setPeriod] = useState(currentPeriod());
  const [scope, setScope] = useState("tenant");
  const [fournisseur, setFournisseur] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) { setScope("tenant"); setFournisseur(""); setError(null); } }, [open]);
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const st = await createFuelStatement({ period_month: period, scope_type: scope, fournisseur: scope === "fournisseur" ? fournisseur : null });
      toast.success(`Décompte ${st.number} créé — snapshot ${st.totals.n_lignes} ligne(s)`);
      invalidateStatements(qc);
      onOpenChange(false);
      onCreated?.(st);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (errCode(e) === "STATEMENT_EXISTS" && d?.statement_id) { toast.error(d.message); onOpenChange(false); onCreated?.({ id: d.statement_id }); } else { const m = apiError(e); setError(m); toast.error(m); }
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fuel-statement-create-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Nouveau décompte</DialogTitle>
          <DialogDescription>Snapshot des transactions Documents du mois (D5, Europe/Zurich). En brouillon, rien n'est verrouillé ; un seul décompte régulier par période et périmètre.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1"><Label className="text-xs text-slate-500">Période</Label>
            <Select value={period} onValueChange={setPeriod}><SelectTrigger data-testid="fuel-statement-create-period"><SelectValue /></SelectTrigger>
              <SelectContent>{periodOptions().map((p) => <SelectItem key={p} value={p}>{periodLabel(p)}</SelectItem>)}</SelectContent></Select></div>
          <div className="space-y-1"><Label className="text-xs text-slate-500">Périmètre</Label>
            <Select value={scope} onValueChange={setScope}><SelectTrigger data-testid="fuel-statement-create-scope"><SelectValue /></SelectTrigger>
              <SelectContent><SelectItem value="tenant">Tout le tenant</SelectItem><SelectItem value="fournisseur">Un fournisseur</SelectItem></SelectContent></Select></div>
          {scope === "fournisseur" && (
            <div className="space-y-1"><Label className="text-xs text-slate-500">Fournisseur</Label>
              <Input list="fuel-statement-fournisseurs" value={fournisseur} onChange={(e) => setFournisseur(e.target.value)} placeholder="Migrol, Shell…" data-testid="fuel-statement-create-fournisseur" />
              <datalist id="fuel-statement-fournisseurs">{fournisseurs.map((f) => <option key={f} value={f} />)}</datalist></div>
          )}
        </div>
        <FormError error={error} testId="fuel-statement-create-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-statement-create-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || (scope === "fournisseur" && !fournisseur.trim())} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-create-confirm">Créer le snapshot</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Recalcul explicite du snapshot (brouillon uniquement) — jamais automatique
export function RecalculateDialog({ st, open, onOpenChange }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) setError(null); }, [open, st?.id]);
  if (!st) return null;
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const r = await recalculateFuelStatement(st.id);
      toast.success(`Snapshot recalculé : +${r.added.length} / −${r.removed.length} transaction(s) · ${r.totals.n_lignes} ligne(s)`);
      invalidateStatements(qc, st.id);
      onOpenChange(false);
    } catch (e) { const m = apiError(e); setError(m); toast.error(m); if (e?.response?.status === 409) invalidateStatements(qc, st.id); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fuel-statement-recalculate-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Recalculer le snapshot</DialogTitle>
          <DialogDescription>Le snapshot sera reconstruit à partir des transactions actuellement éligibles. Les totaux et blockers peuvent changer. Le relevé déclaré, la période et le périmètre sont conservés.</DialogDescription>
        </DialogHeader>
        <FormError error={error} testId="fuel-statement-recalculate-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-statement-recalculate-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-recalculate-confirm">Recalculer</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Clôture normale : résumé avant confirmation ; 409 CLOSE_BLOCKED → détail des blockers / intégrité affiché dans le dialog
export function CloseDialog({ st, open, onOpenChange }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [blocked, setBlocked] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) { setBlocked(null); setError(null); } }, [open, st?.id]);
  if (!st) return null;
  const t = st.totals;
  const submit = async () => {
    setBusy(true); setBlocked(null); setError(null);
    try {
      const r = await closeFuelStatement(st.id);
      toast.success(r.already_closed ? "Décompte déjà clôturé" : `Décompte ${st.number} clôturé — ${t.n_lignes} transaction(s) verrouillée(s)`);
      invalidateStatements(qc, st.id);
      onOpenChange(false);
    } catch (e) {
      const d = e?.response?.data?.detail;
      if (e?.response?.status === 409 && d?.code === "CLOSE_BLOCKED") { setBlocked(d); toast.error(d.message); } else { const m = apiError(e); setError(m); toast.error(m); }
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-statement-close-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg"><Lock className="h-4 w-4" /> Clôturer le décompte {st.number}</DialogTitle>
          <DialogDescription>Point d'immutabilité : le snapshot et ses {t.n_lignes} transaction(s) seront verrouillés (aucune réouverture ; corrections tardives via un correctif).</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-2 gap-2 text-sm" data-testid="fuel-statement-close-summary">
          <p className="text-slate-500">Période</p><p className="font-medium">{periodLabel(st.period_month)} · {st.scope_label}</p>
          <p className="text-slate-500">Lignes</p><p className="font-medium">{t.n_lignes}</p>
          <p className="text-slate-500">Montant CHF Documents</p><p className="font-medium">{na(t.montant_chf, " CHF")}</p>
          <p className="text-slate-500">Volume</p><p className="font-medium">{na(t.litres, " L")} · {na(t.kwh, " kWh")}</p>
          <p className="text-slate-500">Blockers</p><p className={`font-semibold ${t.blocker_count ? "text-rose-700" : "text-emerald-700"}`} data-testid="fuel-statement-close-blocker-count">{t.blocker_count}</p>
          <p className="text-slate-500">Intégrité</p><p className="font-medium">vérifiée par le serveur à la clôture</p>
        </div>
        {t.blocker_count > 0 && !blocked && <p className="rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-900" data-testid="fuel-statement-close-blockers-warning">Le snapshot contient des blockers : la clôture normale sera refusée (409). Corrigez les transactions puis recalculez, ou utilisez « Clôturer avec exception ».</p>}
        <BlockersSummary data={blocked} testId="fuel-statement-close-blocked" />
        <FormError error={error} testId="fuel-statement-close-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-statement-close-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-close-confirm">Confirmer la clôture</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Clôture par exception : action distincte, warning, blockers visibles, motif obligatoire, confirmation explicite
export function CloseExceptionDialog({ st, open, onOpenChange }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [confirm, setConfirm] = useState(false);
  const [busy, setBusy] = useState(false);
  const [integrity, setIntegrity] = useState(null);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) { setReason(""); setConfirm(false); setIntegrity(null); setError(null); } }, [open, st?.id]);
  if (!st) return null;
  const t = st.totals;
  const blockers = { blocker_count: t.blocker_count, blocked_line_count: t.blocked_line_count, blockers_by_type: t.blockers_by_type, lines: (st.lines || []).filter((l) => l.blockers?.length) };
  const submit = async () => {
    setBusy(true); setIntegrity(null); setError(null);
    try {
      await closeFuelStatementException(st.id, { reason: reason.trim(), confirm: true });
      toast.success(`Décompte ${st.number} clôturé avec exception — ${t.blocker_count} blocker(s) conservé(s)`);
      invalidateStatements(qc, st.id);
      onOpenChange(false);
    } catch (e) {
      const d = e?.response?.data?.detail;
      const m = apiError(e);
      if (e?.response?.status === 409 && d?.integrity_errors?.length) setIntegrity(d); else setError(m);
      toast.error(m);
    } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-statement-close-exception-dialog">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg text-rose-800"><AlertTriangle className="h-5 w-5" /> Clôturer avec exception</DialogTitle>
          <DialogDescription>Les blockers ci-dessous ne seront ni supprimés ni résolus : ils resteront visibles dans l'historique du décompte. Les transactions seront verrouillées exactement comme pour une clôture normale.</DialogDescription>
        </DialogHeader>
        <BlockersSummary data={blockers} testId="fuel-statement-close-exception-blockers" />
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif (obligatoire)</Label>
          <Textarea rows={3} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-statement-close-exception-motif" />
        </div>
        <label className="flex items-start gap-2 text-xs text-slate-700">
          <Checkbox checked={confirm} onCheckedChange={(v) => setConfirm(!!v)} data-testid="fuel-statement-close-exception-ack" />
          <span>Je confirme clôturer ce décompte malgré {t.blocker_count} blocker(s) ouvert(s). Aucune réouverture ne sera possible.</span>
        </label>
        {integrity && <BlockersSummary data={{ blocker_count: 0, blocked_line_count: 0, integrity_errors: integrity.integrity_errors }} testId="fuel-statement-close-exception-integrity" />}
        <FormError error={error} testId="fuel-statement-close-exception-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-statement-close-exception-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || !confirm || reason.trim().length < 3} className="bg-rose-700 hover:bg-rose-800" data-testid="fuel-statement-close-exception-confirm">Clôturer avec exception</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

// Correctif : nouveau décompte lié au parent clôturé, même période / périmètre, uniquement les transactions non verrouillées — jamais une réouverture
export function CorrectiveDialog({ st, open, onOpenChange, onCreated }) {
  const qc = useQueryClient();
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { if (open) { setReason(""); setError(null); } }, [open, st?.id]);
  if (!st) return null;
  const submit = async () => {
    setBusy(true); setError(null);
    try {
      const cor = await createFuelStatement({ type: "correctif", parent_statement_id: st.id, reason: reason.trim() });
      toast.success(`Correctif ${cor.number} créé — ${cor.totals.n_lignes} transaction(s) non verrouillée(s)`);
      invalidateStatements(qc, st.id);
      onOpenChange(false);
      onCreated?.(cor);
    } catch (e) { const m = apiError(e); setError(m); toast.error(m); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="fuel-statement-corrective-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Créer un correctif de {st.number}</DialogTitle>
          <DialogDescription>
            Le décompte parent reste immuable (ce n'est pas une réouverture). Le correctif couvre {periodLabel(st.period_month)} · {st.scope_label} et n'inclut que les transactions <b>non verrouillées</b> : tardives ou jamais incluses dans un décompte clôturé.
            {st.corrective_eligible != null && <> Éligibles actuellement : <b data-testid="fuel-statement-corrective-eligible">{st.corrective_eligible}</b>.</>}
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-1">
          <Label className="text-xs text-slate-500">Motif (obligatoire)</Label>
          <Textarea rows={2} value={reason} onChange={(e) => setReason(e.target.value)} data-testid="fuel-statement-corrective-motif" />
        </div>
        <FormError error={error} testId="fuel-statement-corrective-error" />
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-statement-corrective-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || reason.trim().length < 3} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-corrective-confirm">Créer le correctif</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
