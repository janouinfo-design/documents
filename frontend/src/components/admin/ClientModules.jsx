import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Check, X, Loader2, ShieldAlert, Info } from "lucide-react";
import { adminUpdateTenant } from "@/lib/api";
import { MODULES } from "@/lib/rbac";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent, AlertDialogDescription,
  AlertDialogFooter, AlertDialogHeader, AlertDialogTitle,
} from "@/components/ui/alert-dialog";

export const enabledCount = (modules) => MODULES.filter((m) => modules?.[m.key] !== false).length;

export function ModulesBadge({ tenant }) {
  const n = enabledCount(tenant.modules);
  return (
    <Badge variant="outline" data-testid={`admin-client-modules-count-${tenant.id}`}
      className={cn("gap-1 tabular-nums", n === MODULES.length ? "border-slate-300 text-slate-600" : "border-amber-300 text-amber-700")}>
      Modules {n}/{MODULES.length}
    </Badge>
  );
}

function ModuleRow({ tenant, mod, pending, onChange }) {
  const on = tenant.modules?.[mod.key] !== false;
  return (
    <div data-testid={`admin-client-module-row-${mod.key}-${tenant.id}`}
      className={cn("flex items-center gap-3 rounded-xl border px-3.5 py-2.5 transition-colors",
        on ? "border-slate-200 bg-white" : "border-dashed border-slate-300 bg-slate-50")}>
      <span data-testid={`admin-client-module-state-${mod.key}-${tenant.id}`}
        className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-white",
          on ? "bg-emerald-500" : "bg-slate-400")}>
        {on ? <Check className="h-3 w-3" /> : <X className="h-3 w-3" />}
      </span>
      <span className={cn("min-w-0 flex-1 truncate text-sm font-medium", on ? "text-slate-800" : "text-slate-500")}>
        {mod.label}{mod.core && <span className="ml-1.5 text-[10px] font-semibold uppercase tracking-wide text-slate-400">socle</span>}
      </span>
      {pending === mod.key && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
      <Switch checked={on} disabled={!!pending} data-testid={`admin-client-module-${mod.key}-switch-${tenant.id}`}
        onCheckedChange={(v) => onChange(mod, v)} />
    </div>
  );
}

// Modules par client : ON immédiat ; OFF = confirmation explicite (socle + dépendances affichées avant validation).
// Aucune donnée supprimée côté serveur : seul l'accès est bloqué (403 MODULE_DISABLED).
export default function ClientModules({ tenant }) {
  const qc = useQueryClient();
  const [pending, setPending] = useState(null);
  const [confirm, setConfirm] = useState(null);

  const apply = async (mod, value) => {
    setPending(mod.key);
    try {
      await adminUpdateTenant(tenant.id, { modules: { [mod.key]: value } });
      toast.success(`Module ${mod.label} ${value ? "activé" : "désactivé"} — effet immédiat pour ${tenant.name}`);
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
    } catch (e) {
      const d = e?.response?.data?.detail;
      toast.error((typeof d === "string" && d) || d?.message || "Échec de la mise à jour du module");
    } finally {
      setPending(null);
    }
  };
  const onChange = (mod, value) => (value ? apply(mod, true) : setConfirm(mod));

  return (
    <div data-testid={`admin-client-modules-${tenant.id}`}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Modules</h3>
        <ModulesBadge tenant={tenant} />
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {MODULES.map((m) => <ModuleRow key={m.key} tenant={tenant} mod={m} pending={pending} onChange={onChange} />)}
      </div>
      <p className="mt-2 flex items-start gap-1.5 text-xs text-slate-400">
        <Info className="mt-0.5 h-3.5 w-3.5 shrink-0" />
        Désactiver un module bloque uniquement son accès (onglet, routes, API) pour ce client. Aucune donnée n'est supprimée : la réactivation restaure tout immédiatement.
      </p>
      <AlertDialog open={!!confirm} onOpenChange={(v) => !v && setConfirm(null)}>
        <AlertDialogContent data-testid="admin-module-confirm-dialog">
          <AlertDialogHeader>
            <AlertDialogTitle className="flex items-center gap-2">
              <ShieldAlert className={cn("h-5 w-5", confirm?.core ? "text-red-600" : "text-amber-600")} />
              Désactiver le module {confirm?.label} pour {tenant.name} ?
            </AlertDialogTitle>
            <AlertDialogDescription asChild>
              <div className="space-y-2 text-sm text-slate-600">
                <p data-testid="admin-module-confirm-note">{confirm?.note}</p>
                <p>Aucune donnée ne sera supprimée ni modifiée. Le client perd immédiatement l'accès (onglet masqué, API 403) et le retrouve dès la réactivation.</p>
              </div>
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel data-testid="admin-module-cancel-btn">Annuler</AlertDialogCancel>
            <AlertDialogAction data-testid="admin-module-confirm-btn"
              className={confirm?.core ? "bg-red-600 hover:bg-red-700" : "bg-slate-900 hover:bg-slate-800"}
              onClick={() => { const m = confirm; setConfirm(null); apply(m, false); }}>
              Désactiver {confirm?.label}
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
