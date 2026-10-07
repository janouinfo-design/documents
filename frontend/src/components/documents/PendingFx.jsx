import { Hourglass } from "lucide-react";
import { chfExact } from "@/lib/format";

// D7 : documents en devise ≠ CHF sans contre-valeur — « conversion en attente », exclus du total CHF (jamais sommés comme CHF).
export function PendingFxSection({ items = [], onOpenVehicle, compact = false }) {
  if (!items.length) return null;
  return (
    <div data-testid="costs-pending-fx" className="rounded-xl border border-amber-300 bg-amber-50/60 p-4">
      <div className="flex items-center gap-2">
        <Hourglass className="h-4 w-4 text-amber-700" />
        <h3 className={compact ? "text-sm font-semibold text-amber-900" : "font-display text-base font-semibold text-amber-900"}>
          Conversion en attente — {items.length} document(s) exclu(s) du total CHF
        </h3>
      </div>
      <p className="mt-1 text-xs text-amber-800">
        Devise ≠ CHF sans contre-valeur saisie : le montant d'origine est conservé mais n'est jamais additionné comme du CHF.
        Renseignez « Contre-valeur CHF » sur la fiche du document pour l'intégrer au total.
      </p>
      <ul className="mt-3 divide-y divide-amber-200/70">
        {items.map((i) => (
          <li key={i.key} data-testid={`pending-fx-${i.key}`} className="flex items-center justify-between gap-3 py-2">
            <div className="min-w-0">
              <p className="truncate text-sm font-medium text-slate-800">{i.label}</p>
              <p className="text-[11px] text-slate-500">
                {onOpenVehicle ? (
                  <button onClick={() => onOpenVehicle(i.vehicle_id)} className="font-semibold underline-offset-2 hover:underline">{i.plaque || "—"}</button>
                ) : (i.plaque || "—")}
                {" · "}{i.category}{i.fournisseur ? ` · ${i.fournisseur}` : ""}{i.date_debut ? ` · ${i.date_debut}` : ""}
              </p>
            </div>
            <div className="text-right">
              <p className="text-sm font-semibold text-slate-900">{chfExact(i.montant, i.devise)}</p>
              <p className="text-[10px] font-bold uppercase tracking-wide text-amber-700">en attente</p>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// Montant d'un poste : contre-valeur CHF + origine (ex. 66.50 CHF ← 70.00 EUR)
export function CostAmount({ item, className = "" }) {
  return (
    <span className={className}>
      {chfExact(item.montant, item.devise)}
      {item.montant_origine != null && (
        <span data-testid={`cost-origin-${item.key}`} className="ml-1 text-[11px] font-normal text-slate-400">← {chfExact(item.montant_origine, item.devise_origine)}</span>
      )}
    </span>
  );
}
