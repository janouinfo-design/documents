import { useEffect, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { KeyRound, Link2, Loader2, UserPlus } from "lucide-react";
import { adminCreateUser, adminListUsers, adminUpdateUser } from "@/lib/api";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Switch } from "@/components/ui/switch";
import { Badge } from "@/components/ui/badge";
import {
  Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle,
} from "@/components/ui/dialog";
import { DriverLinkField, ROLE_OPTIONS, VehicleScopeField, roleShort, useTenantDrivers } from "@/components/admin/UserAccessFields";

const apiError = (err, fallback) => {
  const d = err?.response?.data?.detail;
  return (typeof d === "string" && d) || d?.message || fallback;
};

function RoleSelect({ value, onChange, testId }) {
  return (
    <select data-testid={testId} value={value} onChange={(e) => onChange(e.target.value)}
      className="mt-1.5 h-9 w-full rounded-md border border-slate-200 bg-white px-3 text-sm">
      {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
    </select>
  );
}

function UserDialog({ open, onOpenChange, title, description, onSubmit, withEmail, tenantId }) {
  const [email, setEmail] = useState("");
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("admin");
  const [driverId, setDriverId] = useState("");
  const [scope, setScope] = useState([]);
  const [saving, setSaving] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      const body = { email: email.trim().toLowerCase(), name: name.trim(), password, role };
      if (role === "driver" && driverId) body.driver_id = driverId;
      if (role === "manager") body.vehicle_scope = scope;
      await onSubmit(body);
      setEmail(""); setName(""); setPassword(""); setRole("admin"); setDriverId(""); setScope([]);
      onOpenChange(false);
    } catch (err) {
      toast.error(apiError(err, "Opération impossible"));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent data-testid="admin-user-dialog" className="max-h-[90vh] overflow-y-auto">
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
                <RoleSelect value={role} onChange={setRole} testId="admin-user-role-select" />
              </div>
              {role === "driver" && <DriverLinkField tenantId={tenantId} value={driverId} onChange={setDriverId} />}
              {role === "manager" && <VehicleScopeField tenantId={tenantId} value={scope} onChange={setScope} />}
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

// Liaison conducteur (driver) / périmètre véhicules (manager) d'un compte existant — superadmin seul, audité avant/après côté serveur.
function AccessDialog({ user, onOpenChange, tenantId, onSaved }) {
  const [driverId, setDriverId] = useState("");
  const [scope, setScope] = useState([]);
  const [saving, setSaving] = useState(false);
  useEffect(() => {
    setDriverId(user?.driver_id || "");
    setScope(user?.vehicle_scope || []);
  }, [user]);
  if (!user) return null;
  const save = async () => {
    setSaving(true);
    try {
      await adminUpdateUser(user.id, user.role === "driver" ? { driver_id: driverId || "" } : { vehicle_scope: scope });
      toast.success(user.role === "driver" ? (driverId ? "Conducteur lié au compte" : "Compte délié du conducteur") : `Périmètre enregistré — ${scope.length} véhicule(s)`);
      onSaved();
      onOpenChange(false);
    } catch (err) {
      toast.error(apiError(err, "Enregistrement impossible"));
    } finally {
      setSaving(false);
    }
  };
  return (
    <Dialog open={!!user} onOpenChange={onOpenChange}>
      <DialogContent data-testid="admin-user-access-dialog" className="max-h-[90vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>{user.role === "driver" ? "Liaison conducteur" : "Périmètre véhicules"}</DialogTitle>
          <DialogDescription>{user.email} · rôle {roleShort(user.role)}. Appliqué immédiatement aux sessions ouvertes (relecture serveur à chaque requête).</DialogDescription>
        </DialogHeader>
        {user.role === "driver"
          ? <DriverLinkField tenantId={tenantId} value={driverId} onChange={setDriverId} currentUserEmail={user.email} />
          : <VehicleScopeField tenantId={tenantId} value={scope} onChange={setScope} />}
        <DialogFooter>
          <Button onClick={save} disabled={saving} data-testid="admin-user-access-save-btn" className="gap-2 bg-slate-900 hover:bg-slate-800">
            {saving && <Loader2 className="h-4 w-4 animate-spin" />} Enregistrer
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function AccessBadge({ u, driversById }) {
  if (u.role === "manager") {
    const n = (u.vehicle_scope || []).length;
    return (
      <Badge data-testid={`admin-user-scope-${u.email}`} className={n ? "bg-indigo-50 text-indigo-700 hover:bg-indigo-50" : "bg-amber-50 text-amber-700 hover:bg-amber-50"}>
        {n ? `périmètre · ${n} véhicule${n > 1 ? "s" : ""}` : "périmètre vide · aucun véhicule"}
      </Badge>
    );
  }
  if (u.role === "driver") {
    const d = u.driver_id ? driversById[u.driver_id] : null;
    return (
      <Badge data-testid={`admin-user-driver-${u.email}`} className={u.driver_id ? "bg-emerald-50 text-emerald-700 hover:bg-emerald-50" : "bg-amber-50 text-amber-700 hover:bg-amber-50"}>
        {u.driver_id ? `conducteur · ${d?.display || u.driver_id}${d?.actif === false ? " (inactif)" : ""}` : "non lié · page d'attente"}
      </Badge>
    );
  }
  return null;
}

export default function ClientUsers({ tenantId }) {
  const qc = useQueryClient();
  const [createOpen, setCreateOpen] = useState(false);
  const [resetUser, setResetUser] = useState(null);
  const [accessUser, setAccessUser] = useState(null);
  const { data: users, isLoading } = useQuery({
    queryKey: ["admin-users", tenantId],
    queryFn: () => adminListUsers(tenantId),
  });
  const { data: drivers = [] } = useTenantDrivers(tenantId, !!users?.some((u) => u.role === "driver"));
  const driversById = Object.fromEntries(drivers.map((d) => [d.id, d]));
  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["admin-users", tenantId] });
    qc.invalidateQueries({ queryKey: ["admin-drivers", tenantId] });
    qc.invalidateQueries({ queryKey: ["admin-overview"] });
  };
  const toggleDisabled = async (u, active) => {
    try {
      await adminUpdateUser(u.id, { disabled: !active });
      toast.success(active ? "Utilisateur réactivé" : "Utilisateur désactivé — sessions révoquées");
      refresh();
    } catch (e) {
      toast.error(apiError(e, "Échec"));
    }
  };
  const changeRole = async (u, role) => {
    try {
      const r = await adminUpdateUser(u.id, { role });
      toast.success(`Rôle changé en ${roleShort(role)} — sessions révoquées`);
      refresh();
      if (role === "driver" || role === "manager") setAccessUser(r);
    } catch (err) {
      toast.error(apiError(err, "Échec du changement de rôle"));
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
                <p className="text-xs text-slate-400">{u.name || "—"} · rôle {roleShort(u.role)}</p>
              </div>
              <AccessBadge u={u} driversById={driversById} />
              {u.disabled && <Badge className="bg-red-100 text-red-700 hover:bg-red-100">Désactivé</Badge>}
              <select data-testid={`admin-user-role-change-${u.email}`} value={u.role} onChange={(e) => changeRole(u, e.target.value)}
                className="h-8 rounded-md border border-slate-200 bg-white px-2 text-xs">
                {ROLE_OPTIONS.map((o) => <option key={o.value} value={o.value}>{roleShort(o.value)}</option>)}
              </select>
              {(u.role === "driver" || u.role === "manager") && (
                <Button size="sm" variant="outline" data-testid={`admin-user-access-btn-${u.email}`}
                  onClick={() => setAccessUser(u)} className="gap-1.5 text-xs">
                  <Link2 className="h-3.5 w-3.5" /> {u.role === "driver" ? "Conducteur" : "Périmètre"}
                </Button>
              )}
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
      <UserDialog open={createOpen} onOpenChange={setCreateOpen} withEmail tenantId={tenantId}
        title="Nouvel utilisateur"
        description={`Compte de connexion pour le client ${tenantId}. Le mot de passe est défini ici, jamais envoyé par email.`}
        onSubmit={async (body) => {
          await adminCreateUser(tenantId, body);
          toast.success("Utilisateur créé");
          refresh();
        }} />
      <UserDialog open={!!resetUser} onOpenChange={(v) => !v && setResetUser(null)} withEmail={false} tenantId={tenantId}
        title="Réinitialiser le mot de passe"
        description={`${resetUser?.email || ""} — toutes ses sessions seront déconnectées.`}
        onSubmit={async ({ password }) => {
          await adminUpdateUser(resetUser.id, { password });
          toast.success("Mot de passe réinitialisé — sessions révoquées");
          refresh();
        }} />
      <AccessDialog user={accessUser} onOpenChange={(v) => !v && setAccessUser(null)} tenantId={tenantId} onSaved={refresh} />
    </div>
  );
}
