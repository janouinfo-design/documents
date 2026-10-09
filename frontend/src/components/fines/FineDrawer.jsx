import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { CheckCircle2, Undo2, Truck, Loader2, Eye } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getFine } from "@/lib/api";
import { chfExact, dateFr } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import FineStatusBadge from "@/components/fines/FineStatusBadge";
import FineStatusControl from "@/components/fines/FineStatusControl";
import FinePaymentDialog from "@/components/fines/FinePaymentDialog";
import FineUnpayDialog from "@/components/fines/FineUnpayDialog";
import FineInfoForm from "@/components/fines/FineInfoForm";
import FineAttachments from "@/components/fines/FineAttachments";
import FineHistory from "@/components/fines/FineHistory";
import { NoFileBadge, AttachFileButton, hasNoFile } from "@/components/documents/NoFileBadge";
import FilePreview from "@/components/FilePreview";
import { PAID_STATUSES } from "@/lib/fines";

function PaymentCard({ doc, canEdit }) {
  const [payOpen, setPayOpen] = useState(false);
  const [unpayOpen, setUnpayOpen] = useState(false);
  const paid = PAID_STATUSES.includes(doc.fine_status);
  return (
    <section className="rounded-xl border border-slate-200 bg-slate-50 p-4" data-testid="fine-payment-card">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Paiement</h4>
          {doc.payee ? (
            <p className="mt-1 text-sm text-slate-800" data-testid="fine-paid-on">
              Payée le <strong>{doc.paid_on ? dateFr(doc.paid_on) : "— (date métier non renseignée)"}</strong>
              {doc.payment_ref && <span className="ml-2 rounded bg-white px-1.5 py-0.5 text-xs text-slate-600" data-testid="fine-payment-ref-value">Réf. {doc.payment_ref}</span>}
            </p>
          ) : (
            <p className="mt-1 text-sm text-slate-600" data-testid="fine-unpaid">
              {doc.fine_status === "annulee" ? "Annulée — aucun paiement attendu." : doc.fine_status === "cloturee" ? "Clôturée." : "Non payée."}
              {doc.date_expiration && doc.deadline_active && <> Échéance le {dateFr(doc.date_expiration)}{doc.days_remaining != null && doc.days_remaining < 0 ? " — en retard" : ""}.</>}
            </p>
          )}
        </div>
        {canEdit && doc.fine_status !== "annulee" && (
          paid ? (
            <Button size="sm" variant="outline" onClick={() => setUnpayOpen(true)} data-testid="fine-unpay-btn" className="gap-1.5">
              <Undo2 className="h-4 w-4" /> Annuler le paiement
            </Button>
          ) : (
            <Button size="sm" onClick={() => setPayOpen(true)} data-testid="fine-pay-btn" className="gap-1.5 bg-emerald-600 hover:bg-emerald-700">
              <CheckCircle2 className="h-4 w-4" /> Marquer payée
            </Button>
          )
        )}
      </div>
      <FinePaymentDialog doc={doc} open={payOpen} onOpenChange={setPayOpen} />
      <FineUnpayDialog doc={doc} open={unpayOpen} onOpenChange={setUnpayOpen} />
    </section>
  );
}

// Fiche amende (Sheet) : statut, paiement, champs, conducteur, pièces liées, historique — même source que la liste (/api/fines).
export default function FineDrawer({ fineId, onOpenChange }) {
  const { user } = useAuth();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = can(user, "fines.write");
  const [filePreview, setFilePreview] = useState(false);
  const { data: doc } = useQuery({ queryKey: ["fines", "one", fineId], queryFn: () => getFine(fineId), enabled: !!fineId });
  const canEdit = isAdmin && !!doc && doc.fine_status !== "annulee";
  return (
    <Sheet open={!!fineId} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-3xl" data-testid="fine-drawer">
        {!doc ? (
          <div className="p-8"><SheetTitle className="sr-only">Amende</SheetTitle><SheetDescription className="sr-only">Chargement</SheetDescription><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
        ) : (
          <div className="space-y-6 p-6">
            <header className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <FineStatusBadge status={doc.fine_status} late={doc.days_remaining != null && doc.days_remaining < 0} />
                {doc.fine_status === "refacturee" && <span className="rounded-full bg-teal-600 px-2 py-0.5 text-[10px] font-bold text-white" data-testid="fine-recharged-marker">Payée · refacturée</span>}
                <NoFileBadge doc={doc} />
                {doc.pending_fx && <span className="rounded-full border border-dashed border-sky-400 bg-sky-50 px-2 py-0.5 text-[10px] font-bold text-sky-800">Conversion en attente</span>}
              </div>
              <SheetTitle className="font-display text-2xl font-bold tracking-tight text-slate-900" data-testid="fine-drawer-title">
                {doc.fournisseur || "Amende"}{doc.numero ? ` · n° ${doc.numero}` : ""}
              </SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
                <strong className={`text-base ${doc.fine_status === "annulee" ? "text-slate-500 line-through" : "text-slate-900"}`} data-testid="fine-drawer-amount">
                  {doc.montant != null ? chfExact(doc.montant, doc.devise) : "Montant non renseigné"}
                </strong>
                {doc.fine_status === "annulee" && <span className="text-xs text-slate-500">montant conservé, exclu des coûts (D9)</span>}
                {doc.date_debut && <span>Infraction le {dateFr(doc.date_debut)}</span>}
                <button type="button" onClick={() => openVehicle(doc.vehicle_id)} className="inline-flex items-center gap-1 font-semibold text-slate-700 hover:underline" data-testid="fine-drawer-vehicle">
                  <Truck className="h-3.5 w-3.5" /> {doc.plaque || doc.vehicle_id}{doc.vehicule_label ? ` · ${doc.vehicule_label}` : ""}
                </button>
                <span data-testid="fine-drawer-driver">Conducteur : {doc.driver_nom || "non identifié"}</span>
              </SheetDescription>
            </header>

            <div className="flex flex-wrap items-center gap-3">
              <span className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Statut</span>
              <FineStatusControl doc={doc} disabled={!isAdmin} />
              {!hasNoFile(doc) && (
                <Button size="sm" variant="outline" onClick={() => setFilePreview(true)} data-testid="fine-file-preview-btn" className="gap-1.5">
                  <Eye className="h-4 w-4" /> Aperçu du fichier
                </Button>
              )}
              {isAdmin && <AttachFileButton doc={doc} />}
            </div>

            <PaymentCard doc={doc} canEdit={isAdmin} />
            <Separator />
            <FineInfoForm doc={doc} canEdit={canEdit} isAdmin={isAdmin} />
            <Separator />
            <FineAttachments docId={doc.id} canEdit={isAdmin} canDelete={can(user, "fines.attachments.delete")} />
            <Separator />
            <FineHistory docId={doc.id} />
            <FilePreview open={filePreview} onOpenChange={setFilePreview}
              file={!hasNoFile(doc) ? { path: doc.storage_path, content_type: doc.content_type, original_filename: doc.original_filename } : null} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
