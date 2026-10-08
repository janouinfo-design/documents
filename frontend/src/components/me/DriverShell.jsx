import { useQuery } from "@tanstack/react-query";
import { Loader2 } from "lucide-react";
import { getMyProfile } from "@/lib/api";
import DriverPending from "@/components/me/DriverPending";
import QueryErrorState from "@/components/QueryErrorState";

const DRIVER_CODES = ["DRIVER_ACCOUNT_NOT_LINKED", "DRIVER_LINK_INVALID", "DRIVER_INACTIVE", "DRIVER_FORBIDDEN", "NOT_DRIVER"];
export const driverErrorCode = (err) => {
  const code = err?.response?.data?.detail?.code;
  return DRIVER_CODES.includes(code) ? code : null;
};
// Profil relu côté serveur (lien users.driver_id → conducteur actif du tenant) ; jamais mis en cache longtemps : un retrait
// du lien ou une désactivation par l'admin s'applique à la requête suivante, même session.
export const useMyProfile = (opts = {}) =>
  useQuery({ queryKey: ["me", "profile"], queryFn: getMyProfile, retry: false, staleTime: 15000, ...opts });

export default function DriverShell({ title, subtitle, icon: Icon, testId, dataError, isLoading, children }) {
  const profile = useMyProfile();
  const code = driverErrorCode(profile.error) || driverErrorCode(dataError);
  if (code) return <DriverPending code={code} />;
  if (profile.isError) return <QueryErrorState error={profile.error} testId="driver-profile-error" />;
  if (profile.isLoading) {
    return <div className="flex justify-center py-24"><Loader2 className="h-6 w-6 animate-spin text-slate-300" data-testid="driver-loading" /></div>;
  }
  const d = profile.data?.driver;
  return (
    <div className="space-y-6 animate-fade-in" data-testid={testId}>
      <div>
        <p className="text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400" data-testid="driver-identity">
          Espace chauffeur · {d?.display}{d?.matricule_interne ? ` · ${d.matricule_interne}` : ""}
        </p>
        <h2 className="mt-1 flex items-center gap-3 font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">
          {Icon && <Icon className="h-8 w-8 text-slate-400" />}{title}
        </h2>
        {subtitle && <p className="mt-1 text-sm text-slate-500">{subtitle}</p>}
      </div>
      {isLoading ? <div className="flex justify-center py-16"><Loader2 className="h-6 w-6 animate-spin text-slate-300" /></div> : children}
    </div>
  );
}
