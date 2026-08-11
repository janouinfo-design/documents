import { useState } from "react";
import { Camera, FolderUp } from "lucide-react";
import { Button } from "@/components/ui/button";
import { SectionCard } from "@/components/Field";
import ScanDocumentDialog, { DOC_TYPE_OPTIONS } from "@/components/ScanDocumentDialog";

export default function DocumentScanCard({ vehicle, docType, title, description, onValidated, testIdPrefix = "scan-card" }) {
  const [open, setOpen] = useState(false);
  const [mode, setMode] = useState("import");
  const label = DOC_TYPE_OPTIONS.find((t) => t.key === docType)?.label;
  const openWith = (m) => { setMode(m); setOpen(true); };

  return (
    <SectionCard
      title={title || `Scan intelligent — ${label || "Document"}`}
      description={description || "Photographiez ou importez le document : les données sont extraites puis soumises à votre validation avant tout enregistrement."}
      testId={`${testIdPrefix}-card`}
    >
      <div className="flex flex-col gap-2 sm:flex-row">
        <Button data-testid={`${testIdPrefix}-camera`} onClick={() => openWith("camera")} className="gap-2 bg-slate-900 hover:bg-slate-800">
          <Camera className="h-4 w-4" /> Prendre une photo
        </Button>
        <Button data-testid={`${testIdPrefix}-import`} variant="outline" onClick={() => openWith("import")} className="gap-2">
          <FolderUp className="h-4 w-4" /> Importer un fichier
        </Button>
      </div>
      <ScanDocumentDialog
        open={open}
        onOpenChange={setOpen}
        vehicle={vehicle}
        initialMode={mode}
        forcedType={docType}
        onValidated={onValidated}
      />
    </SectionCard>
  );
}
