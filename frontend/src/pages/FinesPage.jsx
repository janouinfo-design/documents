import { useEffect, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { useSearchParams } from "react-router-dom";
import { Download, FileSpreadsheet, FileText, Plus, ChevronLeft, ChevronRight } from "lucide-react";
import { getFines, getFinesStats, finesExportUrl, refreshFileToken } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import { Button } from "@/components/ui/button";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem, DropdownMenuLabel, DropdownMenuSeparator } from "@/components/ui/dropdown-menu";
import QueryErrorState from "@/components/QueryErrorState";
import FinesKpis from "@/components/fines/FinesKpis";
import FinesFilters from "@/components/fines/FinesFilters";
import FinesTable from "@/components/fines/FinesTable";
import FineDrawer from "@/components/fines/FineDrawer";
import ManualFineDialog from "@/components/documents/ManualFineDialog";
import { FINE_STATUSES, FINE_STATUS_META, DEADLINE_INACTIVE } from "@/lib/fines";
import { chfExact } from "@/lib/format";
import { cn } from "@/lib/utils";

const EMPTY = { q: "", vehicle_id: "", driver_id: "", type_infraction: "", date_from: "", date_to: "", montant_min: "", montant_max: "" };
const OPEN = FINE_STATUSES.filter((s) => !DEADLINE_INACTIVE.includes(s)).join(",");
const iso = (d) => d.toISOString().slice(0, 10);
const shift = (n) => { const d = new Date(); d.setDate(d.getDate() + n); return iso(d); };
// Vues rapides (KPI) → paramètres /api/fines (filtres serveur : statuts actifs + bornes d'échéance)
const quickParams = (view, urgent) => ({
  all: {}, open: { fine_status: OPEN }, late: { fine_status: OPEN, due_to: shift(-1) },
  soon: { fine_status: OPEN, due_from: shift(0), due_to: shift(urgent) },
  paid: { fine_status: "payee,refacturee" }, contestee: { fine_status: "contestee" }, annulee: { fine_status: "annulee" },
}[view] || {});
const PAGE = 50;

