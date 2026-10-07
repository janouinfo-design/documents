import { useState } from "react";
import { CheckCircle2, Undo2, ExternalLink } from "lucide-react";
import { useNavigate } from "react-router-dom";
import { chfExact, dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";
import { PAID_STATUSES, fineStatusLabel } from "@/lib/fines";
import FinePaymentDialog from "@/components/fines/FinePaymentDialog";
import FineUnpayDialog from "@/components/fines/FineUnpayDialog";

// Amende = document validé (business_category AMENDE) : coût porté par le document, échéance = délai de paiement.
// Lot D : UNE seule logique — fine_status (10 valeurs) dérivé par le serveur, paid_on = date métier (jamais paid_at).
export const isFineDoc = (d) => d?.document_type === "amende" || d?.business_category === "AMENDE";

export function FineSummary({ doc, className }) {
  if (!isFineDoc(doc) || doc.extraction_status !== "validated") return null;
  const parts = [
    doc.fournisseur,
    doc.numero ? `N° ${doc.numero}` : null,
    doc.driver_nom ? `Conducteur ${doc.driver_nom}` : null,
    doc.date_debut ? `Infraction le ${dateFr(doc.date_debut)}` : null,
    doc.fine_status && !["a_payer"].includes(doc.fine_status) ? `Statut ${fineStatusLabel(doc.fine_status)}` : null,
    doc.deadline_active ? (doc.date_expiration ? `À payer avant le ${dateFr(doc.date_expiration)}` : "Délai de paiement non renseigné") : null,
    doc.payee ? `Payée${doc.paid_on ? ` le ${dateFr(doc.paid_on)}` : ""}${doc.payment_ref ? ` · réf. ${doc.payment_ref}` : ""}` : null,
    doc.fine_status === "annulee" ? "Annulée — hors coûts et échéances" : null,
  ].filter(Boolean);
  return (
    <span data-testid={`fine-summary-${doc.id}`} className={cn("text-xs text-slate-500", className)}>
      {doc.montant != null && <strong className={cn("text-slate-700", doc.fine_status === "annulee" && "line-through")}>{chfExact(doc.montant, doc.devise)}</strong>}
      {doc.montant != null && parts.length > 0 && " · "}
      {parts.join(" · ")}
    </span>
  );
}

// Action explicite « Marquer comme payée » (date métier saisie) / « Annuler le paiement » (motif obligatoire) — jamais de suppression, tout est audité.
export function FinePaidButton({ doc, disabled, onChanged, size = "sm" }) {
  const navigate = useNavigate();
  const [payOpen, setPayOpen] = useState(false);
  const [unpayOpen, setUnpayOpen] = useState(false);
  if (!isFineDoc(doc) || doc.extraction_status !== "validated") return null;
  const paid = PAID_STATUSES.includes(doc.fine_status) || !!doc.payee;
  const cancelled = doc.fine_status === "annulee";

  const btn = "inline-flex items-center gap-1.5 rounded-lg border font-semibold transition-colors disabled:opacity-50 " + (size === "sm" ? "h-8 px-2.5 text-xs" : "h-9 px-3 text-sm");
  return (
    <span className="inline-flex items-center gap-1.5">
      {!cancelled && (paid ? (
        <button type="button" onClick={() => setUnpayOpen(true)} disabled={disabled} data-testid={`fine-paid-toggle-${doc.id}`} title="Annuler le statut payée (motif obligatoire)"
          className={cn(btn, "border-slate-200 text-slate-600 hover:border-slate-400 hover:bg-slate-50")}>
          <Undo2 className="h-3.5 w-3.5" /> Annuler le paiement
        </button>
      ) : (
        <button type="button" onClick={() => setPayOpen(true)} disabled={disabled} data-testid={`fine-paid-toggle-${doc.id}`} title="Marquer comme payée (date métier)"
          className={cn(btn, "border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100")}>
          <CheckCircle2 className="h-3.5 w-3.5" /> Marquer comme payée
        </button>
      ))}
      <button type="button" onClick={() => navigate(`/amendes?id=${doc.id}`)} data-testid={`fine-open-${doc.id}`} title="Ouvrir la fiche amende"
        className={cn(btn, "border-slate-200 text-slate-600 hover:border-slate-400 hover:bg-slate-50")}>
        <ExternalLink className="h-3.5 w-3.5" /> Fiche
      </button>
      <FinePaymentDialog doc={doc} open={payOpen} onOpenChange={setPayOpen} onDone={onChanged} />
      <FineUnpayDialog doc={doc} open={unpayOpen} onOpenChange={setUnpayOpen} onDone={onChanged} />
    </span>
  );
}
