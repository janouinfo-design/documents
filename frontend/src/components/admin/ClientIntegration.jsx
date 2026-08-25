import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Save } from "lucide-react";
import { adminGetIntegration, adminUpdateIntegration } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";

export default function ClientIntegration({ tenantId }) {
  const qc = useQueryClient();
  const [apiHash, setApiHash] = useState("");
  const [saving, setSaving] = useState(false);
  const { data: integ, isLoading } = useQuery({
    queryKey: ["admin-integ", tenantId],
    queryFn: () => adminGetIntegration(tenantId),
  });

  const save = async (patch, okMsg = "Intégration mise à jour") => {
    setSaving(true);
    try {
      await adminUpdateIntegration(tenantId, patch);
      toast.success(okMsg);
      setApiHash("");
      qc.invalidateQueries({ queryKey: ["admin-integ", tenantId] });
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
    } catch (e) {
      toast.error(String(e?.response?.data?.detail || "Échec de la mise à jour"));
    } finally {
      setSaving(false);
    }
  };

  if (isLoading) return <Loader2 className="h-5 w-5 animate-spin text-slate-400" />;
  return (
    <div data-testid={`admin-integration-section-${tenantId}`}>
      <h3 className="mb-3 text-sm font-semibold uppercase tracking-wide text-slate-400">
        Intégration télématique (Navixy)
      </h3>
      <div className="space-y-4 rounded-xl border border-slate-200 p-4">
        <div className="flex flex-wrap items-center gap-8">
          <label className="flex items-center gap-3 text-sm font-medium text-slate-700">
            <Switch checked={!!integ?.enabled} disabled={saving} data-testid={`admin-integ-enabled-switch-${tenantId}`}
              onCheckedChange={(v) => save({ enabled: v }, v ? "Synchronisation activée" : "Synchronisation désactivée")} />
            Synchronisation active
          </label>
          <label className="flex items-center gap-3 text-sm font-medium text-slate-700">
            <Switch checked={!!integ?.write_enabled} disabled={saving} data-testid={`admin-integ-write-switch-${tenantId}`}
              onCheckedChange={(v) => save({ write_enabled: v }, v ? "Écriture télématique activée" : "Écriture télématique désactivée")} />
            Écriture autorisée
          </label>
          {integ?.last_sync_at && (
            <span className="text-xs text-slate-400">Dernière synchro : {String(integ.last_sync_at).slice(0, 16).replace("T", " ")}</span>
          )}
        </div>
        <div className="flex flex-wrap items-end gap-3">
          <div className="min-w-[260px] flex-1">
            <Label>Clé API (hash)</Label>
            <Input data-testid={`admin-integ-hash-input-${tenantId}`} type="password" value={apiHash}
              onChange={(e) => setApiHash(e.target.value)}
              placeholder={integ?.configured ? "•••••••• configurée — laisser vide pour conserver" : "Hash API du compte Navixy du client"}
              className="mt-1.5 font-mono text-sm" autoComplete="off" />
          </div>
          <Button data-testid={`admin-integ-save-btn-${tenantId}`} disabled={saving || !apiHash.trim()}
            onClick={() => save({ api_hash: apiHash.trim() }, "Clé API enregistrée")}
            className="gap-2 bg-slate-900 hover:bg-slate-800">
            {saving ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />} Enregistrer la clé
          </Button>
        </div>
        <p className="text-xs text-slate-400">
          La clé n'est jamais réaffichée. Sans clé, le client fonctionne normalement (sans synchronisation télématique).
        </p>
      </div>
    </div>
  );
}