export default function FinesPage() {
  const { user } = useAuth();
  const isAdmin = can(user, "fines.write");
  const [params, setParams] = useSearchParams();
  const [view, setView] = useState(params.get("view") || "all");
  const [status, setStatus] = useState(params.get("fine_status") || "");
  const [f, setF] = useState({ ...EMPTY, vehicle_id: params.get("vehicle_id") || "" });
  const [offset, setOffset] = useState(0);
  const [openId, setOpenId] = useState(params.get("id") || null);
  const [createOpen, setCreateOpen] = useState(false);
  useEffect(() => { setOffset(0); }, [view, status, f]);

  const { data: stats } = useQuery({ queryKey: ["fines-stats"], queryFn: getFinesStats });
  const urgent = stats?.urgent_days ?? 30;
  const query = useMemo(() => {
    const base = status ? { fine_status: status } : quickParams(view, urgent);
    const clean = Object.fromEntries(Object.entries(f).filter(([, v]) => v !== "" && v !== null));
    return { ...base, ...clean, sort: "-created_at" };
  }, [view, status, f, urgent]);
  const { data, isLoading, isError, error } = useQuery({ queryKey: ["fines", "list", query, offset], queryFn: () => getFines({ ...query, limit: PAGE, offset }), keepPreviousData: true });
  const items = data?.items || [];
  const totals = data?.totals;
  const byStatus = stats?.counts?.by_status || {};

  const pickView = (v) => { setStatus(""); setView(view === v && v !== "all" ? "all" : v); setParams({}, { replace: true }); };
  const pickStatus = (s) => { setStatus(s === status ? "" : s); setView("all"); };
  const exportAs = async (fmt) => { await refreshFileToken().catch(() => null); window.open(finesExportUrl(fmt, query), "_blank", "noopener"); };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="fines-page">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Amendes</h2>
          <p className="mt-1 text-sm text-slate-500">10 statuts métier · conducteur · paiement (date métier) · pièces liées · historique. Les annulées restent visibles, hors coûts et échéances (D9).</p>
        </div>
        <div className="flex items-center gap-2">
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="outline" size="sm" className="gap-1.5" data-testid="fines-export-btn"><Download className="h-4 w-4" /> Exporter</Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuLabel className="text-xs font-normal text-slate-500">Périmètre = filtres actifs ({data?.total ?? "…"} amende{(data?.total || 0) > 1 ? "s" : ""})</DropdownMenuLabel>
              <DropdownMenuSeparator />
              <DropdownMenuItem onSelect={() => exportAs("csv")} data-testid="fines-export-csv"><FileText className="mr-2 h-4 w-4 text-slate-400" /> CSV (Excel)</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportAs("xlsx")} data-testid="fines-export-xlsx"><FileSpreadsheet className="mr-2 h-4 w-4 text-slate-400" /> XLSX</DropdownMenuItem>
              <DropdownMenuItem onSelect={() => exportAs("pdf")} data-testid="fines-export-pdf"><FileText className="mr-2 h-4 w-4 text-slate-400" /> PDF</DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
          {isAdmin && (
            <Button size="sm" onClick={() => setCreateOpen(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800" data-testid="fines-create-btn">
              <Plus className="h-4 w-4" /> Nouvelle amende
            </Button>
          )}
        </div>
      </div>

      <FinesKpis stats={stats} onPick={pickView} active={status ? null : view} />

      <div className="no-scrollbar flex gap-1 overflow-x-auto" data-testid="fines-status-tabs">
        <button type="button" onClick={() => pickView("all")} data-testid="fines-tab-all"
          className={cn("shrink-0 rounded-full border px-3 py-1 text-xs font-semibold transition-colors", !status && view === "all" ? "border-slate-900 bg-slate-900 text-white" : "border-slate-200 bg-white text-slate-600 hover:border-slate-400")}>
          Toutes · {stats?.counts?.total ?? "—"}
        </button>
        {FINE_STATUSES.map((s) => (
          <button key={s} type="button" onClick={() => pickStatus(s)} data-testid={`fines-tab-${s}`}
            className={cn("shrink-0 rounded-full border px-3 py-1 text-xs font-semibold transition-colors", status === s ? "border-slate-900 bg-slate-900 text-white" : `${FINE_STATUS_META[s].cls.replace("line-through decoration-slate-400", "")} hover:border-slate-400`)}>
            {FINE_STATUS_META[s].label} · {byStatus[s] ?? 0}
          </button>
        ))}
      </div>

      <FinesFilters f={f} setF={setF} onReset={() => setF(EMPTY)} />
      {isError && <QueryErrorState error={error} testId="fines-error" />}

      {totals && (
        <p className="text-xs text-slate-500" data-testid="fines-totals">
          {data.total} amende{data.total > 1 ? "s" : ""} · total compté <strong className="text-slate-800">{chfExact(totals.total_chf)}</strong>
          · ouvert {chfExact(totals.ouvert_chf)} · payé {chfExact(totals.paye_chf)}
          {totals.annule_chf > 0 && <> · annulé {chfExact(totals.annule_chf)} (exclu)</>}
          {totals.pending_fx_count > 0 && <> · {totals.pending_fx_count} conversion(s) en attente</>}
        </p>
      )}

      <FinesTable items={items} isLoading={isLoading} onOpen={setOpenId} />

      {data && data.total > PAGE && (
        <div className="flex items-center justify-end gap-2 text-xs text-slate-500" data-testid="fines-pagination">
          <span>{offset + 1}–{Math.min(offset + PAGE, data.total)} / {data.total}</span>
          <Button variant="outline" size="sm" className="h-7 w-7 p-0" disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - PAGE))} data-testid="fines-prev"><ChevronLeft className="h-4 w-4" /></Button>
          <Button variant="outline" size="sm" className="h-7 w-7 p-0" disabled={offset + PAGE >= data.total} onClick={() => setOffset(offset + PAGE)} data-testid="fines-next"><ChevronRight className="h-4 w-4" /></Button>
        </div>
      )}

      <FineDrawer fineId={openId} onOpenChange={(o) => !o && setOpenId(null)} />
      <ManualFineDialog open={createOpen} onOpenChange={setCreateOpen} onCreated={(r) => setOpenId(r.document_id)} />
    </div>
  );
}
