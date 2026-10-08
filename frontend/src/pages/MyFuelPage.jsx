import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { CheckCircle2, Download, Droplets, Eye, Fuel, Paperclip, Receipt } from "lucide-react";
import { attachMyFuelReceipt, fileUrl, getMyFuelTransactions } from "@/lib/api";
import { chfExact, dateFr, fmtQty } from "@/lib/format";
import KpiCard from "@/components/KpiCard";
import DropZone from "@/components/DropZone";
import FilePreview from "@/components/FilePreview";
import DriverShell from "@/components/me/DriverShell";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";

const ALL = "__all__";
const months = () => Array.from({ length: 12 }, (_, i) => {
  const d = new Date(); d.setDate(1); d.setMonth(d.getMonth() - i);
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
});
const monthLabel = (m) => new Date(`${m}-01T00:00:00`).toLocaleDateString("fr-CH", { month: "long", year: "numeric" });
const qty = (tx) => (tx.litres != null ? fmtQty(tx.litres, "L", 2) : tx.energie_kwh != null ? fmtQty(tx.energie_kwh, "kWh", 2) : "—");

// Dépôt du justificatif : 1 seul fichier (image / PDF) par plein, jamais remplacé — 409 FILE_ALREADY_PRESENT côté serveur.
function ReceiptDialog({ tx, onOpenChange }) {
  const qc = useQueryClient();
  const [busy, setBusy] = useState(false);
  const onFiles = async (files) => {
    const file = files[0];
    if (!file) return;
    setBusy(true);
    try {
      await attachMyFuelReceipt(tx.id, file);
      toast.success(`Justificatif « ${file.name} » joint à votre plein du ${dateFr(tx.date)}`);
      qc.invalidateQueries({ queryKey: ["me", "fuel"] });
      onOpenChange(false);
    } catch (err) {
      const detail = err?.response?.data?.detail;
      if (detail?.code === "FILE_ALREADY_PRESENT") toast.error("Un justificatif est déjà présent pour ce plein — le fichier existant n'a pas été remplacé.");
      else if (err?.response?.status === 404) toast.error("Ce plein ne vous est pas accessible.");
      else toast.error((typeof detail === "string" && detail) || detail?.message || "Impossible de joindre le justificatif");
    } finally {
      setBusy(false);
    }
  };
  return (
    <Dialog open={!!tx} onOpenChange={onOpenChange}>
      <DialogContent data-testid="me-receipt-dialog">
        <DialogHeader>
          <DialogTitle>Joindre le justificatif</DialogTitle>
          <DialogDescription>
            {tx ? `Plein du ${dateFr(tx.date)} · ${tx.station || tx.fournisseur || "station inconnue"} · ${chfExact(tx.montant, tx.devise || "CHF")}. ` : ""}
            Un seul fichier (image ou PDF) ; il ne pourra pas être remplacé ensuite.
          </DialogDescription>
        </DialogHeader>
        <DropZone onFiles={onFiles} multiple={false} busy={busy} accept=".pdf,.jpg,.jpeg,.png,.webp" label="Déposez votre ticket ici"
          hint="Image (JPG, PNG, WEBP) ou PDF · 1 fichier" testId="me-receipt-dropzone" />
      </DialogContent>
    </Dialog>
  );
}

function ReceiptCell({ tx, onAttach, onPreview }) {
  const j = tx.justificatif;
  if (!j) return <span className="text-xs text-slate-400">—</span>;
  if (j.present) {
    return (
      <div className="flex items-center justify-end gap-1">
        <span className="inline-flex items-center gap-1 rounded-full bg-emerald-50 px-2 py-0.5 text-[11px] font-semibold text-emerald-700" data-testid={`me-fuel-receipt-ok-${tx.id}`}>
          <CheckCircle2 className="h-3 w-3" /> Joint
        </span>
        <button type="button" onClick={onPreview} data-testid={`me-fuel-receipt-preview-${tx.id}`} aria-label="Aperçu"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Eye className="h-4 w-4" /></button>
        <button type="button" onClick={() => window.open(fileUrl(j.path, { download: true, filename: j.filename }), "_blank", "noopener")}
          data-testid={`me-fuel-receipt-download-${tx.id}`} aria-label="Télécharger"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Download className="h-4 w-4" /></button>
      </div>
    );
  }
  return (
    <div className="flex justify-end">
      <button type="button" onClick={onAttach} disabled={!!tx.locked} data-testid={`me-fuel-attach-${tx.id}`}
        title={tx.locked ? "Plein inclus dans un décompte clôturé" : "Joindre le ticket (une seule fois)"}
        className="inline-flex h-8 items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-2.5 text-xs font-semibold text-amber-800 transition-colors hover:bg-amber-50 disabled:opacity-50">
        <Paperclip className="h-3.5 w-3.5" /> Joindre le ticket
      </button>
    </div>
  );
}

