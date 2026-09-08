import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Send } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";
import { adminOverview, adminListTenantVehicles, adminTransferArchive, getActingTenant } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

export default function TransferArchiveDialog({ archive, open, onOpenChange }) {
  const qc = useQueryClient();
  const { user } = useAuth();
  const [targetTenant, setTargetTenant] = useState("");
  const [targetVehicle, setTargetVehicle] = useState("");
  const [busy, setBusy] = useState(false);
  const sourceTenantId = getActingTenant()?.id || user?.tenant_id;

  const { data: overview } = useQuery({ queryKey: ["admin-overview"], queryFn: adminOverview, enabled: open });
  const tenants = overview?.tenants || [];
  const { data: vehicles = [], isLoading: vLoading } = useQuery({
    queryKey: ["admin-tenant-vehicles", targetTenant],
    queryFn: () => adminListTenantVehicles(targetTenant),
    enabled: open && !!targetTenant,
  });

  const close = (o) => {
    if (!o) { setTargetTenant(""); setTargetVehicle(""); }
    onOpenChange(o);
  };

  const confirm = async () => {
    setBusy(true);
    try {
      const r = await adminTransferArchive({
        source_tenant_id: sourceTenantId,
        archive_vehicle_id: archive.id,
        target_tenant_id: targetTenant,
        target_vehicle_id: targetVehicle,
      });
      toast.success(`${r.transferred} document(s) transféré(s) vers ${r.target_plaque || targetTenant}`);
      qc.invalidateQueries({ queryKey: ["vehicles-archive"] });
      qc.invalidateQueries({ queryKey: ["archive-docs", archive.id] });
      close(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Transfert impossible");
    } finally {
      setBusy(false);
    }
  };

  if (!archive) return null;
  return (
    <Dialog open={open} onOpenChange={close}>
      <DialogContent data-testid="archive-transfer-dialog" className="max-w-md">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Transférer les documents — {archive.plaque}</DialogTitle>
          <DialogDescription>
            Les {archive.documents_count} document(s) conservés seront rattachés au véhicule choisi
            du client repreneur, et marqués « à vérifier » pour validation.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div>
            <p className="mb-1.5 text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Client repreneur</p>
            <Select value={targetTenant} onValueChange={(v) => { setTargetTenant(v); setTargetVehicle(""); }}>
              <SelectTrigger data-testid="transfer-tenant-select"><SelectValue placeholder="Choisir un client…" /></SelectTrigger>
              <SelectContent>
                {tenants.map((t) => (
                  <SelectItem key={t.id} value={t.id}>{t.name} ({t.vehicles} véhicule{t.vehicles > 1 ? "s" : ""})</SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
          {targetTenant && (
            <div>
              <p className="mb-1.5 text-xs font-bold uppercase tracking-[0.08em] text-slate-500">Véhicule cible</p>
              {vLoading ? (
                <div className="flex items-center gap-2 py-2 text-sm text-slate-400"><Loader2 className="h-4 w-4 animate-spin" /> Chargement…</div>
              ) : (
                <Select value={targetVehicle} onValueChange={setTargetVehicle}>
                  <SelectTrigger data-testid="transfer-vehicle-select"><SelectValue placeholder="Choisir le véhicule…" /></SelectTrigger>
                  <SelectContent>
                    {vehicles.map((v) => (
                      <SelectItem key={v.id} value={v.id}>{v.plaque || v.id} — {[v.marque, v.modele].filter(Boolean).join(" ")}</SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              )}
            </div>
          )}
        </div>
        <div className="flex justify-end gap-2 border-t border-slate-100 pt-4">
          <Button variant="outline" data-testid="transfer-cancel-btn" onClick={() => close(false)}>Annuler</Button>
          <Button data-testid="transfer-confirm-btn" onClick={confirm} disabled={busy || !targetTenant || !targetVehicle}
                  className="gap-2 bg-slate-900 hover:bg-slate-800">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />} Transférer
          </Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
