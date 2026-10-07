import { useQuery } from "@tanstack/react-query";
import { Search, X } from "lucide-react";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import DriverPicker from "@/components/drivers/DriverPicker";
import { getVehicles } from "@/lib/api";
import { INFRACTION_TYPES } from "@/lib/fines";

const ALL = "__all__";

// Filtres de la vue Amendes — tous transmis tels quels à /api/fines et aux exports (même périmètre).
export default function FinesFilters({ f, setF, onReset }) {
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const set = (k) => (v) => setF((p) => ({ ...p, [k]: v?.target ? v.target.value : v }));
  const hasAny = Object.entries(f).some(([k, v]) => !["fine_status"].includes(k) && v);
  return (
    <div className="grid grid-cols-2 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-4 lg:grid-cols-8" data-testid="fines-filters">
      <div className="relative col-span-2">
        <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
        <Input data-testid="fines-search" value={f.q} onChange={set("q")} placeholder="Référence, dossier, autorité, plaque, conducteur…" className="pl-9" />
      </div>
      <Select value={f.vehicle_id || ALL} onValueChange={(v) => set("vehicle_id")(v === ALL ? "" : v)}>
        <SelectTrigger data-testid="fines-filter-vehicle"><SelectValue placeholder="Véhicule" /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Tous les véhicules</SelectItem>
          {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}</SelectContent>
      </Select>
      <DriverPicker value={f.driver_id || null} onChange={(v) => set("driver_id")(v || "")} testId="fines-filter-driver" placeholder="Tous conducteurs" />
      <Select value={f.type_infraction || ALL} onValueChange={(v) => set("type_infraction")(v === ALL ? "" : v)}>
        <SelectTrigger data-testid="fines-filter-type"><SelectValue placeholder="Type" /></SelectTrigger>
        <SelectContent><SelectItem value={ALL}>Tous les types</SelectItem>
          {INFRACTION_TYPES.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}</SelectContent>
      </Select>
      <Input type="date" value={f.date_from} onChange={set("date_from")} title="Infraction depuis" data-testid="fines-filter-date-from" />
      <Input type="date" value={f.date_to} onChange={set("date_to")} title="Infraction jusqu'au" data-testid="fines-filter-date-to" />
      <div className="flex gap-2">
        <Input type="number" min="0" value={f.montant_min} onChange={set("montant_min")} placeholder="CHF min" data-testid="fines-filter-montant-min" />
        <Input type="number" min="0" value={f.montant_max} onChange={set("montant_max")} placeholder="max" data-testid="fines-filter-montant-max" />
      </div>
      {hasAny && (
        <div className="col-span-2 flex justify-end sm:col-span-4 lg:col-span-8">
          <Button variant="ghost" size="sm" onClick={onReset} className="h-7 gap-1 text-xs text-slate-500" data-testid="fines-filters-reset"><X className="h-3.5 w-3.5" /> Réinitialiser les filtres</Button>
        </div>
      )}
    </div>
  );
}
