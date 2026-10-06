import { useState } from "react";
import { toast } from "sonner";
import { Loader2, Search, ListPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { parseLegacyVehicles } from "@/lib/legacyParse";
import { legacyVehicleCandidates, legacyVehicleStage } from "@/lib/api";

const STATUS_LABEL = {
  strong_candidate: "candidat fort (VIN / id télématique)",
  candidate_warning: "candidat avec avertissement (tracker évolutif)",
  manual_review: "revue manuelle (plaque)",
  ambiguous: "ambigu",
  not_found: "aucun candidat",
};

const PLACEHOLDER = `[{"legacy_vehicle_id":"<uuid Journal>","plate":"VD 123456","vin":"","navixy_tracker_id":123,"model":"…"}]
ou CSV : legacy_vehicle_id;plate;vin;navixy_tracker_id;model`;

export default function LegacyInputBox({ canWrite, onStaged }) {
  const [text, setText] = useState("");
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(null);

  const run = async (mode) => {
    const { vehicles, errors } = parseLegacyVehicles(text);
    if (errors.length) toast.warning(errors.slice(0, 3).join(" · "));
    if (!vehicles.length) return;
    setBusy(mode);
    try {
      if (mode === "preview") {
        const r = await legacyVehicleCandidates({ vehicles });
        setPreview(r);
      } else {
        const r = await legacyVehicleStage({ vehicles });
        toast.success(`${r.created} mis en file · ${r.updated} actualisés · ${r.skipped} ignorés (déjà traités)`);
        setPreview(null);
        setText("");
        onStaged?.();
      }
    } catch (e) {
      toast.error(String(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Échec de l'analyse"));
    } finally {
      setBusy(null);
    }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="legacy-input-section">
      <h2 className="text-base font-semibold text-slate-900 md:text-lg">Véhicules Journal à rapprocher</h2>
      <p className="mt-1 text-sm text-slate-500">
        Collez l'export (JSON ou CSV). L'analyse est en <strong>lecture seule</strong> : VIN / identifiant télématique = candidat fort,
        tracker = avertissement (affectation évolutive), plaque = revue manuelle uniquement. Rien n'est migré.
      </p>
      <Textarea data-testid="legacy-input" value={text} onChange={(e) => setText(e.target.value)}
        placeholder={PLACEHOLDER} rows={6} className="mt-3 font-mono text-xs" disabled={!canWrite} />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button data-testid="legacy-analyze-btn" variant="outline" disabled={!canWrite || !!busy} onClick={() => run("preview")} className="gap-2">
          {busy === "preview" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Search className="h-4 w-4" />} Analyser (lecture seule)
        </Button>
        <Button data-testid="legacy-stage-btn" disabled={!canWrite || !!busy} onClick={() => run("stage")} className="gap-2 bg-slate-900 hover:bg-slate-800">
          {busy === "stage" ? <Loader2 className="h-4 w-4 animate-spin" /> : <ListPlus className="h-4 w-4" />} Mettre en file d'attente
        </Button>
        {!canWrite && <span className="text-xs font-semibold text-amber-600" data-testid="legacy-readonly-note">Lecture seule — confirmation réservée aux administrateurs</span>}
      </div>
      {preview && (
        <div className="mt-4 rounded-xl bg-slate-50 p-4 text-sm" data-testid="legacy-preview-summary">
          <p className="font-semibold text-slate-800">{preview.items.length} véhicule(s) analysé(s) · 0 écriture</p>
          <ul className="mt-2 grid gap-1 sm:grid-cols-2">
            {Object.entries(preview.summary).map(([k, n]) => (
              <li key={k} className="flex justify-between gap-3 text-slate-600" data-testid={`legacy-preview-${k}`}>
                <span>{STATUS_LABEL[k] || k}</span><span className="font-semibold tabular-nums">{n}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </section>
  );
}
