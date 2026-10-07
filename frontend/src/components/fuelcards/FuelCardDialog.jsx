import { useEffect, useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { AlertTriangle } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { F } from "@/components/documents/nofileShared";
import { createFuelCard, updateFuelCard } from "@/lib/api";
import { ASSIGNMENT_TYPES, CARD_STATUSES, CARD_STATUS_META, errDetail, errCode } from "@/lib/fuelCards";

const EMPTY = { fournisseur: "", last4: "", compte_fournisseur: "", external_card_id: "", numero_masque: "", type_affectation: "vehicule",
  activee_le: "", expire_le: "", statut: "active", plafond_tx: "", plafond_jour: "", plafond_mois: "", produits_autorises: "", pays_autorises: "", notes: "" };
const num = (v) => (v === "" || v == null ? null : Number(v));
const list = (v) => (v || "").split(",").map((x) => x.trim()).filter(Boolean);

// Création / édition d'une carte. Identité (fournisseur, last4) NON unique : une collision est signalée et doit être confirmée (D2).
export default function FuelCardDialog({ open, onOpenChange, card, onSaved }) {
  const qc = useQueryClient();
  const [f, setF] = useState(EMPTY);
  const [busy, setBusy] = useState(false);
  const [collision, setCollision] = useState(null);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));
  useEffect(() => {
    if (!open) return;
    setCollision(null);
    setF(card ? { ...EMPTY, ...Object.fromEntries(Object.keys(EMPTY).map((k) => [k, card[k] ?? ""])),
      produits_autorises: (card.produits_autorises || []).join(", "), pays_autorises: (card.pays_autorises || []).join(", ") } : EMPTY);
  }, [open, card]);

  const body = (confirmed) => ({
    fournisseur: f.fournisseur.trim(), last4: f.last4.trim(), compte_fournisseur: f.compte_fournisseur || null, external_card_id: f.external_card_id || null,
    numero_masque: f.numero_masque || null, type_affectation: f.type_affectation, activee_le: f.activee_le || null, expire_le: f.expire_le || null,
    plafond_tx: num(f.plafond_tx), plafond_jour: num(f.plafond_jour), plafond_mois: num(f.plafond_mois),
    produits_autorises: list(f.produits_autorises), pays_autorises: list(f.pays_autorises), notes: f.notes || null,
    collision_confirmed: confirmed, ...(card ? {} : { statut: f.statut }),
  });

  const submit = async (confirmed = false) => {
    setBusy(true);
    try {
      const r = card ? await updateFuelCard(card.id, body(confirmed)) : await createFuelCard(body(confirmed));
      toast.success(card ? "Carte mise à jour" : `Carte ${r.label} créée`);
      qc.invalidateQueries({ queryKey: ["fuel-cards"] });
      qc.invalidateQueries({ queryKey: ["deadlines"] });
      onSaved?.(r);
      onOpenChange(false);
    } catch (e) {
      if (errCode(e) === "LAST4_COLLISION") setCollision(e.response.data.detail);
      else toast.error(errDetail(e, "Enregistrement impossible"));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[92vh] max-w-2xl overflow-y-auto" data-testid="fuel-card-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">{card ? `Modifier ${card.label}` : "Nouvelle carte carburant"}</DialogTitle>
          <DialogDescription>Seuls les 4 derniers chiffres sont enregistrés — jamais le numéro complet. Plusieurs cartes peuvent partager fournisseur et last4.</DialogDescription>
        </DialogHeader>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <F label="Fournisseur / émetteur *"><Input data-testid="fuel-card-fournisseur" value={f.fournisseur} onChange={set("fournisseur")} placeholder="Migrol, Shell, AVIA…" /></F>
          <F label="4 derniers chiffres *"><Input data-testid="fuel-card-last4" value={f.last4} onChange={set("last4")} maxLength={4} inputMode="numeric" placeholder="1234" /></F>
          <F label="Compte fournisseur"><Input data-testid="fuel-card-compte" value={f.compte_fournisseur} onChange={set("compte_fournisseur")} /></F>
          <F label="Identifiant fournisseur (external_card_id)"><Input data-testid="fuel-card-external-id" value={f.external_card_id} onChange={set("external_card_id")} /></F>
          <F label="Numéro masqué (affichage)"><Input data-testid="fuel-card-numero-masque" value={f.numero_masque} onChange={set("numero_masque")} placeholder="**** **** 1234" /></F>
          <F label="Type d'usage">
            <Select value={f.type_affectation} onValueChange={set("type_affectation")}>
              <SelectTrigger data-testid="fuel-card-type"><SelectValue /></SelectTrigger>
              <SelectContent>{ASSIGNMENT_TYPES.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}</SelectContent>
            </Select>
          </F>
          <F label="Activée le"><Input type="date" data-testid="fuel-card-activee-le" value={f.activee_le} onChange={set("activee_le")} /></F>
          <F label="Expire le"><Input type="date" data-testid="fuel-card-expire-le" value={f.expire_le} onChange={set("expire_le")} /></F>
          {!card && (
            <F label="Statut initial">
              <Select value={f.statut} onValueChange={set("statut")}>
                <SelectTrigger data-testid="fuel-card-statut"><SelectValue /></SelectTrigger>
                <SelectContent>{CARD_STATUSES.map((s) => <SelectItem key={s} value={s}>{CARD_STATUS_META[s].label}</SelectItem>)}</SelectContent>
              </Select>
            </F>
          )}
          <F label="Plafond / transaction (CHF, déclaratif)"><Input type="number" step="0.01" data-testid="fuel-card-plafond-tx" value={f.plafond_tx} onChange={set("plafond_tx")} /></F>
          <F label="Plafond / jour"><Input type="number" step="0.01" data-testid="fuel-card-plafond-jour" value={f.plafond_jour} onChange={set("plafond_jour")} /></F>
          <F label="Plafond / mois"><Input type="number" step="0.01" data-testid="fuel-card-plafond-mois" value={f.plafond_mois} onChange={set("plafond_mois")} /></F>
          <F label="Produits autorisés (séparés par des virgules)"><Input data-testid="fuel-card-produits" value={f.produits_autorises} onChange={set("produits_autorises")} placeholder="diesel, adblue" /></F>
          <F label="Pays autorisés"><Input data-testid="fuel-card-pays" value={f.pays_autorises} onChange={set("pays_autorises")} placeholder="CH, FR" /></F>
          <F label="Notes" className="sm:col-span-2"><Textarea rows={2} data-testid="fuel-card-notes" value={f.notes} onChange={set("notes")} /></F>
        </div>
        {collision && (
          <div className="rounded-lg border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900" data-testid="fuel-card-collision-box">
            <p className="flex items-center gap-1.5 font-semibold"><AlertTriangle className="h-4 w-4" /> Même fournisseur et mêmes 4 chiffres qu'une carte existante</p>
            <ul className="mt-1 list-disc pl-5 text-xs">
              {collision.cards.map((c) => <li key={c.id}>{c.label} · {c.statut}{c.external_card_id ? ` · id ${c.external_card_id}` : ""}{c.is_deleted ? " · archivée" : ""}</li>)}
            </ul>
            <p className="mt-1 text-xs">L'identité (fournisseur, last4) n'est pas unique : confirmez qu'il s'agit bien d'une carte distincte. Aucune fusion automatique.</p>
          </div>
        )}
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fuel-card-cancel">Annuler</Button>
          {collision ? (
            <Button onClick={() => submit(true)} disabled={busy} className="bg-amber-600 hover:bg-amber-700" data-testid="fuel-card-confirm-collision">
              {busy ? "Enregistrement…" : "Confirmer : carte distincte"}
            </Button>
          ) : (
            <Button onClick={() => submit(false)} disabled={busy || !f.fournisseur.trim() || !/^\d{4}$/.test(f.last4.trim())} className="bg-slate-900 hover:bg-slate-800" data-testid="fuel-card-submit">
              {busy ? "Enregistrement…" : card ? "Enregistrer" : "Créer la carte"}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