export default function MyFuelPage() {
  const [period, setPeriod] = useState(ALL);
  const [attachTx, setAttachTx] = useState(null);
  const [preview, setPreview] = useState(null);
  const { data, isLoading, error } = useQuery({
    queryKey: ["me", "fuel", period], retry: false,
    queryFn: () => getMyFuelTransactions(period === ALL ? {} : { period_month: period }),
  });
  const items = data?.items || [];
  const totals = data?.totals || {};
  const missing = items.filter((x) => x.justificatif && !x.justificatif.present).length;
  return (
    <DriverShell title="Mes pleins" icon={Fuel} testId="me-fuel-page" dataError={error} isLoading={isLoading}
      subtitle="Vos transactions carburant, rattachées à votre nom par votre entreprise. Vous pouvez joindre un ticket manquant — une seule fois par plein.">
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard testId="me-fuel-kpi-count" label="Pleins" value={data?.total ?? 0} icon={Fuel} accent="slate" sub={period === ALL ? "toutes périodes" : monthLabel(period)} />
        <KpiCard testId="me-fuel-kpi-depenses" label="Dépenses" value={chfExact(totals.depenses || 0)} icon={Receipt} accent="indigo" sub="montant des pleins" />
        <KpiCard testId="me-fuel-kpi-volume" label="Volume" icon={Droplets} accent="sky" sub="litres ou kWh"
          value={totals.litres ? fmtQty(totals.litres, "L", 1) : totals.energie_kwh ? fmtQty(totals.energie_kwh, "kWh", 1) : "—"} />
        <KpiCard testId="me-fuel-kpi-missing" label="Justificatifs manquants" value={missing} icon={Paperclip} accent={missing ? "amber" : "emerald"} sub={missing ? "tickets à joindre" : "tout est complet"} />
      </div>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-slate-500" data-testid="me-fuel-count">{items.length} plein{items.length > 1 ? "s" : ""} affiché{items.length > 1 ? "s" : ""}</p>
        <Select value={period} onValueChange={setPeriod}>
          <SelectTrigger className="w-60" data-testid="me-fuel-period"><SelectValue /></SelectTrigger>
          <SelectContent>
            <SelectItem value={ALL} data-testid="me-fuel-period-all">Toutes les périodes</SelectItem>
            {months().map((m) => <SelectItem key={m} value={m} data-testid={`me-fuel-period-${m}`}>{monthLabel(m)}</SelectItem>)}
          </SelectContent>
        </Select>
      </div>
      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <Table data-testid="me-fuel-table">
          <TableHeader>
            <TableRow>
              <TableHead>Date</TableHead><TableHead>Véhicule</TableHead><TableHead>Station</TableHead>
              <TableHead className="text-right">Quantité</TableHead><TableHead className="text-right">Montant</TableHead><TableHead className="text-right">Justificatif</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {items.length === 0 && (
              <TableRow><TableCell colSpan={6} className="py-12 text-center text-sm text-slate-400" data-testid="me-fuel-empty">
                Aucun plein enregistré à votre nom{period !== ALL ? " sur cette période" : ""}.
              </TableCell></TableRow>
            )}
            {items.map((tx) => (
              <TableRow key={tx.id} data-testid={`me-fuel-row-${tx.id}`}>
                <TableCell className="whitespace-nowrap text-sm text-slate-700">{dateFr(tx.date)}{tx.heure ? ` ${tx.heure}` : ""}</TableCell>
                <TableCell className="text-sm">
                  <span className="font-semibold text-slate-900" data-testid={`me-fuel-plate-${tx.id}`}>{tx.plaque || "—"}</span>
                  {tx.vehicule_label && <span className="ml-1.5 text-xs text-slate-400">{tx.vehicule_label}</span>}
                </TableCell>
                <TableCell className="text-sm text-slate-600">{tx.station || tx.fournisseur || "—"}</TableCell>
                <TableCell className="text-right text-sm text-slate-600">{qty(tx)}</TableCell>
                <TableCell className="text-right text-sm font-semibold text-slate-900" data-testid={`me-fuel-amount-${tx.id}`}>{tx.montant != null ? chfExact(tx.montant, tx.devise || "CHF") : "—"}</TableCell>
                <TableCell>
                  <ReceiptCell tx={tx} onAttach={() => setAttachTx(tx)}
                    onPreview={() => setPreview({ path: tx.justificatif.path, content_type: tx.justificatif.content_type, original_filename: tx.justificatif.filename })} />
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
      <ReceiptDialog tx={attachTx} onOpenChange={(o) => !o && setAttachTx(null)} />
      <FilePreview open={!!preview} onOpenChange={(o) => !o && setPreview(null)} file={preview} />
    </DriverShell>
  );
}
