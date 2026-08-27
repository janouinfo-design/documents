import { useQuery } from "@tanstack/react-query";
import { Wallet, Loader2 } from "lucide-react";
import { getVehicleCosts } from "@/lib/api";
import { chf } from "@/lib/format";
import { SectionCard, Stat } from "@/components/Field";
import QueryErrorState from "@/components/QueryErrorState";

const FREQ_FR = { unique: "Unique", mensuel: "Mensuel", trimestriel: "Trimestriel", semestriel: "Semestriel", annuel: "Annuel" };

export default function CostsTab({ vehicle }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["vehicle-costs", vehicle.id],
    queryFn: () => getVehicleCosts(vehicle.id),
  });
  const items = data?.items || [];
  const totals = data?.totals || { annuel: 0, postes_actifs: 0 };

  if (isError) return <QueryErrorState error={error} testId="vehicle-costs-error" />;

  return (
    <div className="space-y-4" data-testid="costs-tab">
      <div className="grid grid-cols-2 gap-3">
        <Stat label={`Coût annuel ${data?.year || ""}`} value={chf(totals.annuel)} icon={Wallet} />
        <Stat label="Postes actifs" value={totals.postes_actifs} icon={Wallet} />
      </div>
      <SectionCard title="Postes de coût" description="Dérivés des montants des documents et des contrats — sans double comptage." testId="vehicle-costs-list">
        {isLoading && (
          <div className="flex items-center justify-center gap-2 py-8 text-sm text-slate-400">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement…
          </div>
        )}
        {!isLoading && items.length === 0 && (
          <p className="py-6 text-center text-sm text-slate-400" data-testid="vehicle-costs-empty">
            Aucun montant saisi pour ce véhicule — renseignez le montant sur une fiche document ou un contrat.
          </p>
        )}
        <div className="divide-y divide-slate-100">
          {items.map((i) => (
            <div key={i.key} className="flex items-center justify-between gap-3 py-3" data-testid={`vehicle-cost-${i.key}`}>
              <div className="min-w-0">
                <p className="truncate text-sm font-medium text-slate-800">{i.label}</p>
                <p className="text-xs text-slate-400">
                  {i.category} · {FREQ_FR[i.frequence] || i.frequence}
                  {i.source === "legacy" ? " · Fiche véhicule" : ""}
                  {i.date_debut || i.date_expiration ? ` · ${i.date_debut || "…"} → ${i.date_expiration || "…"}` : ""}
                </p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold text-slate-900">{chf(i.cout_annuel)}<span className="text-xs font-normal text-slate-400">/an</span></p>
                <p className="text-[11px] text-slate-400">
                  {chf(i.montant)} {FREQ_FR[i.frequence]?.toLowerCase() || ""}
                  {!i.actif && <span className="ml-1 text-amber-600">· hors {data?.year}</span>}
                </p>
              </div>
            </div>
          ))}
        </div>
      </SectionCard>
    </div>
  );
}
