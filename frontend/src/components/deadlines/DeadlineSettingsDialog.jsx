import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { putDeadlineSettings } from "@/lib/api";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";

export default function DeadlineSettingsDialog({ open, onOpenChange, thresholds }) {
  const qc = useQueryClient();
  const [urgent, setUrgent] = useState(30);
  const [warning, setWarning] = useState(90);
  const [interval, setInterval] = useState(24);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    if (open && thresholds) {
      setUrgent(thresholds.urgent_days);
      setWarning(thresholds.warning_days);
      setInterval(thresholds.controle_interval_months ?? 24);
    }
  }, [open, thresholds]);

  const save = async () => {
    const u = parseInt(urgent, 10);
    const w = parseInt(warning, 10);
    const m = parseInt(interval, 10);
    if (!u || !w || u < 1 || u >= w || w > 730) {
      toast.error("Seuils invalides : 1 ≤ urgent < à planifier ≤ 730 jours");
      return;
    }
    if (!m || m < 1 || m > 120) {
      toast.error("Intervalle de contrôle invalide : 1 à 120 mois");
      return;
    }
    setSaving(true);
    try {
      await putDeadlineSettings({ urgent_days: u, warning_days: w, controle_interval_months: m });
      toast.success("Seuils d'échéances enregistrés");
      ["deadlines", "deadline-settings", "dashboard", "alerts", "all-documents", "vehicles", "timeline"]
        .forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de l'enregistrement des seuils");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md" data-testid="deadline-settings-dialog">
        <DialogHeader>
          <DialogTitle>Seuils d'échéances</DialogTitle>
          <DialogDescription>
            Ces seuils s'appliquent à tout votre compte : Dashboard, Échéances, fiches véhicules et alertes.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          <div className="space-y-1.5">
            <Label htmlFor="threshold-urgent">Urgent — échéance à moins de (jours)</Label>
            <Input id="threshold-urgent" data-testid="threshold-urgent-input" type="number" min={1} max={729}
                   value={urgent} onChange={(e) => setUrgent(e.target.value)} />
          </div>
          <div className="space-y-1.5">
            <Label htmlFor="threshold-warning">À planifier — échéance à moins de (jours)</Label>
            <Input id="threshold-warning" data-testid="threshold-warning-input" type="number" min={2} max={730}
                   value={warning} onChange={(e) => setWarning(e.target.value)} />
          </div>
          <p className="text-xs text-slate-500">
            Au-delà du seuil « à planifier », l'échéance est considérée comme OK. Valeurs par défaut : 30 / 90 jours.
          </p>
          <div className="space-y-1.5 border-t border-slate-100 pt-4">
            <Label htmlFor="threshold-interval">Contrôle technique estimé — intervalle (mois)</Label>
            <Input id="threshold-interval" data-testid="threshold-interval-input" type="number" min={1} max={120}
                   value={interval} onChange={(e) => setInterval(e.target.value)} />
            <p className="text-xs text-slate-500">
              Sans date de prochain contrôle ni document daté, une échéance <span className="font-semibold">estimée</span> est
              calculée depuis la dernière expertise de la carte grise + cet intervalle (défaut : 24 mois). Rien n'est écrit en base.
            </p>
          </div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="deadline-settings-cancel">
            Annuler
          </Button>
          <Button onClick={save} disabled={saving} data-testid="deadline-settings-save"
                  className="bg-slate-900 hover:bg-slate-800">
            {saving ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
