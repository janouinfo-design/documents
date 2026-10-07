import { useRef, useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Paperclip, FileX2, Download, Eye, Trash2, Plus, Loader2 } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription, DialogFooter } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Textarea } from "@/components/ui/textarea";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { getFineAttachments, addFineAttachment, removeFineAttachment, attachDocumentFile, fileUrl } from "@/lib/api";
import { PIECE_TYPES, errDetail } from "@/lib/fines";
import { dateFr } from "@/lib/format";

const invalidate = (qc, docId) => { qc.invalidateQueries({ queryKey: ["fine-attachments", docId] }); qc.invalidateQueries({ queryKey: ["fine-history", docId] }); qc.invalidateQueries({ queryKey: ["fines"] }); };

function AddPieceDialog({ docId, open, onOpenChange }) {
  const qc = useQueryClient();
  const [f, setF] = useState({ piece_type: "courrier", titre: "", date_piece: "", note: "" });
  const [file, setFile] = useState(null);
  const [busy, setBusy] = useState(false);
  const set = (k) => (e) => setF((p) => ({ ...p, [k]: e?.target ? e.target.value : e }));
  const submit = async () => {
    setBusy(true);
    try {
      await addFineAttachment(docId, { ...f, file });
      toast.success(file ? `Pièce « ${f.titre} » ajoutée avec fichier` : `Pièce « ${f.titre} » enregistrée sans fichier`);
      invalidate(qc, docId);
      setF({ piece_type: "courrier", titre: "", date_piece: "", note: "" }); setFile(null);
      onOpenChange(false);
    } catch (e) { toast.error(errDetail(e, "Ajout impossible")); } finally { setBusy(false); }
  };
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md" data-testid="fine-attachment-dialog">
        <DialogHeader>
          <DialogTitle className="font-display text-lg">Ajouter une pièce liée</DialogTitle>
          <DialogDescription>Pièce rattachée à l'amende : ni coût ni échéance. Le fichier est optionnel (ex. courrier non scanné) et peut être joint plus tard.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3">
          <div className="space-y-1"><Label className="text-xs text-slate-500">Type *</Label>
            <Select value={f.piece_type} onValueChange={set("piece_type")}>
              <SelectTrigger data-testid="fine-attachment-type"><SelectValue /></SelectTrigger>
              <SelectContent>{PIECE_TYPES.map(([c, l]) => <SelectItem key={c} value={c}>{l}</SelectItem>)}</SelectContent>
            </Select></div>
          <div className="space-y-1"><Label className="text-xs text-slate-500">Titre *</Label>
            <Input value={f.titre} onChange={set("titre")} placeholder="Courrier de l'autorité du 12.06" data-testid="fine-attachment-title" /></div>
          <div className="grid grid-cols-2 gap-3">
            <div className="space-y-1"><Label className="text-xs text-slate-500">Date</Label>
              <Input type="date" value={f.date_piece} onChange={set("date_piece")} data-testid="fine-attachment-date" /></div>
            <div className="space-y-1"><Label className="text-xs text-slate-500">Fichier (optionnel)</Label>
              <Input type="file" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={(e) => setFile(e.target.files?.[0] || null)} data-testid="fine-attachment-file" /></div>
          </div>
          <div className="space-y-1"><Label className="text-xs text-slate-500">Note</Label>
            <Textarea rows={2} value={f.note} onChange={set("note")} data-testid="fine-attachment-note" /></div>
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)} data-testid="fine-attachment-cancel">Annuler</Button>
          <Button onClick={submit} disabled={busy || f.titre.trim().length < 2} className="bg-slate-900 hover:bg-slate-800" data-testid="fine-attachment-submit">
            {busy ? "Enregistrement…" : "Ajouter la pièce"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

function PieceRow({ a, docId, canEdit }) {
  const qc = useQueryClient();
  const inputRef = useRef(null);
  const [busy, setBusy] = useState(false);
  const onPick = async (e) => {
    const file = e.target.files?.[0]; e.target.value = "";
    if (!file) return;
    setBusy(true);
    try { await attachDocumentFile(a.id, file); toast.success(`Fichier joint à « ${a.label} »`); invalidate(qc, docId); }
    catch (err) { toast.error(errDetail(err, "Impossible de joindre le fichier")); } finally { setBusy(false); }
  };
  const remove = async () => {
    try { await removeFineAttachment(docId, a.id); toast.success("Pièce retirée"); invalidate(qc, docId); }
    catch (err) { toast.error(errDetail(err)); }
  };
  return (
    <li className="flex flex-wrap items-center gap-2 rounded-lg border border-slate-200 bg-white px-3 py-2" data-testid={`fine-attachment-${a.id}`}>
      <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-bold uppercase text-slate-600">{a.piece_type_label}</span>
      <span className="min-w-0 flex-1 truncate text-sm font-medium text-slate-800">{a.label}{a.date_piece ? <span className="ml-1 text-xs font-normal text-slate-500">· {dateFr(a.date_piece)}</span> : null}</span>
      {a.file_missing ? (
        <span className="inline-flex items-center gap-1 rounded-full border border-dashed border-amber-400 bg-amber-50 px-2 py-0.5 text-[10px] font-bold text-amber-800" data-testid={`fine-attachment-nofile-${a.id}`}>
          <FileX2 className="h-3 w-3" /> Aucun fichier joint
        </span>
      ) : (
        <span className="flex items-center gap-1">
          <a href={fileUrl(a.storage_path)} target="_blank" rel="noreferrer" title="Aperçu" data-testid={`fine-attachment-preview-${a.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Eye className="h-4 w-4" /></a>
          <a href={fileUrl(a.storage_path, { download: true, filename: a.original_filename })} title="Télécharger" data-testid={`fine-attachment-download-${a.id}`} className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-slate-100 hover:text-slate-700"><Download className="h-4 w-4" /></a>
        </span>
      )}
      {canEdit && a.file_missing && (
        <>
          <input ref={inputRef} type="file" className="hidden" accept=".pdf,.jpg,.jpeg,.png,.webp" onChange={onPick} data-testid={`fine-attachment-file-input-${a.id}`} />
          <button type="button" onClick={() => inputRef.current?.click()} disabled={busy} data-testid={`fine-attachment-attach-${a.id}`}
            className="inline-flex h-8 items-center gap-1 rounded-lg border border-amber-300 bg-white px-2 text-xs font-semibold text-amber-800 hover:bg-amber-50 disabled:opacity-50">
            {busy ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Paperclip className="h-3.5 w-3.5" />} Joindre le fichier
          </button>
        </>
      )}
      {canEdit && (
        <button type="button" onClick={remove} aria-label="Retirer la pièce" data-testid={`fine-attachment-remove-${a.id}`}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 hover:bg-red-50 hover:text-red-600"><Trash2 className="h-4 w-4" /></button>
      )}
      {a.note && <p className="w-full text-xs text-slate-500">{a.note}</p>}
    </li>
  );
}

export default function FineAttachments({ docId, canEdit }) {
  const [addOpen, setAddOpen] = useState(false);
  const { data: rows = [], isLoading } = useQuery({ queryKey: ["fine-attachments", docId], queryFn: () => getFineAttachments(docId), enabled: !!docId });
  return (
    <section className="space-y-2" data-testid="fine-attachments">
      <div className="flex items-center justify-between">
        <h4 className="text-xs font-semibold uppercase tracking-[0.14em] text-slate-500">Pièces liées ({rows.length})</h4>
        {canEdit && <Button size="sm" variant="outline" onClick={() => setAddOpen(true)} className="h-8 gap-1 text-xs" data-testid="fine-attachment-add-btn"><Plus className="h-3.5 w-3.5" /> Ajouter une pièce</Button>}
      </div>
      {!isLoading && rows.length === 0 && <p className="text-xs text-slate-400" data-testid="fine-attachments-empty">Aucune pièce liée.</p>}
      <ul className="space-y-1.5">{rows.map((a) => <PieceRow key={a.id} a={a} docId={docId} canEdit={canEdit} />)}</ul>
      <AddPieceDialog docId={docId} open={addOpen} onOpenChange={setAddOpen} />
    </section>
  );
}
