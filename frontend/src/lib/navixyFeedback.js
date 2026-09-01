import { toast } from "sonner";
import { pushVehicleNavixy } from "@/lib/api";

// Retour utilisateur honnête après une tentative de synchronisation LOGITRAK → Navixy.
export function notifyNavixyPush(push, vehicleId) {
  if (!push) return;
  switch (push.status) {
    case "pushed":
      toast.success(`Navixy : ${push.fields?.length ?? 0} champ(s) synchronisé(s) (${(push.fields || []).join(", ")})`);
      break;
    case "in_sync":
      toast.info("Navixy : véhicule déjà à jour");
      break;
    case "not_linked":
      toast.info("Navixy : véhicule non lié à un tracker — synchronisation non effectuée");
      break;
    case "integration_absente":
    case "disabled":
      break; // pas d'intégration télématique : rien à signaler
    case "error":
      toast.error("Navixy : synchronisation en échec — les données LOGITRAK sont bien enregistrées", {
        action: vehicleId ? {
          label: "Relancer",
          onClick: () =>
            pushVehicleNavixy(vehicleId)
              .then((r) => notifyNavixyPush({ ...r.navixy_push, status: r.navixy_push?.status === "error" ? "error" : r.navixy_push?.status }, vehicleId))
              .catch(() => toast.error("Navixy : relance impossible")),
        } : undefined,
      });
      break;
    default:
      break;
  }
}
