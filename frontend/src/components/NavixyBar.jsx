import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Satellite, RefreshCw, Loader2, AlertTriangle } from "lucide-react";
import { getNavixyStatus, navixySync } from "@/lib/api";
import { Button } from "@/components/ui/button";

export default function NavixyBar() {
  const qc = useQueryClient();
  const [syncing, setSyncing] = useState(false);
  const { data: st } = useQuery({ queryKey: ["navixy-status"], queryFn: getNavixyStatus });

  const onSync = async () => {
    setSyncing(true);
    try {
      const r = await navixySync();
      toast.success(`Navixy synchronisé · ${r.synced} véhicules (${r.created} ajoutés, ${r.updated} maj)`);
      ["vehicles", "dashboard", "timeline", "navixy-status"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
    } catch {
      toast.error("Échec de la synchronisation Navixy");
    } finally {
      setSyncing(false);
    }
  };

  const connected = st?.connected;

  return (
    <div
      data-testid="navixy-bar"
      className="flex flex-col gap-3 overflow-hidden rounded-xl border border-slate-800 bg-slate-900 p-4 text-white sm:flex-row sm:items-center sm:justify-between"
    >
      <div className="flex items-center gap-3">
        <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-white/10">
          <Satellite className="h-5 w-5 text-sky-300" />
          {connected && (
            <span className="absolute -right-0.5 -top-0.5 h-3 w-3 rounded-full border-2 border-slate-900 bg-emerald-400" />
          )}
        </span>
        <div>
          <div className="flex items-center gap-2">
            <p className="font-display text-sm font-bold tracking-tight">Navixy</p>
            {connected ? (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-emerald-500/15 px-2 py-0.5 text-[11px] font-semibold text-emerald-300">
                <span className="h-1.5 w-1.5 rounded-full bg-emerald-400" /> Connecté · {st.account}
              </span>
            ) : (
              <span className="inline-flex items-center gap-1.5 rounded-full bg-red-500/15 px-2 py-0.5 text-[11px] font-semibold text-red-300">
                <AlertTriangle className="h-3 w-3" /> Non connecté
              </span>
            )}
          </div>
          <p className="text-xs text-slate-400">
            {connected
              ? `${st.imported_count}/${st.trackers_count} véhicules importés · cumul km synchronisé`
              : st?.error || "Vérifiez la clé API Navixy"}
          </p>
        </div>
      </div>
      <Button
        onClick={onSync}
        disabled={syncing || !connected}
        data-testid="navixy-sync-btn"
        className="gap-2 bg-white text-slate-900 hover:bg-slate-100"
      >
        {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        Synchroniser
      </Button>
    </div>
  );
}
