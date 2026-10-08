import { useState } from "react";
import { toast } from "sonner";
import { Download, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { downloadFuelExport } from "@/lib/api";
import { apiError } from "@/lib/fuelStatements";

// Boutons d'export (CSV / XLSX / PDF) — téléchargement authentifié, audité côté serveur (SHA-256) ; autorisé en lecture seule
export default function ExportButtons({ path, params = {}, formats = ["csv", "xlsx", "pdf"], testIdPrefix, size = "sm", disabled }) {
  const [busy, setBusy] = useState(null);
  const run = async (format) => {
    setBusy(format);
    try {
      const r = await downloadFuelExport(path, { ...params, format });
      toast.success(`Téléchargement réussi — ${r.filename}`);
    } catch (e) {
      toast.error(apiError(e, "Export impossible"));
    } finally { setBusy(null); }
  };
  return (
    <div className="flex flex-wrap gap-1.5" data-testid={`${testIdPrefix}-exports`}>
      {formats.map((f) => (
        <Button key={f} size={size} variant="outline" onClick={() => run(f)} disabled={disabled || !!busy} className="gap-1.5" data-testid={`${testIdPrefix}-export-${f}`}>
          {busy === f ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Download className="h-3.5 w-3.5" />} Export {f.toUpperCase()}
        </Button>
      ))}
    </div>
  );
}
