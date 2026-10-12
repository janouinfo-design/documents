import { useEffect, useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Plus, Building2, ChevronDown, ChevronRight, Truck, FileText, Users, Wifi, WifiOff, LifeBuoy } from "lucide-react";
import { adminOverview, adminUpdateTenant } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import NewClientDialog from "@/components/admin/NewClientDialog";
import ClientUsers from "@/components/admin/ClientUsers";
import ClientIntegration from "@/components/admin/ClientIntegration";
import ClientModules, { ModulesBadge } from "@/components/admin/ClientModules";
import ImpersonateDialog from "@/components/admin/ImpersonateDialog";

function ClientCard({ tenant, expanded, onToggle }) {
  const qc = useQueryClient();
  const [impOpen, setImpOpen] = useState(false);
  const update = async (patch, okMsg) => {
    try {
      await adminUpdateTenant(tenant.id, patch);
      toast.success(okMsg);
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
    } catch (e) {
      toast.error(String(e?.response?.data?.detail || "Échec de la mise à jour"));
    }
  };
  return (
    <div className={cn("rounded-2xl border bg-white transition-colors",
      tenant.disabled ? "border-red-200 opacity-70" : "border-slate-200")}
      data-testid={`admin-client-${tenant.id}`}>
      <div className="flex w-full items-center gap-4 px-5 py-4">
        <button onClick={onToggle} data-testid={`admin-client-toggle-${tenant.id}`}
          className="flex min-w-0 flex-1 items-center gap-4 text-left">
          {expanded ? <ChevronDown className="h-4 w-4 shrink-0 text-slate-400" /> : <ChevronRight className="h-4 w-4 shrink-0 text-slate-400" />}
          <div className="min-w-0 flex-1">
            <p className="truncate font-display font-bold text-slate-900">{tenant.name}</p>
            <p className="text-xs text-slate-400">{tenant.id}</p>
          </div>
          <div className="hidden items-center gap-4 text-sm text-slate-500 sm:flex">
            <span className="flex items-center gap-1.5" title="Véhicules"><Truck className="h-4 w-4 text-slate-400" />{tenant.vehicles}</span>
            <span className="flex items-center gap-1.5" title="Documents"><FileText className="h-4 w-4 text-slate-400" />{tenant.documents}</span>
            <span className="flex items-center gap-1.5" title="Utilisateurs"><Users className="h-4 w-4 text-slate-400" />{tenant.users}</span>
          </div>
          <ModulesBadge tenant={tenant} />
          {tenant.integration?.configured ? (
            <Badge variant="outline" className={cn("gap-1", tenant.integration.enabled ? "border-emerald-300 text-emerald-700" : "border-slate-300 text-slate-500")}
              data-testid={`admin-client-integration-badge-${tenant.id}`}>
              <Wifi className="h-3 w-3" /> {tenant.integration.demo ? "Télématique (démo)" : `Télématique ${tenant.integration.enabled ? "active" : "inactive"}`}
            </Badge>
          ) : (
            <Badge variant="outline" className="gap-1 border-slate-200 text-slate-400">
              <WifiOff className="h-3 w-3" /> Sans télématique
            </Badge>
          )}
          {tenant.disabled && <Badge className="bg-red-100 text-red-700 hover:bg-red-100">Désactivé</Badge>}
        </button>
        <Button size="sm" variant="outline" data-testid={`admin-view-client-btn-${tenant.id}`}
          className="shrink-0 gap-1.5" disabled={tenant.disabled}
          title={tenant.disabled ? "Client désactivé" : "Se connecter comme un utilisateur de ce client (mode assistance, droits exacts de l'utilisateur)"}
          onClick={() => setImpOpen(true)}>
          <LifeBuoy className="h-3.5 w-3.5" /> Se connecter
        </Button>
      </div>
      <ImpersonateDialog tenant={tenant} open={impOpen} onOpenChange={setImpOpen} />
      {expanded && (
        <div className="space-y-6 border-t border-slate-100 px-5 py-5">
          <label className="flex items-center gap-3 text-sm font-medium text-slate-700">
            <Switch checked={!tenant.disabled} data-testid={`admin-client-active-switch-${tenant.id}`}
              onCheckedChange={(v) => update({ disabled: !v }, v ? "Client réactivé" : "Client désactivé")} />
            Client actif
          </label>
          <ClientModules tenant={tenant} />
          <ClientUsers tenantId={tenant.id} />
          <ClientIntegration tenantId={tenant.id} />
        </div>
      )}
    </div>
  );
}

export default function AdminPage() {
  const { user } = useAuth();
  const [newOpen, setNewOpen] = useState(false);
  const [expanded, setExpanded] = useState(null);
  useEffect(() => {
    if (new URLSearchParams(window.location.search).get("assist") === "ended") {
      toast.info("Session d'assistance terminée — droits Super Admin restaurés");
      window.history.replaceState({}, document.title, "/admin");
    }
  }, []);
  const { data, isLoading } = useQuery({
    queryKey: ["admin-overview"],
    queryFn: adminOverview,
    enabled: user?.role === "superadmin",
  });
  if (user && user.role !== "superadmin") return <Navigate to="/" replace />;
  const tenants = data?.tenants || [];
  return (
    <div className="space-y-6" data-testid="admin-page">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h1 className="font-display text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
            Administration des clients
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {tenants.length} client(s) · comptes, modules activés et intégration télématique par client.
          </p>
        </div>
        <Button data-testid="admin-new-client-btn" onClick={() => setNewOpen(true)} className="gap-2 bg-slate-900 hover:bg-slate-800">
          <Plus className="h-4 w-4" /> Nouveau client
        </Button>
      </div>
      {isLoading ? (
        <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
      ) : tenants.length === 0 ? (
        <div className="rounded-2xl border border-dashed border-slate-300 p-12 text-center text-slate-400" data-testid="admin-empty">
          <Building2 className="mx-auto mb-3 h-8 w-8" /> Aucun client
        </div>
      ) : (
        <div className="space-y-3">
          {tenants.map((t) => (
            <ClientCard key={t.id} tenant={t} expanded={expanded === t.id}
              onToggle={() => setExpanded(expanded === t.id ? null : t.id)} />
          ))}
        </div>
      )}
      <NewClientDialog open={newOpen} onOpenChange={setNewOpen} />
    </div>
  );
}
