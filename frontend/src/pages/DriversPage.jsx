import { useMemo, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Search, UserPlus, Pencil, Archive, ArchiveRestore, History, Users } from "lucide-react";
import { getDrivers, getDriver, archiveDriver, restoreDriver } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import QueryErrorState from "@/components/QueryErrorState";
import DriverDialog from "@/components/drivers/DriverDialog";
import AssignmentHistory from "@/components/drivers/AssignmentHistory";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const STATES = [["active", "Actifs"], ["inactive", "Désactivés"], ["archived", "Archivés"], ["all", "Tous"]];

function HistoryDialog({ driverId, onOpenChange, readOnly }) {
  const { data } = useQuery({ queryKey: ["drivers", "detail", driverId], queryFn: () => getDriver(driverId), enabled: !!driverId });
  return (
    <Dialog open={!!driverId} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-lg" data-testid="driver-history-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">{data?.display || "Conducteur"} — historique</DialogTitle>
          <DialogDescription>Affectations véhicule datées (valid_from / valid_to), les plus récentes en premier.</DialogDescription>
        </DialogHeader>
        <AssignmentHistory rows={data?.assignments || []} readOnly={readOnly} showVehicle showDriver={false} />
      </DialogContent>
    </Dialog>
  );
}

export default function DriversPage() {
  const { user } = useAuth();
  const qc = useQueryClient();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [q, setQ] = useState("");
  const [state, setState] = useState("active");
  const [edit, setEdit] = useState(null);
  const [createOpen, setCreateOpen] = useState(false);
  const [historyId, setHistoryId] = useState(null);

  const { data: drivers = [], isLoading, isError, error } = useQuery({ queryKey: ["drivers", "list"], queryFn: () => getDrivers({ include_archived: "1" }) });
  const rows = useMemo(() => {
    const term = q.trim().toLowerCase();
    return drivers.filter((d) => (state === "all" || (state === "archived" ? d.is_deleted : !d.is_deleted && (state === "active" ? d.actif !== false : d.actif === false)))
      && (!term || [d.nom, d.prenom, d.matricule_interne, d.email, d.groupe].join(" ").toLowerCase().includes(term)));
  }, [drivers, q, state]);

  const act = async (fn, okMsg) => {
    try { await fn(); toast.success(okMsg); qc.invalidateQueries({ queryKey: ["drivers"] }); }
    catch (e) { const d = e?.response?.data?.detail; toast.error((typeof d === "string" && d) || d?.message || "Action impossible"); }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="drivers-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Conducteurs</h2>
          <p className="mt-1 text-sm text-slate-500">Référentiel du tenant — identifiant stable, nom/prénom = affichage. Affectations datées aux véhicules, jamais de rapprochement automatique par nom.</p>
        </div>
        {isAdmin && (
          <Button data-testid="driver-create-btn" size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800">
            <UserPlus className="h-4 w-4" /> Nouveau conducteur
          </Button>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-3">
        <div className="relative sm:col-span-2">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input data-testid="drivers-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nom, prénom, matricule, email, groupe…" className="pl-9" />
        </div>
        <Select value={state} onValueChange={setState}>
          <SelectTrigger data-testid="drivers-filter-state"><SelectValue /></SelectTrigger>
          <SelectContent>{STATES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}</SelectContent>
        </Select>
      </div>

      {isError && <QueryErrorState error={error} testId="drivers-error" />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="drivers-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Conducteur</TableHead>
              <TableHead>Matricule · groupe</TableHead>
              <TableHead>Contact</TableHead>
              <TableHead>Affectation(s) en cours</TableHead>
              <TableHead>État</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && rows.length === 0 && (
              <TableRow><TableCell colSpan={6}>
                <div className="flex flex-col items-center gap-2 py-10 text-center" data-testid="drivers-empty">
                  <Users className="h-8 w-8 text-slate-300" />
                  <p className="text-sm font-medium text-slate-600">Aucun conducteur dans cette vue</p>
                </div>
              </TableCell></TableRow>
            )}
            {rows.map((d) => (
              <TableRow key={d.id} data-testid={`driver-row-${d.id}`} className="hover:bg-slate-50">
                <TableCell>
                  <p className="text-sm font-semibold text-slate-800" data-testid={`driver-name-${d.id}`}>{[d.prenom, d.nom].filter(Boolean).join(" ")}</p>
                  {d.source === "legacy_import" && <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">import</span>}
                </TableCell>
                <TableCell className="text-sm text-slate-600">{d.matricule_interne || "—"}{d.groupe ? ` · ${d.groupe}` : ""}</TableCell>
                <TableCell className="text-xs text-slate-500">{d.email || "—"}{d.telephone ? ` · ${d.telephone}` : ""}</TableCell>
                <TableCell>
                  {(d.affectations || []).length === 0 ? <span className="text-xs text-slate-400">—</span> : d.affectations.map((a) => (
                    <button key={a.id} onClick={() => openVehicle(a.vehicle_id, "conducteur")} data-testid={`driver-assign-${d.id}-${a.vehicle_id}`}
                      className="mr-1 rounded-full border border-slate-200 bg-white px-2 py-0.5 text-xs font-semibold text-slate-700 hover:bg-slate-100">
                      {a.plaque || a.vehicle_id}{a.principal === false ? " (sec.)" : ""}
                    </button>
                  ))}
                </TableCell>
                <TableCell>
                  <span data-testid={`driver-state-${d.id}`} className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${d.is_deleted ? "bg-slate-100 text-slate-500" : d.actif !== false ? "bg-emerald-50 text-emerald-700" : "bg-amber-50 text-amber-700"}`}>
                    {d.is_deleted ? "Archivé" : d.actif !== false ? "Actif" : "Désactivé"}
                  </span>
                </TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <button onClick={() => setHistoryId(d.id)} data-testid={`driver-history-${d.id}`} aria-label="Historique" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><History className="h-4 w-4" /></button>
                    {isAdmin && !d.is_deleted && (
                      <>
                        <button onClick={() => setEdit(d)} data-testid={`driver-edit-${d.id}`} aria-label="Modifier" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Pencil className="h-4 w-4" /></button>
                        <button onClick={() => act(() => archiveDriver(d.id), `${d.nom} archivé`)} data-testid={`driver-archive-${d.id}`} aria-label="Archiver" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600"><Archive className="h-4 w-4" /></button>
                      </>
                    )}
                    {isAdmin && d.is_deleted && (
                      <button onClick={() => act(() => restoreDriver(d.id), `${d.nom} restauré`)} data-testid={`driver-restore-${d.id}`} aria-label="Restaurer" className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><ArchiveRestore className="h-4 w-4" /></button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <DriverDialog open={createOpen} onOpenChange={setCreateOpen} />
      <DriverDialog open={!!edit} onOpenChange={(o) => !o && setEdit(null)} driver={edit} />
      <HistoryDialog driverId={historyId} onOpenChange={(o) => !o && setHistoryId(null)} readOnly={!isAdmin} />
    </div>
  );
}
