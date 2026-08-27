import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Search, FolderCog, ListChecks, Pencil, Download, FolderOpen, Loader2 } from "lucide-react";
import { getAllDocuments, getDocCategories, getDeadlineSettings, getVehicles, fileUrl } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import QueryErrorState from "@/components/QueryErrorState";
import { DocStatutBadge, DOC_STATUT_META } from "@/components/documents/DocStatutBadge";
import DocumentEditDialog from "@/components/documents/DocumentEditDialog";
import DocCategoriesDialog from "@/components/documents/DocCategoriesDialog";
import DocRequirementsDialog from "@/components/documents/DocRequirementsDialog";
import { useAuth } from "@/context/AuthContext";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const ALL = "__all__";

export default function DocumentsPage() {
  const { user } = useAuth();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const [searchParams] = useSearchParams();
  const [q, setQ] = useState("");
  const [qDebounced, setQDebounced] = useState("");
  const [vehicle, setVehicle] = useState(searchParams.get("vehicle_id") || ALL);
  const [folder, setFolder] = useState(searchParams.get("folder") || ALL);
  const [statut, setStatut] = useState(searchParams.get("statut") || ALL);
  const [echeance, setEcheance] = useState(searchParams.get("echeance") || ALL);
  const [editDoc, setEditDoc] = useState(null);
  const [catsOpen, setCatsOpen] = useState(false);
  const [reqsOpen, setReqsOpen] = useState(false);

  useEffect(() => {
    const t = setTimeout(() => setQDebounced(q), 300);
    return () => clearTimeout(t);
  }, [q]);

  const params = useMemo(() => ({
    ...(qDebounced.trim() && { q: qDebounced.trim() }),
    ...(vehicle !== ALL && { vehicle_id: vehicle }),
    ...(folder !== ALL && { folder }),
    ...(statut !== ALL && { statut }),
    ...(echeance !== ALL && { echeance }),
  }), [qDebounced, vehicle, folder, statut, echeance]);

  const { data: docs = [], isLoading, isError, error } = useQuery({
    queryKey: ["all-documents", params],
    queryFn: () => getAllDocuments(params),
  });
  const { data: categories = [] } = useQuery({ queryKey: ["doc-categories"], queryFn: getDocCategories });
  const { data: vehicles = [] } = useQuery({ queryKey: ["vehicles"], queryFn: getVehicles });
  const { data: dlSettings } = useQuery({ queryKey: ["deadline-settings"], queryFn: getDeadlineSettings });

  const uDays = dlSettings?.urgent_days ?? 30;
  const wDays = dlSettings?.warning_days ?? 90;
  const ECHEANCES = [
    [ALL, "Toutes échéances"],
    ["expired", "Expirés"],
    ["30", `≤ ${uDays} jours`],
    ["90", `${uDays + 1}–${wDays} jours`],
  ];

  return (
    <div className="space-y-6 animate-fade-in" data-testid="documents-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Documents</h2>
          <p className="mt-1 text-sm text-slate-500">
            Bibliothèque documentaire de la flotte — {docs.length} document(s) affiché(s)
          </p>
        </div>
        {isAdmin && (
          <div className="flex gap-2">
            <Button data-testid="manage-categories-btn" variant="outline" size="sm" onClick={() => setCatsOpen(true)} className="gap-1.5">
              <FolderCog className="h-4 w-4" /> Catégories
            </Button>
            <Button data-testid="manage-requirements-btn" variant="outline" size="sm" onClick={() => setReqsOpen(true)} className="gap-1.5">
              <ListChecks className="h-4 w-4" /> Documents requis
            </Button>
          </div>
        )}
      </div>

      <div className="grid grid-cols-1 gap-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm sm:grid-cols-2 lg:grid-cols-5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input data-testid="docs-filter-search" value={q} onChange={(e) => setQ(e.target.value)} placeholder="Nom, fournisseur, n°, tag…" className="pl-9" />
        </div>
        <Select value={vehicle} onValueChange={setVehicle}>
          <SelectTrigger data-testid="docs-filter-vehicle"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous les véhicules</SelectItem>
            {vehicles.map((v) => <SelectItem key={v.id} value={v.id}>{v.plaque || v.id}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={folder} onValueChange={setFolder}>
          <SelectTrigger data-testid="docs-filter-category"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Toutes catégories</SelectItem>
            {categories.map((c) => <SelectItem key={c.name} value={c.name}>{c.name}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={statut} onValueChange={setStatut}>
          <SelectTrigger data-testid="docs-filter-statut"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL}>Tous statuts</SelectItem>
            {Object.entries(DOC_STATUT_META).map(([k, m]) => <SelectItem key={k} value={k}>{m.label}</SelectItem>)}
          </SelectContent>
        </Select>
        <Select value={echeance} onValueChange={setEcheance}>
          <SelectTrigger data-testid="docs-filter-echeance"><SelectValue /></SelectTrigger>
          <SelectContent>
            {ECHEANCES.map(([v, l]) => <SelectItem key={v} value={v}>{l}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>

      {isError && <QueryErrorState error={error} testId="documents-error" />}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Document</TableHead>
              <TableHead>Véhicule</TableHead>
              <TableHead>Catégorie</TableHead>
              <TableHead>Fournisseur</TableHead>
              <TableHead>Expiration</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead className="text-right">Actions</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {isLoading && (
              <TableRow>
                <TableCell colSpan={7}>
                  <div className="flex items-center justify-center gap-2 py-10 text-sm text-slate-400" data-testid="documents-loading">
                    <Loader2 className="h-4 w-4 animate-spin" /> Chargement des documents…
                  </div>
                </TableCell>
              </TableRow>
            )}
            {!isLoading && docs.length === 0 && (
              <TableRow>
                <TableCell colSpan={7}>
                  <div className="flex flex-col items-center gap-2 py-10 text-center">
                    <FolderOpen className="h-8 w-8 text-slate-300" />
                    <p className="text-sm font-medium text-slate-600">Aucun document ne correspond aux filtres</p>
                  </div>
                </TableCell>
              </TableRow>
            )}
            {docs.map((d) => (
              <TableRow key={d.id} data-testid={`doc-row-${d.id}`} className="hover:bg-slate-50">
                <TableCell>
                  <p className="max-w-[220px] truncate text-sm font-semibold text-slate-800">{d.label || d.original_filename}</p>
                  <p className="text-xs text-slate-400">
                    {d.numero ? `N° ${d.numero}` : d.sub_category || ""}
                    {(d.tags || []).length > 0 && ` · ${d.tags.join(", ")}`}
                  </p>
                </TableCell>
                <TableCell>
                  <button onClick={() => openVehicle(d.vehicle_id, "documents")} className="text-sm font-medium text-slate-700 underline-offset-2 hover:underline" data-testid={`doc-open-vehicle-${d.id}`}>
                    {d.plaque || "—"}
                  </button>
                  <p className="text-xs text-slate-400">{d.vehicule_label}</p>
                </TableCell>
                <TableCell className="text-sm text-slate-600">{d.folder}</TableCell>
                <TableCell className="text-sm text-slate-600">{d.fournisseur || "—"}</TableCell>
                <TableCell className={cn("text-sm", d.statut === "EXPIRE" ? "font-semibold text-red-600" : "text-slate-600")}>
                  {d.date_expiration ? dateFr(d.date_expiration) : "—"}
                </TableCell>
                <TableCell><DocStatutBadge statut={d.statut} /></TableCell>
                <TableCell>
                  <div className="flex justify-end gap-1">
                    <button
                      onClick={() => window.open(fileUrl(d.storage_path, { download: true, filename: d.original_filename }), "_blank", "noopener")}
                      data-testid={`doc-page-download-${d.id}`}
                      className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Télécharger">
                      <Download className="h-4 w-4" />
                    </button>
                    {isAdmin && (
                      <button onClick={() => setEditDoc(d)} data-testid={`doc-page-edit-${d.id}`}
                        className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Modifier la fiche">
                        <Pencil className="h-4 w-4" />
                      </button>
                    )}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>

      <DocumentEditDialog doc={editDoc} categories={categories} open={!!editDoc} onOpenChange={(o) => !o && setEditDoc(null)} />
      <DocCategoriesDialog categories={categories} open={catsOpen} onOpenChange={setCatsOpen} />
      <DocRequirementsDialog categories={categories} open={reqsOpen} onOpenChange={setReqsOpen} />
    </div>
  );
}
