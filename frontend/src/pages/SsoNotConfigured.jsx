import { ShieldAlert } from "lucide-react";

export default function SsoNotConfigured() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4" data-testid="sso-not-configured">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-8 text-center shadow-sm">
        <ShieldAlert className="mx-auto mb-4 h-10 w-10 text-amber-500" />
        <h1 className="font-display text-xl font-bold text-slate-900">Accès à Documents non configuré</h1>
        <p className="mt-3 text-sm leading-relaxed text-slate-600">
          Votre compte est correctement authentifié, mais aucun espace Documents
          n'est actuellement associé à votre compte.
        </p>
        <p className="mt-2 text-sm text-slate-600">
          Veuillez contacter votre administrateur ou LOGITRAK.
        </p>
        {/* <a> volontaire (full reload) : purge l'état ssoUnconfigured — ne pas remplacer par <Link> */}
        <a href="/login" data-testid="sso-not-configured-login-link"
          className="mt-6 inline-block text-xs font-medium text-slate-600 underline underline-offset-2 hover:text-slate-900">
          Se connecter avec un compte Documents
        </a>
      </div>
    </div>
  );
}
