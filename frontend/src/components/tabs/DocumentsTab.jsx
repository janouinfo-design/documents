import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  FileText, ShieldCheck, ScrollText, ClipboardCheck, Receipt, Images,
  FileSignature, FolderArchive, Plus, Search, Ticket,
} from "lucide-react";
import { Accordion, AccordionItem, AccordionTrigger, AccordionContent } from "@/components/ui/accordion";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { SectionCard } from "@/components/Field";
import DocFolderSection from "@/components/DocFolderSection";
import ScanDocumentDialog from "@/components/ScanDocumentDialog";
import { getDocCategories } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";

const FOLDER_ICONS = {
  Leasing: FileText, Assurance: ShieldCheck, "Carte grise": ScrollText,
  "Contrôle technique": ClipboardCheck, Vignette: Ticket, Factures: Receipt,
  "États des lieux": Images, Contrats: FileSignature, Divers: FolderArchive,
};

export default function DocumentsTab({ vehicle, onSaved, docs, refetchDocs }) {
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const [scanOpen, setScanOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [openFolders, setOpenFolders] = useState(["Leasing"]);
  const onChange = () => { refetchDocs?.(); onSaved?.(); };
  const { data: categories = [] } = useQuery({ queryKey: ["doc-categories"], queryFn: getDocCategories });
  const folders = categories.map((c) => ({ name: c.name, icon: FOLDER_ICONS[c.name] || FolderArchive }));

  useEffect(() => {
    if (search.trim()) setOpenFolders(folders.map((f) => f.name));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [search]);

  const term = search.trim().toLowerCase();
  const visibleDocs = term
    ? docs.filter((d) => (d.original_filename || "").toLowerCase().includes(term))
    : docs;
  const count = (folder) => visibleDocs.filter((d) => d.folder === folder).length;

  return (
    <>
      <SectionCard
        title="Bibliothèque des documents"
        description="Tous les documents du véhicule, y compris ceux ajoutés depuis Carte grise, Assurance ou Leasing · Chaque dossier accepte aussi le dépôt manuel de fichiers"
        testId="documents-tab"
        action={
          readOnly ? null : (
            <Button data-testid="add-document-btn" size="sm" onClick={() => setScanOpen(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800">
              <Plus className="h-4 w-4" /> Ajouter un document
            </Button>
          )
        }
      >
        <div className="relative mb-4">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            data-testid="doc-search-input"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Rechercher un document par nom…"
            className="pl-9"
          />
        </div>
        <Accordion type="multiple" value={openFolders} onValueChange={setOpenFolders} className="space-y-2">
          {folders.map(({ name, icon: Icon }) => (
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
                <DocFolderSection vehicleId={vehicle.id} folder={name} docs={visibleDocs} onChange={onChange} compact />
              </AccordionContent>
            </AccordionItem>
          ))}
        </Accordion>
      </SectionCard>

      <ScanDocumentDialog
        open={scanOpen}
        onOpenChange={setScanOpen}
        vehicle={vehicle}
        askType
        onValidated={onChange}
      />
    </>
  );
}
