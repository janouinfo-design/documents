import { useState } from "react";
import { useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Pencil, Trash2, Check, X, Plus } from "lucide-react";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { createDocCategory, updateDocCategory, deleteDocCategory } from "@/lib/api";

export default function DocCategoriesDialog({ categories = [], open, onOpenChange }) {
  const qc = useQueryClient();
  const [newName, setNewName] = useState("");
  const [editId, setEditId] = useState(null);
  const [edit, setEdit] = useState({ name: "", subs: "" });

  const refresh = () => {
    qc.invalidateQueries({ queryKey: ["doc-categories"] });
    qc.invalidateQueries({ queryKey: ["all-documents"] });
  };
  const fail = (e) => toast.error(e?.response?.data?.detail || "Opération impossible");

  const add = async () => {
    if (!newName.trim()) return;
    try {
      await createDocCategory({ name: newName.trim() });
      toast.success("Catégorie créée");
      setNewName("");
      refresh();
    } catch (e) { fail(e); }
  };

  const startEdit = (c) => {
    setEditId(c.id);
    setEdit({ name: c.name, subs: (c.sub_categories || []).join(", ") });
  };

  const saveEdit = async (c) => {
    try {
      await updateDocCategory(c.id, {
        name: edit.name.trim() || c.name,
        sub_categories: edit.subs.split(",").map((s) => s.trim()).filter(Boolean),
      });
      toast.success("Catégorie mise à jour");
      setEditId(null);
      refresh();
    } catch (e) { fail(e); }
  };

  const remove = async (c) => {
    try {
      await deleteDocCategory(c.id);
      toast.success("Catégorie supprimée");
      refresh();
    } catch (e) { fail(e); }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[85vh] max-w-lg overflow-y-auto" data-testid="doc-categories-dialog">
        <DialogHeader>
          <DialogTitle>Catégories de documents</DialogTitle>
          <DialogDescription>Propres à votre organisation — la suppression exige une catégorie vide.</DialogDescription>
        </DialogHeader>
        <div className="space-y-2">
          {categories.map((c) => (
            <div key={c.id} className="rounded-lg border border-slate-200 px-3 py-2" data-testid={`cat-row-${c.name.replace(/\s/g, "-").toLowerCase()}`}>
              {editId === c.id ? (
                <div className="space-y-2">
                  <Input data-testid="cat-edit-name" value={edit.name} onChange={(e) => setEdit((p) => ({ ...p, name: e.target.value }))} />
                  <Input data-testid="cat-edit-subs" value={edit.subs} onChange={(e) => setEdit((p) => ({ ...p, subs: e.target.value }))} placeholder="Sous-catégories séparées par des virgules" />
                  <div className="flex justify-end gap-2">
                    <Button size="sm" variant="outline" onClick={() => setEditId(null)}><X className="h-3.5 w-3.5" /></Button>
                    <Button size="sm" data-testid="cat-edit-save" onClick={() => saveEdit(c)} className="bg-slate-900 hover:bg-slate-800"><Check className="h-3.5 w-3.5" /></Button>
                  </div>
                </div>
              ) : (
                <div className="flex items-center justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-sm font-semibold text-slate-800">{c.name}</p>
                    {(c.sub_categories || []).length > 0 && (
                      <p className="truncate text-xs text-slate-400">{c.sub_categories.join(" · ")}</p>
                    )}
                  </div>
                  <div className="flex shrink-0 gap-1">
                    <button data-testid={`cat-edit-${c.name.replace(/\s/g, "-").toLowerCase()}`} onClick={() => startEdit(c)} className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-slate-100 hover:text-slate-700" aria-label="Modifier"><Pencil className="h-3.5 w-3.5" /></button>
                    <button data-testid={`cat-delete-${c.name.replace(/\s/g, "-").toLowerCase()}`} onClick={() => remove(c)} className="flex h-7 w-7 items-center justify-center rounded-md text-slate-400 hover:bg-red-50 hover:text-red-600" aria-label="Supprimer"><Trash2 className="h-3.5 w-3.5" /></button>
                  </div>
                </div>
              )}
            </div>
          ))}
        </div>
        <div className="flex gap-2 border-t border-slate-100 pt-3">
          <Input data-testid="cat-new-name" value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Nouvelle catégorie…" onKeyDown={(e) => e.key === "Enter" && add()} />
          <Button data-testid="cat-add-btn" onClick={add} className="gap-1 bg-slate-900 hover:bg-slate-800"><Plus className="h-4 w-4" /> Ajouter</Button>
        </div>
      </DialogContent>
    </Dialog>
  );
}
