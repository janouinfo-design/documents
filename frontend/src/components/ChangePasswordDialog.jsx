import { useState } from "react";
import { toast } from "sonner";
import { KeyRound, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { authChangePassword } from "@/lib/api";

export default function ChangePasswordDialog({ open, onOpenChange }) {
  const [current, setCurrent] = useState("");
  const [next, setNext] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const reset = () => {
    setCurrent("");
    setNext("");
    setConfirm("");
    setError("");
  };

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    if (next.length < 8) {
      setError("Le nouveau mot de passe doit contenir au moins 8 caractères.");
      return;
    }
    if (next !== confirm) {
      setError("La confirmation ne correspond pas au nouveau mot de passe.");
      return;
    }
    setLoading(true);
    try {
      await authChangePassword(current, next);
      toast.success("Mot de passe modifié");
      reset();
      onOpenChange(false);
    } catch (err) {
      const d = err?.response?.data?.detail;
      setError(typeof d === "string" ? d : "Modification impossible — vérifiez le mot de passe actuel.");
    } finally {
      setLoading(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={(o) => { if (!o) reset(); onOpenChange(o); }}>
      <DialogContent data-testid="change-password-dialog" className="max-w-sm rounded-xl">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2 font-display text-lg">
            <KeyRound className="h-5 w-5 text-slate-500" /> Changer le mot de passe
          </DialogTitle>
          <DialogDescription>Minimum 8 caractères. La nouvelle valeur remplace définitivement l'ancienne.</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-3">
          <Input data-testid="pwd-current-input" type="password" required placeholder="Mot de passe actuel"
                 autoComplete="current-password" value={current} onChange={(e) => setCurrent(e.target.value)} />
          <Input data-testid="pwd-new-input" type="password" required placeholder="Nouveau mot de passe"
                 autoComplete="new-password" value={next} onChange={(e) => setNext(e.target.value)} />
          <Input data-testid="pwd-confirm-input" type="password" required placeholder="Confirmer le nouveau mot de passe"
                 autoComplete="new-password" value={confirm} onChange={(e) => setConfirm(e.target.value)} />
          {error && (
            <p data-testid="pwd-error" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">{error}</p>
          )}
          <div className="flex justify-end gap-2 pt-1">
            <Button type="button" variant="outline" data-testid="pwd-cancel-btn" onClick={() => onOpenChange(false)}>Annuler</Button>
            <Button type="submit" data-testid="pwd-submit-btn" disabled={loading} className="gap-2 bg-slate-900 hover:bg-slate-800">
              {loading && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
            </Button>
          </div>
        </form>
      </DialogContent>
    </Dialog>
  );
}
