import { useState } from "react";
import { Navigate } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Plus, Building2, ChevronDown, ChevronRight, Truck, FileText, Users, Wifi, WifiOff } from "lucide-react";
import { adminOverview, adminUpdateTenant } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import NewClientDialog from "@/components/admin/NewClientDialog";
import ClientUsers from "@/components/admin/ClientUsers";
import ClientIntegration from "@/components/admin/ClientIntegration";

function ClientCard({ tenant, expanded, onToggle }) {
  const qc = useQueryClient();
  const update = async (patch, okMsg) => {
    try {
      await adminUpdateTenant(tenant.id, patch);
      toast.success(okMsg);
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
    } catch (e) {
      toast.error(String(e?.response?.data?.detail || "Échec de la mise à jour"));
    }
  };
  const docsModule = tenant.modules?.documents !== false;
  return (
    <div className={cn("rounded-2xl border bg-white transition-colors",
      tenant.disabled ? "border-red-200 opacity-70" : "border-slate-200")}
      data-testid={`admin-client-${tenant.id}`}>
      <button onClick={onToggle} data-testid={`admin-client-toggle-${tenant.id}`}
        className="flex w-full items-center gap-4 px-5 py-4 text-left">
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
        {tenant.integration?.configured ? (
          <Badge variant="outline" className={cn("gap-1", tenant.integration.enabled ? "border-emerald-300 text-emerald-700" : "border-slate-300 text-slate-500")}
            data-testid={`admin-client-integration-badge-${tenant.id}`}>
            <Wifi className="h-3 w-3" /> Télématique {tenant.integration.enabled ? "active" : "inactive"}
          </Badge>
        ) : (
          <Badge variant="outline" className="gap-1 border-slate-200 text-slate-400">
            <WifiOff className="h-3 w-3" /> Sans télématique
          </Badge>
        )}
        {tenant.disabled && <Badge className="bg-red-100 text-red-700 hover:bg-red-100">Désactivé</Badge>}
      </button>
      {expanded && (
        <div className="space-y-6 border-t border-slate-100 px-5 py-5">
          <div className="flex flex-wrap items-center gap-8">
            <label className="flex items-center gap-3 text-sm font-medium text-slate-700">
              <Switch checked={!tenant.disabled} data-testid={`admin-client-active-switch-${tenant.id}`}
                onCheckedChange={(v) => update({ disabled: !v }, v ? "Client réactivé" : "Client désactivé")} />
              Client actif
            </label>
            <label className="flex items-center gap-3 text-sm font-medium text-slate-700">
              <Switch checked={docsModule} data-testid={`admin-client-module-docs-switch-${tenant.id}`}
                onCheckedChange={(v) => update({ modules: { documents: v } }, v ? "Module Documents activé" : "Module Documents désactivé")} />
              Module Documents
            </label>
          </div>
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
            {tenants.length} client(s) · création de comptes, intégration télématique et modules par client.
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
