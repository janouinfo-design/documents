import { useQuery } from "@tanstack/react-query";
import { Radio, MapPin, Gauge, Clock, Link2, Link2Off, AlertTriangle, Power } from "lucide-react";
import { getVehicleTelematics } from "@/lib/api";
import { fmtKm } from "@/lib/format";
import { cn } from "@/lib/utils";

const STATUS_STYLE = {
  moving: { dot: "bg-emerald-500", label: "text-emerald-700" },
  idle: { dot: "bg-amber-500", label: "text-amber-700" },
  parked: { dot: "bg-slate-400", label: "text-slate-600" },
};
const LINK = {
  LIE: { icon: Link2, text: "Apparié au traceur", cls: "text-emerald-700 bg-emerald-50 border-emerald-200" },
  DIVERGENCE: { icon: AlertTriangle, text: "Divergence à vérifier", cls: "text-amber-700 bg-amber-50 border-amber-200" },
  NON_LIE: { icon: Link2Off, text: "Non apparié", cls: "text-slate-600 bg-slate-50 border-slate-200" },
};

const sinceLabel = (m) => (m < 60 ? `il y a ${m} min` : `il y a ${Math.floor(m / 60)} h ${m % 60 ? (m % 60) + " min" : ""}`.trim());

// Encart « Suivi télématique (démo) » — visible uniquement pour les tenants de démonstration (données fictives).
export default function TelematicsCard({ vehicleId }) {
  const { data } = useQuery({
    queryKey: ["vehicle-telematics", vehicleId],
    queryFn: () => getVehicleTelematics(vehicleId),
    enabled: !!vehicleId,
    retry: false,
  });
  if (!data?.demo || !data?.available) return null;
  const st = STATUS_STYLE[data.status] || STATUS_STYLE.parked;
  const link = LINK[data.link_status] || LINK.LIE;
  const LinkIcon = link.icon;

  return (
    <div data-testid="vehicle-telematics-card"
      className="rounded-2xl border border-indigo-100 bg-gradient-to-br from-indigo-50/70 to-white p-5">
      <div className="mb-4 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-indigo-600 text-white">
            <Radio className="h-4 w-4" />
          </span>
          <div>
            <h4 className="text-sm font-semibold text-slate-900">Suivi télématique</h4>
            <p className="text-[11px] font-medium uppercase tracking-wide text-indigo-500">Données de démonstration</p>
          </div>
        </div>
        <span className={cn("flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium", link.cls)}
          data-testid="vehicle-telematics-link">
          <LinkIcon className="h-3.5 w-3.5" /> {link.text}
        </span>
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-3 sm:grid-cols-4">
        <div>
          <p className="text-[11px] font-medium uppercase tracking-wide text-slate-400">État</p>
          <p className={cn("mt-0.5 flex items-center gap-1.5 text-sm font-semibold", st.label)}>
            <span className={cn("h-2 w-2 rounded-full", st.dot)} /> {data.status_label}
          </p>
        </div>
        <div>
          <p className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-slate-400"><Gauge className="h-3 w-3" /> Vitesse</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800">{data.status === "moving" ? `${data.speed_kmh} km/h` : "—"}</p>
        </div>
        <div>
          <p className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-slate-400"><Clock className="h-3 w-3" /> Dernier point</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800" data-testid="vehicle-telematics-seen">{sinceLabel(data.last_seen_minutes)}</p>
        </div>
        <div>
          <p className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-slate-400"><Power className="h-3 w-3" /> Contact</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800">{data.ignition ? "Mis" : "Coupé"}</p>
        </div>
        <div className="col-span-2">
          <p className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-slate-400"><MapPin className="h-3 w-3" /> Position</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800">{data.position?.label}</p>
          <p className="text-xs text-slate-400">{data.position?.lat}, {data.position?.lng}</p>
        </div>
        <div className="col-span-2">
          <p className="flex items-center gap-1 text-[11px] font-medium uppercase tracking-wide text-slate-400"><Gauge className="h-3 w-3" /> Odomètre télématique</p>
          <p className="mt-0.5 text-sm font-semibold text-slate-800">{fmtKm(data.odometer_km)}</p>
          <p className="text-xs text-slate-400">Traceur {data.tracker_id}</p>
        </div>
      </div>
      {data.note && <p className="mt-3 text-xs text-slate-400">{data.note}</p>}
    </div>
  );
}
