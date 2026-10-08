import { useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { adminListTenantDrivers, adminListTenantVehicles } from "@/lib/api";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export const ROLE_OPTIONS = [
  { value: "admin", label: "Admin (lecture + écriture)" },
  { value: "manager", label: "Manager (véhicules de son périmètre)" },
  { value: "read_only", label: "Lecture seule" },
  { value: "driver", label: "Chauffeur (ses pleins / amendes / véhicules)" },
];
export const roleShort = (r) => ({ admin: "admin", manager: "manager", read_only: "lecture seule", driver: "chauffeur", superadmin: "super admin" }[r] || r);

export const useTenantDrivers = (tenantId, enabled = true) =>
  useQuery({ queryKey: ["admin-drivers", tenantId], queryFn: () => adminListTenantDrivers(tenantId), enabled: !!tenantId && enabled });
export const useTenantVehicles = (tenantId, enabled = true) =>
  useQuery({ queryKey: ["admin-vehicles", tenantId], queryFn: () => adminListTenantVehicles(tenantId), enabled: !!tenantId && enabled });

// Liaison compte ↔ conducteur : choix EXPLICITE dans le référentiel du MÊME client (aucune déduction nom / email / matricule).
export function DriverLinkField({ tenantId, value, onChange, currentUserEmail, testId = "admin-user-driver-select" }) {
  const { data: drivers = [], isLoading } = useTenantDrivers(tenantId);
  return (
    <div>
      <Label>Conducteur lié</Label>
      <select data-testid={testId} value={value || ""} onChange={(e) => onChange(e.target.value)}
        className="mt-1.5 h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm">
        <option value="">— Aucun (compte en attente de liaison) —</option>
        {drivers.map((d) => {
          const linkedElsewhere = d.linked_user_email && d.linked_user_email !== currentUserEmail;
          return (
            <option key={d.id} value={d.id} disabled={linkedElsewhere}>
              {d.display}{d.matricule_interne ? ` · ${d.matricule_interne}` : ""}{d.actif === false ? " · inactif" : ""}{linkedElsewhere ? ` · déjà lié (${d.linked_user_email})` : ""}
            </option>
          );
        })}
      </select>
      <p className="mt-1 text-xs text-slate-400" data-testid={`${testId}-hint`}>
        {isLoading ? "Chargement des conducteurs…" : drivers.length === 0 ? "Aucun conducteur dans ce client — créez-le d'abord dans Conducteurs." : "Sans liaison, le chauffeur voit une page d'attente (aucune donnée)."}
      </p>
    </div>
  );
}

// Scope manager : liste explicite de véhicules du client. [] = aucun véhicule (jamais « toute la flotte »).
export function VehicleScopeField({ tenantId, value = [], onChange, testId = "admin-user-scope" }) {
  const { data: vehicles = [], isLoading } = useTenantVehicles(tenantId);
  const [q, setQ] = useState("");
  const shown = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? vehicles.filter((v) => `${v.plaque} ${v.marque || ""} ${v.modele || ""}`.toLowerCase().includes(t)) : vehicles;
  }, [vehicles, q]);
  const toggle = (id) => onChange(value.includes(id) ? value.filter((x) => x !== id) : [...value, id]);
  return (
    <div>
      <div className="flex items-center justify-between">
        <Label>Périmètre véhicules</Label>
        <span className="text-xs font-semibold text-slate-600" data-testid={`${testId}-count`}>{value.length} véhicule{value.length > 1 ? "s" : ""} sélectionné{value.length > 1 ? "s" : ""}</span>
      </div>
      <div className="relative mt-1.5">
        <Search className="pointer-events-none absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
        <Input data-testid={`${testId}-search`} value={q} onChange={(e) => setQ(e.target.value)} placeholder="Filtrer par plaque, marque…" className="h-8 pl-8 text-xs" />
      </div>
      <ul className="mt-1.5 max-h-44 divide-y divide-slate-100 overflow-y-auto rounded-md border border-slate-200" data-testid={`${testId}-list`}>
        {isLoading && <li className="px-3 py-2 text-xs text-slate-400">Chargement…</li>}
        {!isLoading && vehicles.length === 0 && <li className="px-3 py-2 text-xs text-slate-400">Aucun véhicule dans ce client.</li>}
        {shown.map((v) => (
          <li key={v.id}>
            <label className="flex cursor-pointer items-center gap-2 px-3 py-1.5 text-sm hover:bg-slate-50">
              <input type="checkbox" checked={value.includes(v.id)} onChange={() => toggle(v.id)} data-testid={`${testId}-vehicle-${v.id}`} className="h-4 w-4 accent-slate-900" />
              <span className="font-semibold text-slate-900">{v.plaque}</span>
              <span className="text-xs text-slate-500">{[v.marque, v.modele].filter(Boolean).join(" ")}</span>
            </label>
          </li>
        ))}
      </ul>
      <p className="mt-1 text-xs text-slate-400">Un périmètre vide = aucun véhicule visible. Le serveur relit ce périmètre à chaque requête.</p>
    </div>
  );
}
