import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { Loader2, Fuel, CreditCard, Truck, FileText, AlertTriangle, PenLine } from "lucide-react";
import { Sheet, SheetContent, SheetTitle, SheetDescription } from "@/components/ui/sheet";
import { Button } from "@/components/ui/button";
import { Separator } from "@/components/ui/separator";
import { getFuelTransaction } from "@/lib/api";
import { chfExact, dateFr } from "@/lib/format";
import { useAuth } from "@/context/AuthContext";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";
import Pill from "@/components/energy/Pill";
import MatchBreakdown from "@/components/energy/MatchBreakdown";
import AnomalyList from "@/components/energy/AnomalyList";
import AnomalyDecisionDialog from "@/components/energy/AnomalyDecisionDialog";
import { VehicleCorrectionDialog, CardChoiceDialog } from "@/components/energy/TransactionDialogs";
import { MATCH_META, CARD_RES_META } from "@/lib/fuelImport";
import { cardStatusLabel } from "@/lib/fuelCards";

const Row = ({ k, v, testId }) => (
  <div className="flex justify-between gap-3 py-1 text-sm"><span className="text-slate-500">{k}</span><span className="text-right font-medium text-slate-800" data-testid={testId}>{v ?? "—"}</span></div>
);
const Section = ({ icon: Icon, title, children, testId }) => (
  <section className="space-y-2" data-testid={testId}>
    <h3 className="flex items-center gap-2 font-display text-sm font-bold uppercase tracking-wide text-slate-500"><Icon className="h-4 w-4" /> {title}</h3>
    {children}
  </section>
);
const FX = { not_needed: "CHF (sans conversion)", converted: "Contre-valeur CHF renseignée", pending: "FX en attente — exclu des totaux CHF" };

