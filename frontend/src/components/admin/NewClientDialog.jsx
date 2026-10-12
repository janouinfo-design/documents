import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, Lock } from "lucide-react";
import { adminCreateTenant } from "@/lib/api";
import { MODULES } from "@/lib/rbac";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Checkbox } from "@/components/ui/checkbox";
import { cn } from "@/lib/utils";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

const slugify = (v) => (v || "").trim().toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);
const ALL_ON = Object.fromEntries(MODULES.map((m) => [m.key, true]));

// Modules à activer dès la création : tous cochés par défaut ; le socle Véhicules reste verrouillé (désactivable ensuite avec confirmation).
function ModulesPicker({ value, onChange }) {
  const count = MODULES.filter((m) => value[m.key]).length;
  const setAll = (v) => onChange({ ...Object.fromEntries(MODULES.map((m) => [m.key, v])), vehicles: true });
  return (
    <div data-testid="admin-new-client-modules">
      <div className="flex items-center justify-between">
        <Label>Modules activés <span className="font-normal text-slate-400" data-testid="admin-new-client-modules-count">· {count}/{MODULES.length}</span></Label>
        <div className="flex gap-3 text-xs">
          <button type="button" onClick={() => setAll(true)} data-testid="admin-new-client-modules-all" className="font-semibold text-slate-600 hover:text-slate-900">Tout</button>
          <button type="button" onClick={() => setAll(false)} data-testid="admin-new-client-modules-none" className="font-semibold text-slate-400 hover:text-slate-900">Socle seul</button>
        </div>
      </div>
      <div className="mt-2 grid grid-cols-2 gap-1.5">
        {MODULES.map((m) => {
          const on = !!value[m.key];
          return (
            <label key={m.key} htmlFor={`new-mod-${m.key}`}
              className={cn("flex cursor-pointer items-center gap-2 rounded-lg border px-2.5 py-2 text-sm transition-colors",
                on ? "border-slate-200 bg-white text-slate-800" : "border-dashed border-slate-300 bg-slate-50 text-slate-500",
                m.core && "cursor-default")}>
              <Checkbox id={`new-mod-${m.key}`} checked={on} disabled={m.core} data-testid={`admin-new-client-module-${m.key}`}
                onCheckedChange={(v) => onChange({ ...value, [m.key]: v === true })} />
              <span className="min-w-0 flex-1 truncate">{m.label}</span>
              {m.core && <Lock className="h-3 w-3 shrink-0 text-slate-400" title="Module socle — toujours activé à la création" />}
            </label>
          );
        })}
      </div>
      <p className="mt-1.5 text-xs text-slate-400">Modifiable à tout moment depuis la fiche client. Désactivé = accès bloqué, jamais de suppression de données.</p>
    </div>
  );
}

export default function NewClientDialog({ open, onOpenChange }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [modules, setModules] = useState(ALL_ON);
  const [saving, setSaving] = useState(false);

  const reset = () => { setName(""); setId(""); setIdTouched(false); setModules(ALL_ON); };

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const off = MODULES.filter((m) => !modules[m.key]).length;
      await adminCreateTenant({ name: name.trim(), id: (idTouched ? id : slugify(name)) || undefined, modules });
      toast.success(off ? `Client créé — ${MODULES.length - off}/${MODULES.length} modules activés` : "Client créé — tous les modules activés");
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
      reset();
      onOpenChange(false);
    } catch (err) {
      const d = err?.response?.data?.detail;
      toast.error((typeof d === "string" && d) || d?.message || "Création impossible");
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(v) => { onOpenChange(v); if (!v) reset(); }}>
      <DialogContent data-testid="admin-new-client-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>Nouveau client</DialogTitle>
          <DialogDescription>
            Crée un compte client isolé avec les modules choisis. Ajoutez ensuite ses utilisateurs et sa clé télématique.
          </DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          <div>
            <Label htmlFor="client-name">Nom du client</Label>
            <Input id="client-name" data-testid="admin-new-client-name-input" required value={name}
              onChange={(e) => setName(e.target.value)} placeholder="Transports Exemple SA" className="mt-1.5" />
          </div>
          <div>
            <Label htmlFor="client-id">Identifiant technique</Label>
            <Input id="client-id" data-testid="admin-new-client-id-input"
              value={idTouched ? id : slugify(name)}
              onChange={(e) => { setIdTouched(true); setId(slugify(e.target.value)); }}
              placeholder="transports-exemple" className="mt-1.5 font-mono text-sm" />
            <p className="mt-1 text-xs text-slate-400">Minuscules, chiffres et tirets — non modifiable ensuite.</p>
          </div>
          <ModulesPicker value={modules} onChange={setModules} />
          <DialogFooter>
            <Button type="submit" data-testid="admin-new-client-submit-btn" disabled={saving || !name.trim()}
              className="gap-2 bg-slate-900 hover:bg-slate-800">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Créer le client
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
