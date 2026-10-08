import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { setFuelStatementDeclared } from "@/lib/api";
import { invalidateStatements } from "@/components/energy/StatementDialogs";
import { na, signed, apiError, FormError } from "@/lib/fuelStatements";

const F = [["montant", "Montant", "fuel-statement-declared-amount"], ["devise", "Devise", "fuel-statement-declared-currency"], ["volume_l", "Volume (L)", "fuel-statement-declared-volume"],
           ["kwh", "kWh", "fuel-statement-declared-kwh"], ["nb_lignes", "Nb lignes", "fuel-statement-declared-line-count"]];
const toForm = (d) => Object.fromEntries(F.map(([k]) => [k, d?.[k] ?? ""]));
const num = (v) => (v === "" ? null : Number(v));

// Relevé fournisseur déclaré (saisie manuelle facultative) + écarts Documents − déclaré. Vide = N/A (jamais 0). Verrouillé dès clôture (409 serveur).
export default function DeclaredSection({ st, editable }) {
  const qc = useQueryClient();
  const declaredKey = JSON.stringify(st.declared ?? null);
  const [form, setForm] = useState(toForm(st.declared));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  useEffect(() => { setForm(toForm(st.declared)); setError(null); }, [st.id, declaredKey]); // eslint-disable-line react-hooks/exhaustive-deps
  const d = st.deltas || {};
  const save = async () => {
    setBusy(true); setError(null);
    try {
      await setFuelStatementDeclared(st.id, { montant: num(form.montant), devise: form.devise || null, volume_l: num(form.volume_l), kwh: num(form.kwh), nb_lignes: num(form.nb_lignes) });
      toast.success("Relevé fournisseur déclaré enregistré");
      invalidateStatements(qc, st.id);
    } catch (e) { const m = apiError(e); setError(m); toast.error(m); } finally { setBusy(false); }
  };
  return (
    <section className="space-y-2" data-testid="fuel-statement-declared-section">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">C. Relevé fournisseur déclaré (facultatif)</h3>
      <p className="text-[11px] text-slate-400">Saisi manuellement depuis le relevé fournisseur — aucun import ligne à ligne. Valeur absente = N/A, jamais 0.{!editable && st.status === "cloture" ? " Décompte clôturé : relevé figé." : ""}</p>
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-5">
        {F.map(([k, label, tid]) => (
          <div key={k} className="space-y-1"><Label className="text-[11px] text-slate-500">{label}</Label>
            <Input type={k === "devise" ? "text" : "number"} value={form[k]} disabled={!editable} placeholder="N/A" maxLength={k === "devise" ? 3 : undefined} step={k === "nb_lignes" ? "1" : "0.01"}
              onChange={(e) => setForm((f) => ({ ...f, [k]: e.target.value }))} data-testid={tid} /></div>
        ))}
      </div>
      <FormError error={error} testId="fuel-statement-declared-error" />
      {editable && <Button size="sm" onClick={save} disabled={busy} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-statement-declared-save">Enregistrer le relevé déclaré</Button>}
      <h3 className="pt-1 font-display text-sm font-bold uppercase tracking-wide text-slate-500">D. Écarts (Documents − déclaré)</h3>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-sm sm:grid-cols-4" data-testid="fuel-statement-deltas">
        <p className="text-slate-500">Δ montant</p><p className="font-semibold" data-testid="fuel-statement-delta-amount">{d.montant_comparable === false ? "non comparable (devise ≠ CHF)" : signed(d.delta_montant, " CHF")}{d.delta_montant_pct != null ? <span className="ml-1 text-xs text-slate-400">({signed(d.delta_montant_pct, " %", 1)})</span> : null}</p>
        <p className="text-slate-500">Δ volume</p><p className="font-semibold" data-testid="fuel-statement-delta-volume">{signed(d.delta_volume_l, " L")}</p>
        <p className="text-slate-500">Δ kWh</p><p className="font-semibold" data-testid="fuel-statement-delta-kwh">{signed(d.delta_kwh, " kWh")}</p>
        <p className="text-slate-500">Δ nb lignes</p><p className="font-semibold" data-testid="fuel-statement-delta-lines">{signed(d.delta_nb_lignes, "", 0)}</p>
      </div>
      {st.declared_at && <p className="text-[11px] text-slate-400" data-testid="fuel-statement-declared-meta">Déclaré par {st.declared_by} · {new Date(st.declared_at).toLocaleString("fr-CH")} · déclaré : {na(st.declared?.montant)} {st.declared?.devise || ""}</p>}
    </section>
  );
}
