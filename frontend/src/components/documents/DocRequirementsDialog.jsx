import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { getDocRequirements, putDocRequirements } from "@/lib/api";

const PROFIL_LABELS = {
  base: "Tous les véhicules",
  achete: "Véhicule acheté",
  leasing: "Véhicule en leasing",
  thermique: "Thermique",
  electrique: "Électrique",
  hybride: "Hybride / PHEV",
};

export default function DocRequirementsDialog({ categories = [], open, onOpenChange }) {
  const qc = useQueryClient();
  const { data } = useQuery({ queryKey: ["doc-requirements"], queryFn: getDocRequirements, enabled: open });
  const [reqs, setReqs] = useState({});
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (data?.requirements) setReqs(data.requirements);
  }, [data]);

  const toggle = (profil, cat) =>
    setReqs((p) => {
      const cur = p[profil] || [];
      return { ...p, [profil]: cur.includes(cat) ? cur.filter((c) => c !== cat) : [...cur, cat] };
    });

  const save = async () => {
    setBusy(true);
    try {
      const initial = data?.requirements || {};
      const changed = Object.keys(PROFIL_LABELS).filter((p) => {
        const a = [...(initial[p] || [])].sort();
        const b = [...(reqs[p] || [])].sort();
        return a.length !== b.length || a.some((x, i) => x !== b[i]);
      });
      for (const profil of changed) {
        await putDocRequirements(profil, reqs[profil] || []);
      }
      toast.success(changed.length ? "Documents requis enregistrés" : "Aucun changement");
      qc.invalidateQueries({ queryKey: ["doc-requirements"] });
      qc.invalidateQueries({ queryKey: ["dashboard"] });
      onOpenChange(false);
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Échec de l'enregistrement");
      qc.invalidateQueries({ queryKey: ["doc-requirements"] });
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-2xl overflow-y-auto" data-testid="doc-requirements-dialog">
        <DialogHeader>
          <DialogTitle>Documents requis par profil de véhicule</DialogTitle>
          <DialogDescription>
            La conformité documentaire d'un véhicule combine « Tous les véhicules » + son mode de financement + son énergie.
          </DialogDescription>
        </DialogHeader>
        <div className="space-y-4">
          {Object.entries(PROFIL_LABELS).map(([profil, label]) => (
            <div key={profil} className="rounded-lg border border-slate-200 p-3" data-testid={`req-profil-${profil}`}>
              <p className="mb-2 text-sm font-semibold text-slate-800">{label}</p>
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
                {categories.map((c) => (
                  <label key={c.name} className="flex items-center gap-2 text-sm text-slate-600">
                    <Checkbox
                      data-testid={`req-${profil}-${c.name.replace(/\s/g, "-").toLowerCase()}`}
                      checked={(reqs[profil] || []).includes(c.name)}
                      onCheckedChange={() => toggle(profil, c.name)}
                    />
                    {c.name}
                  </label>
                ))}
              </div>
            </div>
          ))}
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>Annuler</Button>
          <Button data-testid="req-save-btn" onClick={save} disabled={busy} className="bg-slate-900 hover:bg-slate-800">
            {busy ? "Enregistrement…" : "Enregistrer"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
