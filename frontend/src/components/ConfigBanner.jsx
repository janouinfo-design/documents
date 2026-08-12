import { useQuery } from "@tanstack/react-query";
import { AlertTriangle } from "lucide-react";
import { getConfigStatus } from "@/lib/api";

export default function ConfigBanner() {
  const { data } = useQuery({ queryKey: ["config-status"], queryFn: getConfigStatus, staleTime: 60000, retry: 1 });
  if (!data || (data.scan_configured && data.technical_data_configured)) return null;
  const missing = [];
  if (!data.scan_configured) missing.push("Scan de documents (OCR) : clé EMERGENT_LLM_KEY manquante");
  if (!data.technical_data_configured) missing.push("Base technique SwissCarInfo : clé SWISSCARINFO_API_KEY manquante");
  return (
    <div data-testid="config-banner" className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3">
      <p className="flex items-center gap-2 text-sm font-semibold text-amber-900">
        <AlertTriangle className="h-4 w-4 shrink-0" /> Configuration serveur incomplète
      </p>
      <ul className="mt-1.5 list-inside list-disc space-y-0.5 text-sm text-amber-800">
        {missing.map((m) => (
          <li key={m} data-testid="config-banner-item">{m}</li>
        ))}
      </ul>
      <p className="mt-1.5 text-xs text-amber-700">
        Renseignez ces clés dans le fichier .env du serveur (deploy/.env sur le VPS) puis redémarrez le backend.
      </p>
    </div>
  );
}
