import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2 } from "lucide-react";
import { adminCreateTenant } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

const slugify = (v) => (v || "").trim().toLowerCase().replace(/[^a-z0-9-]+/g, "-").replace(/^-+|-+$/g, "").slice(0, 40);

export default function NewClientDialog({ open, onOpenChange }) {
  const qc = useQueryClient();
  const [name, setName] = useState("");
  const [id, setId] = useState("");
  const [idTouched, setIdTouched] = useState(false);
  const [saving, setSaving] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await adminCreateTenant({ name: name.trim(), id: (idTouched ? id : slugify(name)) || undefined });
      toast.success("Client créé");
      qc.invalidateQueries({ queryKey: ["admin-overview"] });
      setName(""); setId(""); setIdTouched(false);
      onOpenChange(false);
    } catch (err) {
      toast.error(String(err?.response?.data?.detail || "Création impossible"));
    } finally {
      setSaving(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="admin-new-client-dialog">
        <DialogHeader>
          <DialogTitle>Nouveau client</DialogTitle>
          <DialogDescription>
            Crée un compte client isolé. Ajoutez ensuite ses utilisateurs et sa clé télématique.
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
