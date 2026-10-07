import { useQuery } from "@tanstack/react-query";
import { History } from "lucide-react";
import { getDocumentHistory } from "@/lib/api";
import { dateFrLong } from "@/lib/format";

const ACTION_FR = {
  create: "Création", legacy_replay: "Rejeu import", validate: "Validation", modify: "Modification", attach_file: "Justificatif joint",
  fine_status_change: "Changement de statut", fine_cancel: "Annulation", fine_recharge: "Refacturation", fine_close: "Clôture",
  fine_dispute: "Contestation", fine_paid: "Paiement", fine_unpaid: "Retour « à payer »", fine_payment_reverted: "Dé-paiement (correction)", fine_driver: "Conducteur",
  fine_due_date: "Échéance", fine_payment_ref: "Réf. paiement", fine_attachment_add: "Pièce ajoutée",
  fine_attachment_file: "Fichier de pièce", fine_attachment_remove: "Pièce retirée", delete: "Suppression",
};
const ACTION_CLS = {
  fine_cancel: "bg-red-100 text-red-700", fine_paid: "bg-emerald-100 text-emerald-700", fine_unpaid: "bg-amber-100 text-amber-800", fine_payment_reverted: "bg-amber-100 text-amber-800",
  fine_recharge: "bg-teal-100 text-teal-700", fine_close: "bg-slate-200 text-slate-700", fine_dispute: "bg-orange-100 text-orange-700",
  fine_driver: "bg-indigo-100 text-indigo-700", fine_attachment_add: "bg-sky-100 text-sky-700", fine_attachment_remove: "bg-sky-100 text-sky-700",
  fine_attachment_file: "bg-sky-100 text-sky-700", create: "bg-slate-100 text-slate-700",
};

// Historique métier chronologique de l'amende (audit filtré par entité, tenant-scopé, côté serveur).
export default function FineHistory({ docId }) {
  const { data: rows = [], isLoading } = useQuery({ queryKey: ["fine-history", docId], queryFn: () => getDocumentHistory(docId), enabled: !!docId });
  return (
    <section className="space-y-2" data-testid="fine-history">
      <h4 className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500"><History className="h-3.5 w-3.5" /> Historique ({rows.length})</h4>
      {!isLoading && rows.length === 0 && <p className="text-xs text-slate-400">Aucun événement.</p>}
      <ol className="relative space-y-3 border-l border-slate-200 pl-4">
        {rows.map((r) => (
          <li key={r.id} className="relative" data-testid={`fine-history-${r.action}`}>
            <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full border-2 border-white bg-slate-400" />
            <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
              <span className={`rounded px-1.5 py-0.5 text-[10px] font-bold uppercase ${ACTION_CLS[r.action] || "bg-slate-100 text-slate-600"}`}>{ACTION_FR[r.action] || r.action}</span>
              <span>{dateFrLong(r.created_at)}</span>
              <span className="text-slate-400">· {r.user}</span>
            </div>
            <p className="mt-0.5 text-sm text-slate-700">{r.detail}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
