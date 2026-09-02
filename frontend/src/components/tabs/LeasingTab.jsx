import { useState } from "react";
import { toast } from "sonner";
import { Pencil, Loader2, CalendarClock, Wallet, PieChart, Building2, FileText } from "lucide-react";
import { updateVehicle } from "@/lib/api";
import { chf, dateFr, fmtNum, daysLabel } from "@/lib/format";
import { Stat, SectionCard, FormRow } from "@/components/Field";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Switch } from "@/components/ui/switch";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { Label } from "@/components/ui/label";
import AlertChips from "@/components/AlertChips";
import StatusBadge from "@/components/StatusBadge";
import DocFolderSection from "@/components/DocFolderSection";
import DocumentScanCard from "@/components/DocumentScanCard";

const F = ["societe", "numero_contrat", "date_debut", "date_fin", "mensualite_chf", "duree_mois", "km_contractuel", "option_achat", "valeur_residuelle", "cout_total", "cout_mensuel", "commentaires"];
const pick = (l = {}) => Object.fromEntries(F.map((k) => [k, l[k] ?? (k === "option_achat" ? false : "")]));

export default function LeasingTab({ vehicle, metrics, onSaved, docs, refetchDocs }) {
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const l = vehicle.leasing || {};
  const lm = metrics.leasing || {};
  const [edit, setEdit] = useState(false);
  const [form, setForm] = useState(() => pick(l));
  const [saving, setSaving] = useState(false);
  const set = (k, v) => setForm((f) => ({ ...f, [k]: v }));

  const pct = lm.percent_used ?? 0;
  const barColor = pct < 70 ? "#10b981" : pct < 90 ? "#f59e0b" : "#ef4444";

  const save = async () => {
    setSaving(true);
    try {
      await updateVehicle(vehicle.id, {
        leasing: {
          ...form,
          mensualite_chf: Number(form.mensualite_chf) || 0,
          duree_mois: Number(form.duree_mois) || 0,
          km_contractuel: Number(form.km_contractuel) || 0,
          valeur_residuelle: Number(form.valeur_residuelle) || 0,
          cout_total: Number(form.cout_total) || 0,
          cout_mensuel: Number(form.cout_mensuel) || Number(form.mensualite_chf) || 0,
          date_debut: form.date_debut || null,
          date_fin: form.date_fin || null,
        },
      });
      toast.success("Leasing enregistré");
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
      {/* Computed metrics */}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400"><CalendarClock className="h-3.5 w-3.5" /> Mois restants</div>
          <p className="mt-1 font-display text-2xl font-bold text-slate-900">{lm.months_remaining ?? "—"}</p>
          <p className="text-xs text-slate-500">{daysLabel(lm.days_remaining)}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400"><Wallet className="h-3.5 w-3.5" /> Coût restant</div>
          <p className="mt-1 font-display text-2xl font-bold text-slate-900">{lm.cost_remaining != null ? chf(lm.cost_remaining) : "—"}</p>
          <p className="text-xs text-slate-500">Mensualité {chf(l.mensualite_chf)}</p>
        </div>
        <div className="rounded-xl border border-slate-200 bg-white p-4">
          <div className="flex items-center justify-between text-[10px] font-bold uppercase tracking-[0.12em] text-slate-400"><span className="flex items-center gap-1.5"><PieChart className="h-3.5 w-3.5" /> Contrat utilisé</span><span className="text-slate-900">{pct}%</span></div>
          <div className="mt-3 h-2 w-full overflow-hidden rounded-full bg-slate-100">
            <div className="h-2 rounded-full transition-all" style={{ width: `${pct}%`, backgroundColor: barColor }} />
          </div>
          <p className="mt-2 text-xs text-slate-500">{lm.total_months || 0} mois au total</p>
        </div>
      </div>

      {/* Alerts */}
      <div className="flex flex-col gap-2 rounded-xl border border-slate-200 bg-white p-4 sm:flex-row sm:items-center sm:justify-between">
        <div className="flex items-center gap-2">
          <span className="text-xs font-semibold uppercase tracking-[0.1em] text-slate-500">Alertes d'échéance</span>
          <StatusBadge level={lm.level} days={lm.days_remaining} showDays />
        </div>
        <AlertChips days={lm.days_remaining} thresholds={[180, 90, 30]} testId="leasing-alerts" />
      </div>

      {edit ? (
        <SectionCard title="Modifier le contrat de leasing" testId="leasing-edit">
          <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
            {[
              ["societe", "Société de leasing"], ["numero_contrat", "Numéro de contrat"],
              ["date_debut", "Date de début", "date"], ["date_fin", "Date de fin", "date"],
              ["mensualite_chf", "Mensualité (CHF)", "number"], ["duree_mois", "Durée (mois)", "number"],
              ["km_contractuel", "Kilométrage contractuel", "number"], ["valeur_residuelle", "Valeur résiduelle (CHF)", "number"],
              ["cout_total", "Coût total (CHF)", "number"], ["cout_mensuel", "Coût mensuel (CHF)", "number"],
            ].map(([k, label, type]) => (
              <FormRow key={k} label={label}><Input data-testid={`leasing-${k}`} type={type || "text"} value={form[k] ?? ""} onChange={(e) => set(k, e.target.value)} /></FormRow>
            ))}
            <div className="flex items-center justify-between rounded-lg border border-slate-200 px-4 py-2.5">
              <Label className="text-sm text-slate-700">Option d'achat</Label>
              <Switch data-testid="leasing-option_achat" checked={!!form.option_achat} onCheckedChange={(v) => set("option_achat", v)} />
            </div>
            <FormRow label="Commentaires" className="sm:col-span-2"><Textarea data-testid="leasing-commentaires" value={form.commentaires || ""} onChange={(e) => set("commentaires", e.target.value)} rows={3} /></FormRow>
          </div>
          <div className="mt-5 flex justify-end gap-2">
            <Button variant="outline" onClick={() => setEdit(false)}>Annuler</Button>
            <Button data-testid="leasing-save" onClick={save} disabled={saving} className="gap-2 bg-slate-900 hover:bg-slate-800">{saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer</Button>
          </div>
        </SectionCard>
      ) : (
        <SectionCard
          title="Contrat de leasing"
          description={l.societe || "Aucune société renseignée"}
          testId="leasing-view"
          action={!readOnly && (<Button variant="outline" size="sm" onClick={() => { setForm(pick(l)); setEdit(true); }} data-testid="leasing-edit-btn" className="gap-1.5"><Pencil className="h-3.5 w-3.5" /> Modifier</Button>)}
        >
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
            <Stat label="Société" value={l.societe} icon={Building2} />
            <Stat label="N° contrat" value={l.numero_contrat} icon={FileText} />
            <Stat label="Début" value={dateFr(l.date_debut)} />
            <Stat label="Fin" value={dateFr(l.date_fin)} />
            <Stat label="Mensualité" value={chf(l.mensualite_chf)} />
            <Stat label="Durée" value={`${l.duree_mois || 0} mois`} />
            <Stat label="Km contractuel" value={`${fmtNum(l.km_contractuel)} km`} />
            <Stat label="Option d'achat" value={l.option_achat ? "Oui" : "Non"} />
            <Stat label="Valeur résiduelle" value={chf(l.valeur_residuelle)} />
            <Stat label="Coût total" value={chf(l.cout_total)} />
            <Stat label="Coût mensuel" value={chf(l.cout_mensuel)} />
          </div>
          {l.commentaires && <div className="mt-3 rounded-lg bg-slate-50 p-3 text-sm text-slate-600">{l.commentaires}</div>}
        </SectionCard>
      )}

      <DocumentScanCard
        vehicle={vehicle}
        docType="leasing"
        testIdPrefix="leasing-scan"
        title="Scan intelligent — Contrat de leasing"
        description="Photographiez ou importez le contrat : organisme, n° de contrat, mensualité, dates, kilométrage… sont extraits puis soumis à votre validation."
        onValidated={() => { onSaved?.(); refetchDocs?.(); }}
      />

      <SectionCard title="Documents leasing" description="Contrat PDF · Conditions · Annexes" testId="leasing-docs">
        <DocFolderSection vehicleId={vehicle.id} folder="Leasing" docs={docs} onChange={() => { refetchDocs?.(); onSaved?.(); }} compact />
      </SectionCard>
    </div>
  );
}
