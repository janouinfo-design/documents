import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Download, Gavel, Wallet } from "lucide-react";
import { fileUrl, getMyFines } from "@/lib/api";
import { chfExact, dateFr } from "@/lib/format";
import KpiCard from "@/components/KpiCard";
import DriverShell from "@/components/me/DriverShell";
import FineStatusBadge from "@/components/fines/FineStatusBadge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { cn } from "@/lib/utils";

function Deadline({ f }) {
  if (!f.date_expiration) return <span className="text-xs text-slate-400">—</span>;
  const d = f.days_remaining;
  const late = d != null && d < 0;
  return (
    <div className="text-sm">
      <p className={cn("font-medium", late ? "text-red-600" : "text-slate-700")}>{dateFr(f.date_expiration)}</p>
      {d != null && f.deadline_active && (
        <p className={cn("text-[11px]", late ? "text-red-600" : d <= 7 ? "text-amber-600" : "text-slate-400")} data-testid={`me-fine-days-${f.id}`}>
          {late ? `En retard de ${Math.abs(d)} j` : d === 0 ? "Aujourd'hui" : `Dans ${d} j`}
        </p>
      )}
    </div>
  );
}

// Mes amendes = documents amende dont driver_id = mon conducteur ; projection serveur sans notes internes / dossier / priorité.
export default function MyFinesPage() {
  const { data, isLoading, error } = useQuery({ queryKey: ["me", "fines"], queryFn: getMyFines, retry: false });
  const items = data?.items || [];
  const t = data?.totals || {};
  return (
    <DriverShell title="Mes amendes" icon={Gavel} testId="me-fines-page" dataError={error} isLoading={isLoading}
      subtitle="Amendes rattachées à votre nom par votre entreprise. Les informations internes de gestion ne sont pas affichées.">
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
        <KpiCard testId="me-fines-kpi-open" label="À traiter" value={t.ouvertes ?? 0} icon={Gavel} accent="amber" sub="délai de paiement actif" />
        <KpiCard testId="me-fines-kpi-late" label="En retard" value={t.en_retard ?? 0} icon={AlertTriangle} accent={t.en_retard ? "red" : "emerald"} sub="délai dépassé" />
        <KpiCard testId="me-fines-kpi-amount" label="Montant ouvert" value={chfExact(t.montant_ouvert_chf || 0)} icon={Wallet} accent="slate" sub="amendes à traiter, en CHF" />
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="me-fines-table">
          <TableHeader>
            <TableRow>
              <TableHead>Infraction</TableHead><TableHead>Véhicule</TableHead><TableHead>Autorité · n°</TableHead><TableHead>Type · lieu</TableHead>
              <TableHead className="text-right">Montant</TableHead><TableHead>Délai</TableHead><TableHead>Statut</TableHead><TableHead className="text-right">Document</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 && (
              <TableRow><TableCell colSpan={8} className="py-12 text-center text-sm text-slate-400" data-testid="me-fines-empty">Aucune amende rattachée à votre nom.</TableCell></TableRow>
            )}
            {items.map((f) => (
              <TableRow key={f.id} data-testid={`me-fine-row-${f.id}`}>
                <TableCell className="whitespace-nowrap text-sm text-slate-700">{f.date_debut ? dateFr(f.date_debut) : "—"}{f.heure_infraction ? ` ${f.heure_infraction}` : ""}</TableCell>
                <TableCell className="text-sm">
                  <span className="font-semibold text-slate-900" data-testid={`me-fine-plate-${f.id}`}>{f.plaque || "—"}</span>
                  {f.vehicule_label && <span className="ml-1.5 text-xs text-slate-400">{f.vehicule_label}</span>}
                </TableCell>
                <TableCell className="text-sm text-slate-600">{f.fournisseur || "—"}{f.numero ? <span className="block text-xs text-slate-400">n° {f.numero}</span> : null}</TableCell>
                <TableCell className="text-sm text-slate-600">{f.type_infraction_label || "—"}{f.lieu_label ? <span className="block text-xs text-slate-400">{f.lieu_label}</span> : null}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900" data-testid={`me-fine-amount-${f.id}`}>
                  {f.montant != null ? chfExact(f.montant, f.devise || "CHF") : "—"}
                </TableCell>
                <TableCell><Deadline f={f} /></TableCell>
                <TableCell><FineStatusBadge status={f.fine_status} late={f.days_remaining != null && f.days_remaining < 0} /></TableCell>
                <TableCell>
                  <div className="flex justify-end">
                    {f.storage_path ? (
                      <button type="button" onClick={() => window.open(fileUrl(f.storage_path, { download: true, filename: f.original_filename }), "_blank", "noopener")}
                        data-testid={`me-fine-download-${f.id}`} aria-label="Télécharger"
                        className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Download className="h-4 w-4" /></button>
                    ) : <span className="text-xs text-slate-400">sans fichier</span>}
                  </div>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </DriverShell>
  );
}
