import { useState } from "react";
import { toast } from "sonner";
import { Trash2, Loader2 } from "lucide-react";
import {
  AlertDialog, AlertDialogAction, AlertDialogCancel, AlertDialogContent,
  AlertDialogDescription, AlertDialogFooter, AlertDialogHeader, AlertDialogTitle, AlertDialogTrigger,
} from "@/components/ui/alert-dialog";
import { Button } from "@/components/ui/button";
import { deleteVehicle } from "@/lib/api";

export default function DeleteVehicleButton({ vehicle, onDeleted }) {
  const [busy, setBusy] = useState(false);
  const confirm = async () => {
    setBusy(true);
    try {
      const r = await deleteVehicle(vehicle.id);
      toast.success(`Véhicule ${vehicle.plaque} supprimé · ${r.documents_archived ?? 0} document(s) conservé(s) en archive`);
      onDeleted?.();
    } catch (e) {
      toast.error(e?.response?.data?.detail || "Suppression impossible");
    } finally {
      setBusy(false);
    }
  };
  return (
    <AlertDialog>
      <AlertDialogTrigger asChild>
        <Button variant="outline" size="sm" data-testid="vehicle-delete-btn"
                className="gap-1.5 border-red-200 text-red-600 hover:bg-red-50 hover:text-red-700">
          <Trash2 className="h-3.5 w-3.5" /> Supprimer
        </Button>
      </AlertDialogTrigger>
      <AlertDialogContent data-testid="vehicle-delete-dialog">
        <AlertDialogHeader>
          <AlertDialogTitle>Supprimer le véhicule {vehicle.plaque} ?</AlertDialogTitle>
          <AlertDialogDescription>
            Le véhicule sera retiré de la liste. Ses documents ne sont pas détruits : ils sont
            conservés en archive et restent récupérables (par exemple pour le compte qui a repris
            ce véhicule). Cette action ne modifie rien côté Navixy.
          </AlertDialogDescription>
        </AlertDialogHeader>
        <AlertDialogFooter>
          <AlertDialogCancel data-testid="vehicle-delete-cancel">Annuler</AlertDialogCancel>
          <AlertDialogAction data-testid="vehicle-delete-confirm" onClick={confirm} disabled={busy}
                             className="bg-red-600 hover:bg-red-700">
            {busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Supprimer définitivement"}
          </AlertDialogAction>
        </AlertDialogFooter>
      </AlertDialogContent>
    </AlertDialog>
  );
}
