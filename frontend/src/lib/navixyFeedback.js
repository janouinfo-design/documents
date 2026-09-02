import { toast } from "sonner";
import { pushVehicleNavixy, retryVehiclePhotoNavixy } from "@/lib/api";

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
      toast.info("Navixy : véhicule non lié à une fiche « Gestion de flotte » Navixy — synchronisation non effectuée (liaison possible depuis la page Intégrité)");
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

// Retour honnête après tentative de synchronisation de la PHOTO véhicule vers Navixy.
export function notifyNavixyPhoto(sync, vehicleId) {
  if (!sync) return;
  switch (sync.status) {
    case "synced":
      toast.success("Photo synchronisée avec la fiche Navixy");
      break;
    case "not_linked":
      toast.info("Photo enregistrée dans LogiTrak — véhicule non lié à une fiche Navixy (liaison possible depuis la page Intégrité)");
      break;
    case "integration_absente":
    case "disabled":
      toast.info("Photo enregistrée dans LogiTrak — synchronisation de photo Navixy non disponible");
      break;
    case "failed":
      toast.error(`Photo enregistrée — synchronisation Navixy échouée${sync.message ? ` (${sync.message})` : ""}`, {
        action: vehicleId ? {
          label: "Réessayer",
          onClick: () =>
            retryVehiclePhotoNavixy(vehicleId)
              .then((r) => notifyNavixyPhoto(r.navixy_photo, vehicleId))
              .catch(() => toast.error("Relance impossible")),
        } : undefined,
      });
      break;
    default:
      break;
  }
}
