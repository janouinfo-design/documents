import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RefreshCw, Loader2 } from "lucide-react";
import { getNavixyStatus, navixySync } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function SyncButton() {
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const { data: st } = useQuery({ queryKey: ["sync-status"], queryFn: getNavixyStatus });
  const connected = st?.connected;

  const onSync = async () => {
    setSyncing(true);
    try {
      const r = await navixySync();
      toast.success(`Synchronisation réussie · ${r.synced} véhicules (${r.created} ajoutés, ${r.updated} mis à jour)`);
      ["vehicles", "dashboard", "timeline", "sync-status"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
    } catch {
      toast.error("Échec de la synchronisation");
    } finally {
      setSyncing(false);
    }
  };

  return (
    <Button
      onClick={onSync}
      disabled={syncing || !connected}
      data-testid="sync-btn"
      variant="outline"
      title={connected ? `Connecté · ${st.imported_count}/${st.trackers_count} véhicules importés` : st?.error || "Synchronisation non connectée — vérifiez la clé API"}
      className="gap-2 border-slate-300 text-slate-700 hover:bg-slate-50"
    >
      {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
      Synchroniser
      <span className={`h-2 w-2 rounded-full ${connected ? "bg-emerald-500" : "bg-red-400"}`} data-testid="sync-status-dot" />
    </Button>
  );
}
