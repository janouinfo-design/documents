import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { getFieldMeta, getVehicleHistory } from "@/lib/api";
import { dateFr } from "@/lib/format";

const SOURCE_LABELS = {
  document_scan: "Scan de document",
  navixy: "Télématique",
  manual: "Manuel",
  can: "CAN",
  fuel_import: "Import carburant",
  external_vehicle_database: "Base externe",
  system_calculation: "Calcul système",
};

export default function ProvenanceSection({ vehicleId }) {
  const { data: meta = [] } = useQuery({
    queryKey: ["field-meta", vehicleId],
    queryFn: () => getFieldMeta(vehicleId),
    enabled: !!vehicleId,
  });
  const { data: history = [] } = useQuery({
    queryKey: ["vehicle-history", vehicleId],
    queryFn: () => getVehicleHistory(vehicleId),
    enabled: !!vehicleId,
  });

  if (!meta.length && !history.length) return null;

  return (
    <Accordion type="single" collapsible data-testid="provenance-section" className="rounded-xl border border-slate-200 bg-white px-4">
      <AccordionItem value="prov" className="border-0">
        <AccordionTrigger className="py-4 hover:no-underline">
          <span className="flex items-center gap-2 text-sm font-semibold text-slate-800">
            <History className="h-4 w-4 text-slate-400" /> Provenance & historique des données
            <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">{meta.length}</span>
            <span className="text-xs font-normal text-slate-400">Afficher les détails</span>
          </span>
        </AccordionTrigger>
        <AccordionContent className="pb-4">
          {meta.length > 0 && (
            <div className="mb-4 overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead>
                  <tr className="text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400">
                    <th className="pb-2 pr-3">Champ</th>
                    <th className="pb-2 pr-3">Source</th>
                    <th className="pb-2 pr-3">Confiance</th>
                    <th className="pb-2">Validé le</th>
                  </tr>
                </thead>
                <tbody>
                  {meta.map((m) => (
                    <tr key={m.field} className="border-t border-slate-100" data-testid={`meta-${m.field}`}>
                      <td className="py-2 pr-3 font-medium text-slate-800">{m.label || m.field}</td>
                      <td className="py-2 pr-3 text-slate-600">{SOURCE_LABELS[m.source] || m.source}</td>
                      <td className="py-2 pr-3 text-slate-600">{m.confidence != null ? `${Math.round(m.confidence * 100)} %` : "—"}</td>
                      <td className="py-2 text-slate-600">{dateFr(m.validated_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
          {history.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.1em] text-slate-400">Historique des modifications</p>
              <ul className="space-y-1.5">
                {history.map((h) => (
                  <li key={h.id} className="rounded-lg bg-slate-50 px-3 py-2 text-xs text-slate-600">
                    <span className="font-semibold text-slate-500">{dateFr(h.created_at)}</span> · {h.detail}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </AccordionContent>
      </AccordionItem>
    </Accordion>
  );
}
