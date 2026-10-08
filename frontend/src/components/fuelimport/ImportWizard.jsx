import { useEffect, useState } from "react";
import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { getFuelImport, getFuelImportRows } from "@/lib/api";
import UploadStep from "./UploadStep";
import MappingStep from "./MappingStep";
import PreviewStep from "./PreviewStep";

const STEPS = [["upload", "1. Fichier"], ["mapping", "2. Mapping"], ["preview", "3. Preview"], ["confirm", "4. Confirmation"]];

// Wizard d'import : upload → mapping → preview (workspace) → confirmation explicite. `jobId` null = nouvel import.
export default function ImportWizard({ jobId, isAdmin, onJobChange }) {
  const [job, setJob] = useState(null);
  const [rows, setRows] = useState([]);
  const [loading, setLoading] = useState(false);
  const [forceMapping, setForceMapping] = useState(false);
  const loadRows = async (id) => { const r = await getFuelImportRows(id || job.id); setRows(r.items); return r.items; };
  useEffect(() => {
    let alive = true;
    setForceMapping(false);
    if (!jobId) { setJob(null); setRows([]); return undefined; }
    setLoading(true);
    Promise.all([getFuelImport(jobId), getFuelImportRows(jobId)]).then(([j, r]) => { if (alive) { setJob(j); setRows(r.items); } }).finally(() => alive && setLoading(false));
    return () => { alive = false; };
  }, [jobId]);
  const step = !job ? "upload" : forceMapping || job.status === "mapping" ? "mapping" : job.status === "confirmed" ? "confirm" : "preview";
  const stepIdx = STEPS.findIndex(([k]) => k === step);
  return (
    <div className="space-y-4 rounded-xl border border-slate-200 bg-white p-5 shadow-sm" data-testid="fuel-import-wizard">
      <ol className="flex flex-wrap gap-2" data-testid="fuel-import-steps">
        {STEPS.map(([k, label], i) => (
          <li key={k} data-testid={`fuel-import-step-${k}`} data-active={step === k}
            className={cn("rounded-full px-3 py-1 text-xs font-bold", i < stepIdx ? "bg-emerald-100 text-emerald-800" : step === k ? "bg-slate-900 text-white" : "bg-slate-100 text-slate-400")}>{label}</li>
        ))}
      </ol>
      {loading && <div className="flex items-center gap-2 py-6 text-sm text-slate-500" data-testid="fuel-import-loading"><Loader2 className="h-4 w-4 animate-spin" /> Chargement de l'import…</div>}
      {!loading && step === "upload" && (isAdmin
        ? <UploadStep onJob={(j) => { setJob(j); setRows([]); onJobChange(j.id); }} />
        : <p className="rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm text-slate-500" data-testid="fuel-import-readonly-hint">Consultation seule : sélectionnez un import dans la liste pour voir son détail.</p>)}
      {!loading && step === "mapping" && job && (
        <MappingStep job={job} onBack={() => (forceMapping ? setForceMapping(false) : onJobChange(null))}
          onPreview={(res) => { setForceMapping(false); setJob({ ...job, ...res, rows: undefined }); setRows(res.rows); }} />
      )}
      {!loading && (step === "preview" || step === "confirm") && job && (
        <PreviewStep job={job} rows={rows} isAdmin={isAdmin} onJob={setJob} onBack={job.status !== "confirmed" && isAdmin ? () => setForceMapping(true) : null}
          onRows={async (next) => { if (Array.isArray(next)) setRows(next); else await loadRows(); }} />
      )}
    </div>
  );
}
