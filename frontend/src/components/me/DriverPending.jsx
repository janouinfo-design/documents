import { Clock, ShieldAlert, UserX } from "lucide-react";
import { Button } from "@/components/ui/button";
import { useAuth } from "@/context/AuthContext";
import { cn } from "@/lib/utils";

const TONES = { slate: "bg-slate-100 text-slate-700", amber: "bg-amber-50 text-amber-700", red: "bg-red-50 text-red-700" };

const VARIANTS = {
  DRIVER_ACCOUNT_NOT_LINKED: {
    testId: "driver-pending-page", icon: Clock, tone: "slate", title: "Compte chauffeur en attente",
    text: "Votre compte n'est pas encore relié à un profil conducteur. Vos vues Mes pleins, Mes amendes et Mes véhicules seront disponibles dès que l'administrateur aura effectué la liaison.",
  },
  DRIVER_LINK_INVALID: {
    testId: "driver-pending-page", icon: ShieldAlert, tone: "red", title: "Compte chauffeur en attente",
    text: "La liaison entre votre compte et un profil conducteur n'est plus valide. Aucune donnée ne peut être affichée tant qu'elle n'a pas été rétablie.",
  },
  DRIVER_INACTIVE: {
    testId: "driver-inactive-page", icon: UserX, tone: "amber", title: "Profil conducteur inactif",
    text: "Votre profil conducteur a été désactivé par l'administrateur de votre entreprise. Vos pleins, amendes et véhicules ne sont plus consultables tant que le profil n'est pas réactivé.",
  },
};

// Page d'attente chauffeur : aucune donnée flotte, aucune navigation métier, aucun fallback — le serveur a refusé (403 codé).
export default function DriverPending({ code }) {
  const { user, logout } = useAuth();
  const v = VARIANTS[code] || VARIANTS.DRIVER_ACCOUNT_NOT_LINKED;
  const Icon = v.icon;
  return (
    <div className="mx-auto max-w-xl py-10 animate-fade-in sm:py-16" data-testid={v.testId}>
      <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm sm:p-10">
        <div className={cn("flex h-14 w-14 items-center justify-center rounded-xl", TONES[v.tone])}><Icon className="h-7 w-7" /></div>
        <p className="mt-6 text-[11px] font-semibold uppercase tracking-[0.18em] text-slate-400">Espace chauffeur</p>
        <h2 className="mt-2 font-display text-3xl font-bold tracking-tight text-slate-900" data-testid="driver-pending-title">{v.title}</h2>
        <p className="mt-3 text-sm leading-relaxed text-slate-600" data-testid="driver-pending-text">{v.text}</p>
        <p className="mt-4 rounded-lg bg-slate-50 px-4 py-3 text-sm font-medium text-slate-700" data-testid="driver-pending-contact">
          Contactez l'administrateur de votre flotte pour activer votre accès.
        </p>
        <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
          <span className="font-mono text-[11px] text-slate-400" data-testid="driver-pending-code">{code} · {user?.email}</span>
          <Button variant="outline" size="sm" onClick={logout} data-testid="driver-pending-logout">Se déconnecter</Button>
        </div>
      </div>
    </div>
  );
}
