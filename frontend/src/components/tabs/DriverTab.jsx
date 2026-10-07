import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { UserRound, UserPlus } from "lucide-react";
import { getVehicleAssignments, getDriverAt } from "@/lib/api";
import { SectionCard } from "@/components/Field";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import AssignmentDialog from "@/components/drivers/AssignmentDialog";
import AssignmentHistory from "@/components/drivers/AssignmentHistory";

// Onglet « Conducteur » du drawer véhicule : conducteur du jour (lecture, par affectation datée) + historique.
export default function DriverTab({ vehicle }) {
  const { user } = useAuth();
  const readOnly = user?.role === "read_only";
  const [open, setOpen] = useState(false);
  const { data: rows = [] } = useQuery({ queryKey: ["assignments", vehicle.id], queryFn: () => getVehicleAssignments(vehicle.id) });
  const { data: at } = useQuery({ queryKey: ["driver-at", vehicle.id], queryFn: () => getDriverAt(vehicle.id) });

  return (
    <div className="space-y-4" data-testid="driver-tab">
      <SectionCard title="Conducteur actuel" description="Résolu par affectation datée uniquement — jamais par nom, plaque ou tracker."
        action={!readOnly && (
          <Button size="sm" data-testid="assign-driver-btn" onClick={() => setOpen(true)} className="gap-1.5 bg-slate-900 hover:bg-slate-800">
            <UserPlus className="h-4 w-4" /> Affecter un conducteur
          </Button>
        )}>
        <div className="flex items-center gap-3" data-testid="driver-current">
          <span className="flex h-10 w-10 items-center justify-center rounded-full bg-slate-100 text-slate-500"><UserRound className="h-5 w-5" /></span>
          <div>
            <p className="text-sm font-semibold text-slate-800" data-testid="driver-current-name">
              {at?.driver ? at.driver.driver_nom : at?.ambiguous ? "Ambigu — plusieurs affectations principales" : "Aucun conducteur affecté aujourd'hui"}
            </p>
            <p className="text-xs text-slate-500">
              {at?.driver ? `Principal depuis le ${at.driver.valid_from}` : `${at?.candidates?.length || 0} affectation(s) couvrant le ${at?.date || "jour"}`}
              {(at?.candidates || []).filter((c) => !c.principal).length > 0 && ` · secondaires : ${at.candidates.filter((c) => !c.principal).map((c) => c.driver_nom).join(", ")}`}
            </p>
          </div>
        </div>
      </SectionCard>
      <SectionCard title="Historique des affectations" description={`${rows.length} période(s) — ${vehicle.responsable ? `responsable (texte libre) : ${vehicle.responsable}` : "aucun responsable texte"}`}>
        <AssignmentHistory rows={rows} readOnly={readOnly} />
      </SectionCard>
      <AssignmentDialog open={open} onOpenChange={setOpen} vehicle={vehicle} />
    </div>
  );
}
