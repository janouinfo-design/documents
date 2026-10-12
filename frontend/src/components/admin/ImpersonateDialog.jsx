import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { toast } from "sonner";
import { LifeBuoy, Loader2, Truck, UserRound } from "lucide-react";
import { adminImpersonate, adminListUsers, beginImpersonation } from "@/lib/api";
import { ROLE_LABELS } from "@/lib/rbac";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { cn } from "@/lib/utils";

const apiError = (err, fallback) => {
  const d = err?.response?.data?.detail;
  return (typeof d === "string" && d) || d?.message || fallback;
};

function UserRow({ u, selected, onSelect }) {
  const scope = u.role === "manager" ? (u.vehicle_scope || []).length : null;
  return (
    <button type="button" onClick={() => onSelect(u)} data-testid={`impersonate-user-${u.email}`}
      aria-pressed={selected}
      className={cn("flex w-full items-center gap-3 rounded-xl border px-4 py-3 text-left transition-colors",
        selected ? "border-indigo-500 bg-indigo-50" : "border-slate-200 bg-white hover:border-slate-300 hover:bg-slate-50")}>
      <span className={cn("flex h-9 w-9 shrink-0 items-center justify-center rounded-full",
        selected ? "bg-indigo-600 text-white" : "bg-slate-100 text-slate-500")}>
        <UserRound className="h-4 w-4" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-slate-900">{u.name || u.email}</span>
        <span className="block truncate text-xs text-slate-500">{u.email}</span>
      </span>
      <span className="flex shrink-0 items-center gap-1.5 text-xs font-medium capitalize text-slate-600">
        {ROLE_LABELS[u.role] || u.role}
        {scope != null && (
          <span className="flex items-center gap-1 normal-case text-slate-400" data-testid={`impersonate-user-scope-${u.email}`}>
            · <Truck className="h-3 w-3" /> {scope} véhicule{scope > 1 ? "s" : ""}
          </span>
        )}
      </span>
    </button>
  );
}

// « Se connecter » : choisir un utilisateur ACTIF du client ; l'identité et les droits exacts sont résolus côté serveur.
export default function ImpersonateDialog({ tenant, open, onOpenChange }) {
  const [selected, setSelected] = useState(null);
  const [busy, setBusy] = useState(false);
  const { data: users = [], isLoading } = useQuery({
    queryKey: ["admin-users", tenant.id],
    queryFn: () => adminListUsers(tenant.id),
    enabled: open,
  });
  const active = users.filter((u) => !u.disabled && u.role !== "superadmin");

  const go = async () => {
    if (!selected) return;
    setBusy(true);
    try {
      const data = await adminImpersonate(tenant.id, selected.id);
      beginImpersonation({ ...data, tenant: data.tenant || { id: tenant.id, name: tenant.name } });
      window.location.assign("/");
    } catch (e) {
      toast.error(apiError(e, "Connexion en mode assistance impossible"));
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { if (!busy) { onOpenChange(v); if (!v) setSelected(null); } }}>
      <DialogContent data-testid="impersonate-dialog" className="max-h-[90vh] overflow-y-auto sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <LifeBuoy className="h-5 w-5 text-indigo-600" /> Se connecter — {tenant.name}
          </DialogTitle>
          <DialogDescription>
            Utilisateurs actifs de ce client. Vous obtiendrez exactement les droits de l'utilisateur choisi (rôle, périmètre véhicules, modules actifs) — son mot de passe n'est ni lu ni modifié. Chaque session est auditée.
          </DialogDescription>
        </DialogHeader>
        {isLoading ? (
          <div className="flex justify-center py-8"><Loader2 className="h-5 w-5 animate-spin text-slate-400" /></div>
        ) : active.length === 0 ? (
          <p className="rounded-xl border border-dashed border-slate-300 px-4 py-6 text-center text-sm text-slate-400" data-testid="impersonate-empty">
            Aucun utilisateur actif — créez ou réactivez un compte dans la section Utilisateurs.
          </p>
        ) : (
          <div className="space-y-2" data-testid="impersonate-user-list">
            {active.map((u) => <UserRow key={u.id} u={u} selected={selected?.id === u.id} onSelect={setSelected} />)}
          </div>
        )}
        <DialogFooter>
          <Button onClick={go} disabled={!selected || busy} data-testid="impersonate-confirm-btn"
            className="gap-2 bg-indigo-600 hover:bg-indigo-700">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <LifeBuoy className="h-4 w-4" />}
            Se connecter comme cet utilisateur
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
