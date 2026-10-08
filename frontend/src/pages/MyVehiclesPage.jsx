import { useQuery } from "@tanstack/react-query";
import { CalendarCheck, Truck } from "lucide-react";
import { getMyVehicles, photoSrc } from "@/lib/api";
import { dateFr, fmtKm } from "@/lib/format";
import DriverShell from "@/components/me/DriverShell";

function Spec({ label, value, testId }) {
  return (
    <div>
      <dt className="text-[10px] font-semibold uppercase tracking-[0.14em] text-slate-400">{label}</dt>
      <dd className="mt-0.5 text-sm font-medium text-slate-800" data-testid={testId}>{value || "—"}</dd>
    </div>
  );
}

// Mes véhicules = affectations ACTIVES aujourd'hui (serveur) ; fiche réduite (aucune donnée leasing / assurance / coûts).
export default function MyVehiclesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["me", "vehicles"], queryFn: getMyVehicles, retry: false });
  const items = data?.items || [];
  return (
    <DriverShell title="Mes véhicules" icon={Truck} testId="me-vehicles-page" dataError={error} isLoading={isLoading}
      subtitle={`Véhicules qui vous sont affectés aujourd'hui${data?.date ? ` (${dateFr(data.date)})` : ""}. Les affectations terminées ou futures n'apparaissent pas.`}>
      {items.length === 0 ? (
        <div className="flex flex-col items-center gap-2 rounded-xl border border-dashed border-slate-300 bg-white px-6 py-16 text-center" data-testid="me-vehicles-empty">
          <Truck className="h-8 w-8 text-slate-300" />
          <p className="text-sm font-medium text-slate-600">Aucun véhicule ne vous est affecté aujourd'hui.</p>
          <p className="text-xs text-slate-400">Les affectations sont gérées par votre entreprise.</p>
        </div>
      ) : (
        <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3" data-testid="me-vehicles-grid">
          {items.map((v) => {
            const src = v.photo_url ? photoSrc(v.photo_url) : null;
            const a = v.assignment || {};
            return (
              <article key={v.id} data-testid={`me-vehicle-card-${v.id}`} className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm transition-shadow hover:shadow-md">
                <div className="flex h-36 items-center justify-center bg-slate-100">
                  {src ? <img src={src} alt={v.plaque} className="h-full w-full object-cover" /> : <Truck className="h-10 w-10 text-slate-300" />}
                </div>
                <div className="p-5">
                  <div className="flex items-start justify-between gap-2">
                    <h3 className="font-display text-xl font-bold tracking-tight text-slate-900" data-testid={`me-vehicle-plate-${v.id}`}>{v.plaque}</h3>
                    {a.principal && <span className="rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white" data-testid={`me-vehicle-principal-${v.id}`}>Principal</span>}
                  </div>
                  <p className="text-sm text-slate-500">{[v.marque, v.modele].filter(Boolean).join(" ") || "—"}{v.annee ? ` · ${v.annee}` : ""}</p>
                  <dl className="mt-4 grid grid-cols-2 gap-3">
                    <Spec label="Carburant" value={v.type_carburant} testId={`me-vehicle-fuel-${v.id}`} />
                    <Spec label="Kilométrage" value={v.kilometrage != null ? fmtKm(v.kilometrage) : null} testId={`me-vehicle-km-${v.id}`} />
                    <Spec label="Catégorie" value={v.categorie} />
                    <Spec label="Couleur" value={v.couleur} />
                  </dl>
                  <p className="mt-4 flex items-center gap-1.5 text-xs text-slate-500" data-testid={`me-vehicle-assignment-${v.id}`}>
                    <CalendarCheck className="h-3.5 w-3.5 text-slate-400" />
                    Affecté depuis le {dateFr(a.valid_from)}{a.valid_to ? ` · jusqu'au ${dateFr(a.valid_to)}` : ""}
                  </p>
                </div>
              </article>
            );
          })}
        </div>
      )}
    </DriverShell>
  );
}
