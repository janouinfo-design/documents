import { useQuery } from "@tanstack/react-query";
import { Satellite, RefreshCw, MapPin, Gauge, Signal, Battery, Navigation, Loader2 } from "lucide-react";
import { getVehicleLive } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { cn } from "@/lib/utils";

const CONN = {
  active: { label: "En ligne", cls: "bg-emerald-500/15 text-emerald-300", dot: "bg-emerald-400" },
  idle: { label: "Inactif", cls: "bg-amber-500/15 text-amber-300", dot: "bg-amber-400" },
  offline: { label: "Hors ligne", cls: "bg-slate-500/20 text-slate-300", dot: "bg-slate-400" },
  signal_lost: { label: "Signal perdu", cls: "bg-red-500/15 text-red-300", dot: "bg-red-400" },
};

function Metric({ icon: Icon, label, value }) {
  return (
    <div className="rounded-lg bg-white/5 p-3">
      <div className="flex items-center gap-1.5 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400">
        <Icon className="h-3.5 w-3.5" /> {label}
      </div>
      <p className="mt-1 truncate text-sm font-semibold text-white">{value ?? "—"}</p>
    </div>
  );
}

export default function NavixyLiveCard({ vehicle }) {
  const { data, isFetching, refetch, isError } = useQuery({
    queryKey: ["live", vehicle.id],
    queryFn: () => getVehicleLive(vehicle.id),
    refetchOnWindowFocus: false,
    retry: false,
  });

  const conn = CONN[data?.connection_status] || CONN.offline;
  const moving = data?.movement_status === "moving";

  return (
    <div className="overflow-hidden rounded-xl border border-slate-800 bg-slate-900 text-white" data-testid="navixy-live-card">
      <div className="flex items-center justify-between border-b border-white/10 px-5 py-3">
        <div className="flex items-center gap-2.5">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10">
            <Satellite className="h-4 w-4 text-sky-300" />
          </span>
          <div>
            <p className="font-display text-sm font-bold leading-none">Suivi Navixy en direct</p>
            <p className="mt-0.5 text-[11px] text-slate-400">Tracker #{vehicle.navixy_tracker_id}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {data && (
            <span className={cn("inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-semibold", conn.cls)}>
              <span className={cn("h-1.5 w-1.5 rounded-full", conn.dot)} /> {conn.label}
            </span>
          )}
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            data-testid="navixy-live-refresh"
            className="flex h-8 w-8 items-center justify-center rounded-lg bg-white/10 text-slate-200 transition-colors hover:bg-white/20"
            aria-label="Actualiser"
          >
            {isFetching ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          </button>
        </div>
      </div>

      {isError ? (
        <p className="px-5 py-4 text-sm text-slate-400">Position indisponible pour ce tracker.</p>
      ) : !data ? (
        <p className="px-5 py-6 text-center text-sm text-slate-400">Chargement de la position…</p>
      ) : (
        <div className="grid grid-cols-2 gap-2 p-4 sm:grid-cols-3">
          <Metric icon={Navigation} label="Mouvement" value={moving ? `En route · ${Math.round(data.speed || 0)} km/h` : "À l'arrêt"} />
          <Metric icon={Gauge} label="Odomètre" value={data.odometer_km != null ? fmtKm(data.odometer_km) : "—"} />
          <Metric icon={Signal} label="Réseau" value={data.gsm_network} />
          <Metric icon={MapPin} label="Position" value={data.lat ? `${data.lat.toFixed(4)}, ${data.lng.toFixed(4)}` : "—"} />
          <Metric icon={Battery} label="Batterie" value={data.battery_level != null ? `${data.battery_level}%` : "—"} />
          <Metric icon={RefreshCw} label="Mise à jour" value={data.last_update} />
          {data.lat && (
            <a
              href={`https://www.google.com/maps?q=${data.lat},${data.lng}`}
              target="_blank"
              rel="noreferrer"
              data-testid="navixy-live-map-link"
              className="col-span-2 flex items-center justify-center gap-2 rounded-lg bg-sky-500/15 p-3 text-sm font-semibold text-sky-300 transition-colors hover:bg-sky-500/25 sm:col-span-3"
            >
              <MapPin className="h-4 w-4" /> Voir sur la carte
            </a>
          )}
        </div>
      )}
    </div>
  );
}