// Fiche transaction (Sheet) : données, document lié (coût), carte résolue / card_id, véhicule + scoring explicable, anomalies, source import. read_only : aucune action.
export default function TransactionDrawer({ txId, onOpenChange }) {
  const { user } = useAuth();
  const { openVehicle } = useVehicleDrawer();
  const isAdmin = ["admin", "superadmin"].includes(user?.role);
  const { data: tx, isError, error } = useQuery({ queryKey: ["fuel-tx", txId], queryFn: () => getFuelTransaction(txId), enabled: !!txId });
  const [vehicleDlg, setVehicleDlg] = useState(false);
  const [cardDlg, setCardDlg] = useState(false);
  const [decide, setDecide] = useState(null);
  const cardCode = tx?.card_manual ? "manual" : tx?.carte_last4 ? tx?.card_resolution?.status || "none" : "none";
  return (
    <Sheet open={!!txId} onOpenChange={onOpenChange}>
      <SheetContent side="right" className="w-full overflow-y-auto p-0 sm:max-w-3xl" data-testid="fuel-transaction-drawer">
        {!tx ? (
          <div className="p-8"><SheetTitle className="sr-only">Transaction</SheetTitle><SheetDescription className="sr-only">Chargement</SheetDescription>
            {isError ? <p className="text-sm text-red-600" data-testid="fuel-transaction-drawer-error">{error?.response?.status === 404 ? "Transaction introuvable dans ce tenant." : "Impossible de charger la transaction."}</p> : <Loader2 className="h-6 w-6 animate-spin text-slate-400" />}
          </div>
        ) : (
          <div className="space-y-6 p-6">
            <header className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <Pill map={MATCH_META} code={tx.match_status} testId="fuel-transaction-match-status" />
                <Pill map={CARD_RES_META} code={cardCode} testId="fuel-transaction-card-status" />
                {tx.anomalies_open > 0 && <span className="rounded-full bg-rose-600 px-2 py-0.5 text-[10px] font-bold text-white" data-testid="fuel-transaction-anomalies-open">{tx.anomalies_open} anomalie(s) ouverte(s)</span>}
                {["manual", "legacy_import", "import"].includes(tx.created_from) && <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-amber-400 bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold text-amber-800" data-testid="fuel-transaction-declarative"><PenLine className="h-2.5 w-2.5" /> déclaratif · {tx.created_from}</span>}
              </div>
              <SheetTitle className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-slate-900" data-testid="fuel-transaction-drawer-title">
                <Fuel className="h-6 w-6 text-slate-400" /> {tx.station || tx.fournisseur || "Transaction"} — {tx.montant != null ? chfExact(tx.montant, tx.devise || "CHF") : "—"}
              </SheetTitle>
              <SheetDescription className="text-sm text-slate-500">{dateFr(tx.date)}{tx.heure ? ` ${tx.heure}` : ""} · {tx.fournisseur || "fournisseur inconnu"}{tx.external_transaction_id ? ` · réf. ${tx.external_transaction_id}` : ""}</SheetDescription>
            </header>

            {isAdmin && (
              <div className="flex flex-wrap gap-2">
                <Button size="sm" variant="outline" onClick={() => setVehicleDlg(true)} className="gap-1.5" data-testid="fuel-vehicle-correct-btn"><Truck className="h-4 w-4" /> Corriger le véhicule</Button>
                <Button size="sm" variant="outline" onClick={() => setCardDlg(true)} className="gap-1.5" data-testid="fuel-card-choose-btn"><CreditCard className="h-4 w-4" /> Choisir la carte</Button>
              </div>
            )}

            <Section icon={Fuel} title="Transaction" testId="fuel-transaction-section-data">
              <Row k="Énergie / produit" v={tx.type_carburant || (tx.energie === "electrique" ? "Électricité" : "Carburant")} />
              <Row k="Quantité" v={tx.energie === "electrique" ? (tx.energie_kwh != null ? `${tx.energie_kwh} kWh` : null) : (tx.litres != null ? `${tx.litres} L` : null)} />
              <Row k="Prix unitaire" v={tx.energie === "electrique" ? (tx.prix_kwh != null ? `${tx.prix_kwh} ${tx.devise}/kWh` : null) : (tx.prix_litre != null ? `${tx.prix_litre} ${tx.devise}/L` : null)} />
              <Row k="Montant" v={tx.montant != null ? chfExact(tx.montant, tx.devise || "CHF") : null} testId="fuel-transaction-amount" />
              <Row k="Devise / FX" v={`${tx.devise || "CHF"}${tx.devise && tx.devise !== "CHF" ? ` — ${tx.montant_chf != null ? `= ${chfExact(tx.montant_chf)}` : "FX en attente"}` : ""}${tx.fx_status ? ` · ${FX[tx.fx_status] || tx.fx_status}` : ""}`} testId="fuel-transaction-fx" />
              <Row k="Kilométrage" v={tx.kilometrage ? `${tx.kilometrage} km` : null} />
              <Row k="Conducteur" v={tx.driver_nom || tx.driver_hint} testId="fuel-transaction-driver" />
              <Row k="Source" v={<>{tx.created_from || "document"}{tx.import_job_id && <> · <Link className="underline" to={`/energie/imports?job=${tx.import_job_id}`} data-testid="fuel-transaction-import-link">import{tx.import_row_id ? " (ligne)" : ""}</Link></>}</>} testId="fuel-transaction-source" />
              {tx.commentaire && <Row k="Commentaire" v={tx.commentaire} />}
            </Section>
            <Separator />
            <Section icon={FileText} title="Document lié (source du coût)" testId="fuel-transaction-section-document">
              {tx.document ? (<>
                <Row k="Libellé" v={tx.document.label} testId="fuel-transaction-document-label" />
                <Row k="Justificatif" v={tx.document.justificatif_absent ? "Absent (document sans fichier)" : tx.document.original_filename || "Fichier"} />
                <Row k="Coût compté (Coûts)" v={tx.document.cost ? (tx.document.cost.pending_fx ? `FX en attente — ${tx.document.cost.montant} ${tx.document.cost.devise} exclu des totaux CHF` : `${chfExact(tx.document.cost.montant_chf)} · ${tx.document.cost.category_label || ""}`) : null} testId="fuel-transaction-document-cost" />
              </>) : <p className="text-sm text-slate-400">Aucun document lié.</p>}
            </Section>
            <Separator />
            <Section icon={CreditCard} title="Carte" testId="fuel-transaction-section-card">
              <Row k="Carte lue (fichier)" v={tx.carte_last4 ? `••••${tx.carte_last4}` : null} />
              <Row k="Résolution" v={`${tx.card_resolution?.status || "—"}${tx.card_resolution?.level ? ` (${tx.card_resolution.level})` : ""}${tx.card_manual ? " · décision manuelle" : ""}`} testId="fuel-transaction-card-resolution" />
              <Row k="card_id" v={tx.card_id ? <>{tx.card?.label ? <b>{tx.card.label}</b> : null}<span className="ml-1 font-mono text-[11px] text-slate-500">{tx.card_id}</span></> : null} testId="fuel-transaction-card" />
              {tx.card && (<>
                <Row k="Carte" v={tx.card.label} testId="fuel-transaction-card-label" />
                <Row k="Statut courant" v={`${cardStatusLabel(tx.card.statut)}${tx.card.expire_le ? ` · expire le ${dateFr(tx.card.expire_le)}` : ""}`} />
                {tx.card_inactive?.inactive && <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-800" data-testid="fuel-transaction-card-inactive">
                  CARD_INACTIVE à la date {dateFr(tx.card_inactive.transaction_date)} : {tx.card_inactive.inactive_by_status ? `statut ${tx.card_inactive.card_status_current}` : ""}{tx.card_inactive.inactive_by_status && tx.card_inactive.inactive_by_expiration ? " et " : ""}{tx.card_inactive.inactive_by_expiration ? `expirée le ${dateFr(tx.card_inactive.expire_le)}` : ""} (modèle {tx.card_inactive.evaluation_model})
                </p>}
              </>)}
              {(tx.card_resolution?.candidates || []).length > 1 && (
                <ul className="text-xs text-slate-600" data-testid="fuel-transaction-card-candidates">{tx.card_resolution.candidates.map((c) => <li key={c.id}>• {c.label} · {cardStatusLabel(c.statut)}{c.assigned_plaque ? ` · ${c.assigned_plaque}` : ""}</li>)}</ul>
              )}
            </Section>
            <Separator />
            <Section icon={Truck} title="Véhicule & rattachement" testId="fuel-transaction-section-vehicle">
              <Row k="Véhicule" v={<button type="button" className="underline" onClick={() => openVehicle(tx.vehicle_id, "energie")} data-testid="fuel-transaction-vehicle">{tx.vehicule_label || tx.plaque || tx.vehicle_id}</button>} />
              {tx.vehicle_hint && <Row k="Plaque du fichier" v={<span className="font-mono">{tx.vehicle_hint}</span>} testId="fuel-transaction-plate-hint" />}
              <Row k="Statut" v={tx.match_label || tx.match_status} />
              <Row k="Score" v={tx.match?.score != null ? `${tx.match.score} pt` : null} testId="fuel-transaction-score" />
              <Row k="Méthode" v={tx.match?.method} testId="fuel-transaction-method" />
              {tx.match?.status === "manual" && <Row k="Décidé par" v={`${tx.match.decided_by || "—"} · ${tx.match.decided_at ? new Date(tx.match.decided_at).toLocaleString("fr-CH") : "—"}${tx.match.reason ? ` — ${tx.match.reason}` : ""}`} testId="fuel-transaction-decided" />}
              <MatchBreakdown match={tx.match} vehicleId={tx.vehicle_id} />
            </Section>
            <Separator />
            <Section icon={AlertTriangle} title={`Anomalies (${tx.anomalies?.length || 0})`} testId="fuel-transaction-section-anomalies">
              <AnomalyList anomalies={tx.anomalies} isAdmin={isAdmin} onDecide={setDecide} />
            </Section>

            <VehicleCorrectionDialog tx={tx} open={vehicleDlg} onOpenChange={setVehicleDlg} />
            <CardChoiceDialog tx={tx} open={cardDlg} onOpenChange={setCardDlg} />
            <AnomalyDecisionDialog anomaly={decide} open={!!decide} onOpenChange={(o) => !o && setDecide(null)} />
          </div>
        )}
      </SheetContent>
    </Sheet>
  );
}
