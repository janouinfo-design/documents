import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { RefreshCw, Loader2 } from "lucide-react";
import { getNavixyStatus, navixySync } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";

const fmtSync = (iso) => {
  if (!iso) return null;
  const d = new Date(iso);
  return d.toLocaleString("fr-CH", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
};

export default function SyncButton() {
  const qc = useQueryClient();
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const [syncing, setSyncing] = useState(false);
  const { data: st, isLoading: stLoading } = useQuery({
    queryKey: ["sync-status"], queryFn: getNavixyStatus, enabled: !readOnly, refetchInterval: 120000,
  });
  const connected = st?.connected;
  // Écriture métier : masqué pour les comptes en lecture seule (le backend renvoie 403 de toute façon)
  if (readOnly) return null;

  const onSync = async () => {
    setSyncing(true);
    try {
      const r = await navixySync();
      toast.success(`Synchronisation réussie · ${r.synced} véhicules (${r.created} ajoutés, ${r.updated} mis à jour)`);
      ["vehicles", "dashboard", "timeline", "sync-status"].forEach((k) =>
        qc.invalidateQueries({ queryKey: [k] })
      );
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de la synchronisation");
      qc.invalidateQueries({ queryKey: ["sync-status"] });
    } finally {
      setSyncing(false);
    }
  };

  // Jamais de point vert si l'état réel est inconnu
  const dotClass = syncing
    ? "bg-amber-400 animate-pulse"
    : stLoading || st === undefined
      ? "bg-slate-300"
      : connected
        ? "bg-emerald-500"
        : "bg-red-400";

  const caption = syncing
    ? "Synchronisation en cours…"
    : stLoading || st === undefined
      ? "État en cours de vérification"
      : !connected
        ? (st?.configured ? "Erreur de connexion télématique" : "Non configuré")
        : st?.last_sync_at
          ? `Dernière sync : ${fmtSync(st.last_sync_at)}`
          : "Connecté · jamais synchronisé";

  return (
    <div className="flex flex-col items-end gap-0.5">
      <Button
        onClick={onSync}
        disabled={syncing || !connected}
        data-testid="sync-btn"
        variant="outline"
        title={connected ? `Connecté · ${st.imported_count}/${st.trackers_count} véhicules importés` : st?.error || "Synchronisation non connectée — vérifiez la clé API"}
        className="gap-2 border-slate-300 text-slate-700 hover:bg-slate-50"
      >
        {syncing ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
        {syncing ? "Synchronisation…" : "Synchroniser"}
        <span className={`h-2 w-2 rounded-full ${dotClass}`} data-testid="sync-status-dot" />
      </Button>
      <span className="text-[10px] text-slate-400" data-testid="sync-last-caption">{caption}</span>
    </div>
  );
}
