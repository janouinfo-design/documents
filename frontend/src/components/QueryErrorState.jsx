import { AlertTriangle } from "lucide-react";

export default function QueryErrorState({ error, testId = "query-error" }) {
  const status = error?.response?.status;
  const detail = error?.response?.data?.detail;
  const msg = typeof detail === "string"
    ? detail
    : status === 403
      ? "Accès non autorisé — module désactivé ou droits insuffisants. Contactez votre administrateur."
      : "Impossible de charger les données. Vérifiez votre connexion puis réessayez.";
  return (
    <div data-testid={testId}
      className="flex items-start gap-3 rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
      <AlertTriangle className="mt-0.5 h-5 w-5 shrink-0" />
      <p>{msg}</p>
    </div>
  );
}
