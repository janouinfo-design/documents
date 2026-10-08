import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Loader2, Pencil, Archive, ArchiveRestore, RefreshCw, Truck, User, CreditCard } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getFuelCard } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import FuelCardStatusBadge, { ExpirationCell, CardWarnings } from "@/components/fuelcards/FuelCardStatusBadge";
import FuelCardDialog from "@/components/fuelcards/FuelCardDialog";
import { FuelCardStatusDialog, FuelCardArchiveDialog } from "@/components/fuelcards/FuelCardLifecycleDialogs";
import { FuelCardAssignments, FuelCardHistory } from "@/components/fuelcards/FuelCardDetails";

const Row = ({ k, v, testId }) => (
  <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-slate-500">{k}</span><span className="text-right font-medium text-slate-800" data-testid={testId}>{v ?? "—"}</span></div>
);

// Fiche carte (Sheet) : identité humaine « Fournisseur ••••1234 » (jamais une clé technique), statut déclaré, expiration dérivée,
// avertissements, affectations datées, historique audit. read_only : aucune action.
export default function FuelCardDrawer({ cardId, onOpenChange }) {
  const { user } = useAuth();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = can(user, "cards.manage");
  const { data: card } = useQuery({ queryKey: ["fuel-cards", "one", cardId], queryFn: () => getFuelCard(cardId), enabled: !!cardId });
  const [edit, setEdit] = useState(false);
  const [status, setStatus] = useState(false);
  const [archive, setArchive] = useState(false);
  const canEdit = isAdmin && card && !card.is_deleted;
  return (
    <Sheet open={!!cardId} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-3xl" data-testid="fuel-card-drawer">
        {!card ? (
          <div className="p-8"><SheetTitle className="sr-only">Carte</SheetTitle><SheetDescription className="sr-only">Chargement</SheetDescription><Loader2 className="h-6 w-6 animate-spin text-slate-400" /></div>
        ) : (
          <div className="space-y-6 p-6">
            <header className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <FuelCardStatusBadge statut={card.statut} />
                {card.is_deleted && <span className="rounded-full bg-slate-800 px-2 py-0.5 text-[10px] font-bold text-white" data-testid="fuel-card-archived-marker">Archivée</span>}
                <span className={`rounded-full px-2 py-0.5 text-[10px] font-bold ${card.utilisable ? "bg-emerald-600 text-white" : "bg-slate-200 text-slate-700"}`} data-testid="fuel-card-usable-marker">
                  {card.utilisable ? "Utilisable" : "Non utilisable"}
                </span>
              </div>
              <SheetTitle className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-slate-900" data-testid="fuel-card-drawer-title">
                <CreditCard className="h-6 w-6 text-slate-400" /> {card.label}
              </SheetTitle>
              <SheetDescription className="flex flex-wrap items-center gap-x-3 gap-y-1 text-sm text-slate-500">
                <span>Type d'usage : {card.type_affectation_label}</span>
                {card.external_card_id && <span>ID fournisseur {card.external_card_id}</span>}
                {card.compte_fournisseur && <span>Compte {card.compte_fournisseur}</span>}
              </SheetDescription>
            </header>

            {isAdmin && (
              <div className="flex flex-wrap gap-2">
                {canEdit && <Button size="sm" variant="outline" onClick={() => setEdit(true)} className="gap-1.5" data-testid="fuel-card-edit-btn"><Pencil className="h-4 w-4" /> Modifier</Button>}
                {canEdit && <Button size="sm" variant="outline" onClick={() => setStatus(true)} className="gap-1.5" data-testid="fuel-card-status-btn"><RefreshCw className="h-4 w-4" /> Changer le statut</Button>}
                {card.is_deleted
                  ? <Button size="sm" variant="outline" onClick={() => setArchive(true)} className="gap-1.5" data-testid="fuel-card-restore-btn"><ArchiveRestore className="h-4 w-4" /> Restaurer</Button>
                  : <Button size="sm" variant="outline" onClick={() => setArchive(true)} className="gap-1.5" data-testid="fuel-card-archive-btn"><Archive className="h-4 w-4" /> Archiver</Button>}
              </div>
            )}

            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-4" data-testid="fuel-card-expiration-card">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Expiration</h3>
                <ExpirationCell card={card} />
                <p className="mt-2 text-[11px] text-slate-500">État dérivé de la date (seuils Échéances du tenant) — le statut déclaré n'est jamais modifié automatiquement.</p>
                <Row k="Activée le" v={card.activee_le ? dateFr(card.activee_le) : null} testId="fuel-card-activee-le-value" />
              </section>
              <section className="rounded-xl border border-slate-200 bg-slate-50/60 p-4" data-testid="fuel-card-current-card">
                <h3 className="mb-2 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Affectation actuelle</h3>
                <p className="flex items-center gap-1.5 text-sm" data-testid="fuel-card-current-vehicle">
                  <Truck className="h-4 w-4 text-slate-400" />
                  {card.vehicule_courant
                    ? <button type="button" className="font-semibold hover:underline" onClick={() => openVehicle(card.vehicule_courant.vehicle_id)}>{card.vehicule_courant.plaque}{card.vehicule_courant.vehicule_label ? ` · ${card.vehicule_courant.vehicule_label}` : ""}</button>
                    : <span className="text-slate-400">Aucun véhicule</span>}
                </p>
                <p className="mt-1 flex items-center gap-1.5 text-sm" data-testid="fuel-card-current-driver">
                  <User className="h-4 w-4 text-slate-400" />
                  {card.conducteur_courant ? <span className="font-semibold">{card.conducteur_courant.driver_nom}</span> : <span className="text-slate-400">Aucun conducteur</span>}
                </p>
                <div className="mt-3"><CardWarnings warnings={card.warnings} cardId={card.id} /></div>
              </section>
            </div>

            <section className="rounded-xl border border-slate-200 p-4" data-testid="fuel-card-info">
              <h3 className="mb-1 text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Fiche</h3>
              <div className="grid grid-cols-1 gap-x-6 sm:grid-cols-2">
                <Row k="Fournisseur" v={card.fournisseur} testId="fuel-card-field-fournisseur" />
                <Row k="4 derniers chiffres" v={`••••${card.last4}`} testId="fuel-card-field-last4" />
                <Row k="Numéro masqué" v={card.numero_masque} />
                <Row k="Statut déclaré" v={card.statut_label} testId="fuel-card-field-statut" />
                <Row k="Plafond / tx" v={card.plafond_tx != null ? `${card.plafond_tx} CHF` : null} />
                <Row k="Plafond / jour" v={card.plafond_jour != null ? `${card.plafond_jour} CHF` : null} />
                <Row k="Plafond / mois" v={card.plafond_mois != null ? `${card.plafond_mois} CHF` : null} />
                <Row k="Produits autorisés" v={card.produits_autorises?.length ? card.produits_autorises.join(", ") : null} />
                <Row k="Pays autorisés" v={card.pays_autorises?.length ? card.pays_autorises.join(", ") : null} />
                <Row k="Remplacée par" v={card.remplacee_par} />
                {card.statut_motif && <Row k="Dernier motif de statut" v={card.statut_motif} testId="fuel-card-field-statut-motif" />}
                {card.archive_motif && card.is_deleted && <Row k="Motif d'archivage" v={card.archive_motif} />}
                {card.source === "legacy_import" && <Row k="Legacy" v={`${card.legacy_source} · ${card.legacy_id}`} />}
              </div>
              {card.notes && <p className="mt-2 rounded bg-slate-50 p-2 text-sm text-slate-700" data-testid="fuel-card-field-notes">{card.notes}</p>}
            </section>

            <Separator />
            <FuelCardAssignments card={card} canEdit={canEdit} />
            <Separator />
            {can(user, "cards.history") && <FuelCardHistory cardId={card.id} />}
          </div>
        )}
        {card && <FuelCardDialog open={edit} onOpenChange={setEdit} card={card} />}
        {card && <FuelCardStatusDialog card={card} open={status} onOpenChange={setStatus} />}
        {card && <FuelCardArchiveDialog card={card} open={archive} onOpenChange={setArchive} />}
      </SheetContent>
    </Sheet>
  );
}
