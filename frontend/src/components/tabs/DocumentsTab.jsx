import { useState } from "react";
import {
  FileText, ShieldCheck, ScrollText, ClipboardCheck, Receipt, Images,
  FileSignature, FolderArchive, Plus, Camera, FolderUp, PenLine,
} from "lucide-react";
import { toast } from "sonner";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { DropdownMenu, DropdownMenuTrigger, DropdownMenuContent, DropdownMenuItem } from "@/components/ui/dropdown-menu";
import { Select, SelectTrigger, SelectContent, SelectItem, SelectValue } from "@/components/ui/select";
import { Button } from "@/components/ui/button";
import { uploadDocument } from "@/lib/api";
import { SectionCard } from "@/components/Field";
import DocFolderSection from "@/components/DocFolderSection";
import DropZone from "@/components/DropZone";
import ScanDocumentDialog from "@/components/ScanDocumentDialog";

const FOLDERS = [
  { name: "Leasing", icon: FileText },
  { name: "Assurance", icon: ShieldCheck },
  { name: "Carte grise", icon: ScrollText },
  { name: "Contrôle technique", icon: ClipboardCheck },
  { name: "Factures", icon: Receipt },
  { name: "États des lieux", icon: Images },
  { name: "Contrats", icon: FileSignature },
  { name: "Divers", icon: FolderArchive },
];

export default function DocumentsTab({ vehicle, onSaved, docs, refetchDocs }) {
  const count = (folder) => docs.filter((d) => d.folder === folder).length;
  const onChange = () => { refetchDocs?.(); onSaved?.(); };

  const [scanOpen, setScanOpen] = useState(false);
  const [scanMode, setScanMode] = useState("import");
  const [manualOpen, setManualOpen] = useState(false);
  const [manualFolder, setManualFolder] = useState("Divers");
  const [manualBusy, setManualBusy] = useState(false);

  const openScan = (mode) => { setScanMode(mode); setScanOpen(true); };

  const manualUpload = async (files) => {
    setManualBusy(true);
    try {
      for (const f of files) await uploadDocument(vehicle.id, f, manualFolder);
      toast.success(`${files.length} fichier(s) ajouté(s) · ${manualFolder}`);
      setManualOpen(false);
      onChange();
    } catch {
      toast.error("Échec du téléversement");
    } finally {
      setManualBusy(false);
    }
  };

  return (
    <>
      <SectionCard
        title="Arborescence des documents"
        description="Organisez tous les fichiers du véhicule par dossier · PDF, JPG, PNG, DOCX, XLSX, ZIP"
        testId="documents-tab"
        action={
          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button data-testid="add-document-btn" size="sm" className="gap-1.5 bg-slate-900 hover:bg-slate-800">
                <Plus className="h-4 w-4" /> Ajouter un document
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end" className="w-64">
              <DropdownMenuItem data-testid="add-doc-scan" onClick={() => openScan("camera")} className="gap-2.5 py-2.5">
                <Camera className="h-4 w-4 text-slate-500" /> Scanner / prendre une photo
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="add-doc-import" onClick={() => openScan("import")} className="gap-2.5 py-2.5">
                <FolderUp className="h-4 w-4 text-slate-500" /> Importer PDF ou image
              </DropdownMenuItem>
              <DropdownMenuItem data-testid="add-doc-manual" onClick={() => setManualOpen(true)} className="gap-2.5 py-2.5">
                <PenLine className="h-4 w-4 text-slate-500" /> Ajouter manuellement
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        }
      >
        <Accordion type="multiple" defaultValue={["Leasing"]} className="space-y-2">
          {FOLDERS.map(({ name, icon: Icon }) => (
            <AccordionItem key={name} value={name} className="overflow-hidden rounded-xl border border-slate-200 bg-white px-0">
              <AccordionTrigger className="px-4 py-3 hover:no-underline" data-testid={`folder-${name.replace(/\s/g, "-").toLowerCase()}`}>
                <div className="flex flex-1 items-center justify-between pr-3">
                  <span className="flex items-center gap-2.5 text-sm font-semibold text-slate-800">
                    <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-slate-100 text-slate-600"><Icon className="h-4 w-4" /></span>
                    {name}
                  </span>
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-500">{count(name)}</span>
                </div>
              </AccordionTrigger>
              <AccordionContent className="border-t border-slate-100 px-4 py-4">
                <DocFolderSection vehicleId={vehicle.id} folder={name} docs={docs} onChange={onChange} compact />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </SectionCard>

      <ScanDocumentDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        vehicle={vehicle}
        initialMode={scanMode}
        onValidated={onChange}
      />

      <Dialog open={manualOpen} onOpenChange={setManualOpen}>
        <DialogContent className="max-w-md" data-testid="manual-add-dialog">
          <DialogHeader>
            <DialogTitle className="font-display">Ajouter manuellement</DialogTitle>
            <DialogDescription>Choisissez un dossier puis déposez le fichier — sans analyse automatique.</DialogDescription>
          </DialogHeader>
          <Select value={manualFolder} onValueChange={setManualFolder}>
            <SelectTrigger data-testid="manual-folder-select"><SelectValue /></SelectTrigger>
            <SelectContent>
              {FOLDERS.map(({ name }) => <SelectItem key={name} value={name}>{name}</SelectItem>)}
            </SelectContent>
          </Select>
          <DropZone
            onFiles={manualUpload}
            busy={manualBusy}
            testId="manual-dropzone"
            accept=".pdf,.jpg,.jpeg,.png,.webp,.docx,.doc,.xlsx,.xls,.zip,.csv"
          />
        </DialogContent>
      </Dialog>
    </>
  );
}
