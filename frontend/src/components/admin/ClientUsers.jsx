import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, Loader2, UserPlus } from "lucide-react";
import { adminCreateUser, adminListUsers, adminUpdateUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";

function UserDialog({ open, onOpenChange, title, description, onSubmit, withEmail }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("admin");
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await onSubmit({ email: email.trim().toLowerCase(), name: name.trim(), password, role });
      setEmail(""); setName(""); setPassword(""); setRole("admin");
      onOpenChange(false);
    } catch (err) {
      toast.error(String(err?.response?.data?.detail || "Opération impossible"));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="admin-user-dialog">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>
        <form onSubmit={submit} className="space-y-4">
          {withEmail && (
            <>
              <div>
                <Label>Email</Label>
                <Input data-testid="admin-user-email-input" type="email" required value={email}
                  onChange={(e) => setEmail(e.target.value)} placeholder="admin@client.ch" className="mt-1.5" />
              </div>
              <div>
                <Label>Nom (optionnel)</Label>
                <Input data-testid="admin-user-name-input" value={name}
                  onChange={(e) => setName(e.target.value)} placeholder="Prénom Nom" className="mt-1.5" />
              </div>
              <div>
                <Label>Rôle</Label>
                <select data-testid="admin-user-role-select" value={role}
                  onChange={(e) => setRole(e.target.value)}
                  className="mt-1.5 h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm">
                  <option value="admin">Admin (lecture + écriture)</option>
                  <option value="read_only">Lecture seule</option>
                </select>
              </div>
            </>
          )}
          <div>
            <Label>Mot de passe (8 caractères min.)</Label>
            <Input data-testid="admin-user-password-input" type="password" required minLength={8} value={password}
              onChange={(e) => setPassword(e.target.value)} placeholder="••••••••" className="mt-1.5" />
          </div>
          <DialogFooter>
            <Button type="submit" data-testid="admin-user-submit-btn" disabled={saving}
              className="gap-2 bg-slate-900 hover:bg-slate-800">
              {saving && <Loader2 className="h-4 w-4 animate-spin" />} Valider
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}

export default function ClientUsers({ tenantId }) {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users", tenantId],
    queryFn: () => adminListUsers(tenantId),
  });
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin-users", tenantId] });
    qc.invalidateQueries({ queryKey: ["admin-overview"] });
  };
  const toggleDisabled = async (u, active) => {
    try {
      await adminUpdateUser(u.id, { disabled: !active });
      toast.success(active ? "Utilisateur réactivé" : "Utilisateur désactivé — sessions révoquées");
      refresh();
    } catch (e) {
      toast.error(String(e?.response?.data?.detail || "Échec"));
    }
  };
  return (
    <div data-testid={`admin-users-section-${tenantId}`}>
      <div className="mb-3 flex items-center justify-between">
        <h3 className="text-sm font-semibold uppercase tracking-wide text-slate-400">Utilisateurs</h3>
        <Button size="sm" variant="outline" data-testid={`admin-add-user-btn-${tenantId}`}
          onClick={() => setCreateOpen(true)} className="gap-2">
          <UserPlus className="h-4 w-4" /> Ajouter
        </Button>
      </div>
      {isLoading ? (
        <Loader2 className="h-5 w-5 animate-spin text-slate-400" />
      ) : !users?.length ? (
        <p className="text-sm text-slate-400" data-testid={`admin-users-empty-${tenantId}`}>
          Aucun utilisateur — ce client ne peut pas encore se connecter.
        </p>
      ) : (
        <div className="divide-y divide-slate-100 rounded-xl border border-slate-200">
          {users.map((u) => (
            <div key={u.id} className="flex flex-wrap items-center gap-3 px-4 py-3" data-testid={`admin-user-row-${u.email}`}>
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-slate-900">{u.email}</p>
                <p className="text-xs text-slate-400">{u.name || "—"} · rôle {u.role}</p>
              </div>
              {u.disabled && <Badge className="bg-red-100 text-red-700 hover:bg-red-100">Désactivé</Badge>}
              <select data-testid={`admin-user-role-change-${u.email}`} value={u.role}
                onChange={async (e) => {
                  try {
                    await adminUpdateUser(u.id, { role: e.target.value });
                    toast.success(`Rôle changé en ${e.target.value} — sessions révoquées`);
                    refresh();
                  } catch (err) {
                    toast.error(String(err?.response?.data?.detail || "Échec du changement de rôle"));
                  }
                }}
                className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs">
                <option value="admin">admin</option>
                <option value="read_only">lecture seule</option>
              </select>
              <Button size="sm" variant="ghost" data-testid={`admin-user-reset-btn-${u.email}`}
                onClick={() => setResetUser(u)} className="gap-1.5 text-slate-500">
                <KeyRound className="h-3.5 w-3.5" /> Réinitialiser
              </Button>
              <Switch checked={!u.disabled} data-testid={`admin-user-active-switch-${u.email}`}
                onCheckedChange={(v) => toggleDisabled(u, v)} />
            </div>
          ))}
        </div>
      )}
      <UserDialog open={createOpen} onOpenChange={setCreateOpen} withEmail
        title="Nouvel utilisateur"
        description={`Compte de connexion pour le client ${tenantId}. Le mot de passe est défini ici, jamais envoyé par email.`}
        onSubmit={async ({ email, name, password, role }) => {
          await adminCreateUser(tenantId, { email, name, password, role });
          toast.success("Utilisateur créé");
          refresh();
        }} />
      <UserDialog open={!!resetUser} onOpenChange={(v) => !v && setResetUser(null)} withEmail={false}
        title={`Réinitialiser le mot de passe`}
        description={`${resetUser?.email || ""} — toutes ses sessions seront déconnectées.`}
        onSubmit={async ({ password }) => {
          await adminUpdateUser(resetUser.id, { password });
          toast.success("Mot de passe réinitialisé — sessions révoquées");
          refresh();
        }} />
    </div>
  );
}
