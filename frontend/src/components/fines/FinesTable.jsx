import { Gavel, Paperclip, UserRound } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import FineStatusBadge from "@/components/fines/FineStatusBadge";
import { NoFileBadge } from "@/components/documents/NoFileBadge";
import { chfExact, dateFr, daysLabel } from "@/lib/format";
import { infractionLabel } from "@/lib/fines";
import { cn } from "@/lib/utils";

// Tableau des amendes — l'essentiel visible d'un coup d'œil : référence, véhicule, conducteur, infraction, échéance, montant, statut, paiement.
export default function FinesTable({ items, isLoading, onOpen }) {
  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="overflow-x-auto">
        <Table data-testid="fines-table">
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Référence</TableHead>
              <TableHead>Véhicule</TableHead>
              <TableHead>Conducteur</TableHead>
              <TableHead>Infraction</TableHead>
              <TableHead>Échéance</TableHead>
              <TableHead className="text-right">Montant</TableHead>
              <TableHead>Statut</TableHead>
              <TableHead>Paiement</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {!isLoading && items.length === 0 && (
              <TableRow><TableCell colSpan={8}>
                <div className="flex flex-col items-center gap-2 py-12 text-center" data-testid="fines-empty">
                  <Gavel className="h-8 w-8 text-slate-300" />
                  <p className="text-sm font-medium text-slate-600">Aucune amende dans cette vue</p>
                </div>
              </TableCell></TableRow>
            )}
            {items.map((d) => {
              const late = d.days_remaining != null && d.days_remaining < 0;
              const cancelled = d.fine_status === "annulee";
              return (
                <TableRow key={d.id} data-testid={`fine-row-${d.id}`} onClick={() => onOpen(d.id)}
                  className={cn("cursor-pointer hover:bg-slate-50", cancelled && "opacity-70")}>
                  <TableCell>
                    <p className="text-sm font-semibold text-slate-800" data-testid={`fine-ref-${d.id}`}>{d.numero || d.dossier_interne || "—"}</p>
                    <p className="flex flex-wrap items-center gap-1 text-xs text-slate-500">
                      {d.fournisseur || "Autorité inconnue"}
                      {d.dossier_interne && d.numero ? <span>· {d.dossier_interne}</span> : null}
                      <NoFileBadge doc={d} />
                      {d.attachments_count > 0 && <span className="inline-flex items-center gap-0.5 text-slate-400" title={`${d.attachments_count} pièce(s) liée(s)`} data-testid={`fine-att-count-${d.id}`}><Paperclip className="h-3 w-3" />{d.attachments_count}</span>}
                    </p>
                  </TableCell>
                  <TableCell>
                    <p className="text-sm font-medium text-slate-800">{d.plaque || "—"}</p>
                    <p className="text-xs text-slate-500">{d.vehicule_label}</p>
                  </TableCell>
                  <TableCell className="text-sm text-slate-700" data-testid={`fine-driver-${d.id}`}>
                    {d.driver_nom ? <span className="inline-flex items-center gap-1"><UserRound className="h-3.5 w-3.5 text-slate-400" />{d.driver_nom}</span> : <span className="text-xs italic text-slate-400">non identifié</span>}
                  </TableCell>
                  <TableCell>
                    <p className="text-sm text-slate-700">{d.date_debut ? dateFr(d.date_debut) : "—"}</p>
                    <p className="text-xs text-slate-500">{infractionLabel(d.type_infraction || "other")}{d.lieu_label ? ` · ${d.lieu_label}` : ""}</p>
                  </TableCell>
                  <TableCell>
                    {d.date_expiration ? (
                      <>
                        <p className={cn("text-sm", late && d.deadline_active ? "font-semibold text-red-600" : "text-slate-700")}>{dateFr(d.date_expiration)}</p>
                        {d.deadline_active && <p className="text-xs text-slate-500" data-testid={`fine-days-${d.id}`}>{daysLabel(d.days_remaining)}</p>}
                      </>
                    ) : <span className="text-xs text-slate-400">—</span>}
                  </TableCell>
                  <TableCell className="text-right">
                    <p className={cn("text-sm font-semibold", cancelled ? "text-slate-500 line-through" : "text-slate-900")} data-testid={`fine-amount-${d.id}`}>
                      {d.montant != null ? chfExact(d.montant, d.devise) : "—"}
                    </p>
                    {d.pending_fx && <p className="text-[10px] text-sky-700">conversion en attente</p>}
                    {d.frais_admin != null && d.frais_admin > 0 && <p className="text-[10px] text-slate-400">dont frais {chfExact(d.frais_admin, d.devise)}</p>}
                  </TableCell>
                  <TableCell><FineStatusBadge status={d.fine_status} late={late} /></TableCell>
                  <TableCell className="text-xs text-slate-600" data-testid={`fine-paid-${d.id}`}>
                    {d.payee ? <>Payée{d.paid_on ? ` le ${dateFr(d.paid_on)}` : ""}{d.payment_ref ? <span className="block text-slate-400">réf. {d.payment_ref}</span> : null}</> : <span className="text-slate-400">—</span>}
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
