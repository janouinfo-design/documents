import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useState } from "react";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { getVehicles } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { NOFILE_QUERY_KEYS } from "@/components/documents/NoFileBadge";

export const CURRENCIES = ["CHF", "EUR", "USD"];

export const F = ({ label, children, className = "" }) => (
  <div className={`space-y-1 ${className}`}>
    <Label className="text-xs text-slate-500">{label}</Label>
    {children}
  </div>
);

export function DeclarativeBanner() {
  return (
    <p data-testid="nofile-declarative-banner" className="flex items-start gap-2 rounded-lg border border-amber-200 bg-amber-50 px-3 py-2 text-xs text-amber-800">
      <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
      Saisie déclarative sans justificatif — motif obligatoire, enregistrement audité. Le document créé porte le coût (une seule fois) ;
      vous pourrez joindre le justificatif plus tard. Date et heure en heure locale Europe/Zurich.
    </p>
  );
}

export function VehicleSelect({ value, onChange, testId = "nofile-vehicle" }) {
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  return (
    <F label="Véhicule">
      <Select value={value || ""} onValueChange={onChange}>
        <SelectTrigger data-testid={testId}><SelectValue placeholder="Choisir un véhicule" /></SelectTrigger>
        <SelectContent>
          {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}{v.marque ? ` · ${v.marque} ${v.modele || ""}` : ""}</SelectItem>)}
        </SelectContent>
      </Select>
    </F>
  );
}

// D7 : devise + contre-valeur CHF (uniquement si devise ≠ CHF ; vide = « conversion en attente », exclu du total CHF)
export function CurrencyFields({ devise, montantChf, onDevise, onMontantChf, idPrefix }) {
  return (
    <>
      <F label="Devise">
        <Select value={devise} onValueChange={onDevise}>
          <SelectTrigger data-testid={`${idPrefix}-devise`}><SelectValue /></SelectTrigger>
          <SelectContent>{CURRENCIES.map((d) => <SelectItem key={d} value={d}>{d}</SelectItem>)}</SelectContent>
        </Select>
      </F>
      {devise !== "CHF" && (
        <F label="Contre-valeur CHF (optionnel)">
          <Input data-testid={`${idPrefix}-montant-chf`} type="number" min="0" step="0.05" value={montantChf} onChange={(e) => onMontantChf(e.target.value)} placeholder="Vide = conversion en attente" />
          <p className="text-[11px] text-slate-500" data-testid={`${idPrefix}-fx-note`}>Sans contre-valeur, la ligne est marquée « conversion en attente » et exclue du total CHF.</p>
        </F>
      )}
    </>
  );
}

export const num = (v) => (v === "" || v === null || v === undefined ? null : Number(v));

// Soumission commune : 409 DUPLICATE_SUSPECTED → confirmation explicite, puis rafraîchissement des vues dérivées.
export function useNoFileSubmit({ submit, onSuccess, successLabel }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const [dup, setDup] = useState(null);
  const [warnings, setWarnings] = useState([]);

  const run = async (override = false) => {
    setBusy(true);
    try {
      const r = await submit(override);
      setDup(null);
      setWarnings(r.warnings || []);
      NOFILE_QUERY_KEYS.forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      toast.success(successLabel(r));
      onSuccess?.(r);
    } catch (e) {
      const detail = e?.response?.data?.detail;
      if (e?.response?.status === 409 && detail?.code === "DUPLICATE_SUSPECTED") setDup(detail);
      else toast.error((typeof detail === "string" && detail) || detail?.message || "Enregistrement impossible");
    } finally {
      setBusy(false);
    }
  };
  const reset = useCallback(() => { setDup(null); setWarnings([]); }, []);
  return { busy, dup, warnings, run, reset };
}
