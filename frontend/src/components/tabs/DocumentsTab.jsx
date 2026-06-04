import { FileText, ShieldCheck, ScrollText, ClipboardCheck, Receipt, Images, FileSignature, FolderArchive } from "lucide-react";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { SectionCard } from "@/components/Field";
import DocFolderSection from "@/components/DocFolderSection";

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

  return (
    <SectionCard
      title="Arborescence des documents"
      description="Organisez tous les fichiers du véhicule par dossier · PDF, JPG, PNG, DOCX, XLSX, ZIP"
      testId="documents-tab"
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
  );
}
