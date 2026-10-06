import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, Undo2, Loader2 } from "lucide-react";
import { setDocumentPaid } from "@/lib/api";
import { chfExact, dateFr } from "@/lib/format";
import { cn } from "@/lib/utils";

// Amende = document validé (business_category AMENDE) : coût porté par le document, échéance = délai de paiement.
export const isFineDoc = (d) => d?.document_type === "amende" || d?.business_category === "AMENDE";

export function FineSummary({ doc, className }) {
  if (!isFineDoc(doc) || doc.extraction_status !== "validated") return null;
  const parts = [
    doc.fournisseur,
    doc.numero ? `N° ${doc.numero}` : null,
    doc.date_debut ? `Infraction le ${dateFr(doc.date_debut)}` : null,
    doc.date_expiration ? `À payer avant le ${dateFr(doc.date_expiration)}` : "Délai de paiement non renseigné",
    doc.payee && doc.paid_at ? `Payée le ${dateFr(doc.paid_at)}` : null,
  ].filter(Boolean);
  return (
    <span data-testid={`fine-summary-${doc.id}`} className={cn("text-xs text-slate-500", className)}>
      {doc.montant != null && <strong className="text-slate-700">{chfExact(doc.montant, doc.devise)}</strong>}
      {doc.montant != null && parts.length > 0 && " · "}
      {parts.join(" · ")}
    </span>
  );
}

// Action explicite « Marquer comme payée » / « Annuler le paiement » — jamais de suppression, tout est audité.
export function FinePaidButton({ doc, disabled, onChanged, size = "sm" }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  if (!isFineDoc(doc) || doc.extraction_status !== "validated") return null;
  const paid = !!doc.payee;

  const toggle = async () => {
    setBusy(true);
    try {
      await setDocumentPaid(doc.id, !paid);
      toast.success(paid ? "Paiement annulé — l'amende est à nouveau à payer" : "Amende marquée comme payée");
      ["all-documents", "deadlines", "dashboard", "costs"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
      onChanged?.();
    } catch (e) {
      const detail = e?.response?.data?.detail;
      toast.error((typeof detail === "string" && detail) || detail?.message || "Action impossible");
    } finally {
      setBusy(false);
    }
  };

  return (
    <button
      type="button"
      onClick={toggle}
      disabled={disabled || busy}
      data-testid={`fine-paid-toggle-${doc.id}`}
      title={paid ? "Annuler le statut payée" : "Marquer comme payée"}
      className={cn(
        "inline-flex items-center gap-1.5 rounded-lg border font-semibold transition-colors disabled:opacity-50",
        size === "sm" ? "h-8 px-2.5 text-xs" : "h-9 px-3 text-sm",
        paid
          ? "border-slate-200 text-slate-600 hover:border-slate-400 hover:bg-slate-50"
          : "border-emerald-300 bg-emerald-50 text-emerald-700 hover:bg-emerald-100"
      )}
    >
      {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : paid ? <Undo2 className="h-3.5 w-3.5" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
      {paid ? "Annuler le paiement" : "Marquer comme payée"}
    </button>
  );
}
