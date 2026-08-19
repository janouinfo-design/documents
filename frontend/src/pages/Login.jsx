import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Layers3, Loader2, Lock, Mail } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useAuth } from "@/context/AuthContext";

function formatApiErrorDetail(detail) {
  if (detail == null) return "Une erreur est survenue. Réessayez.";
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail))
    return detail.map((e) => (e && typeof e.msg === "string" ? e.msg : JSON.stringify(e))).filter(Boolean).join(" ");
  if (detail && typeof detail.msg === "string") return detail.msg;
  return String(detail);
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      await login(email, password);
      navigate("/", { replace: true });
    } catch (err) {
      setError(formatApiErrorDetail(err?.response?.data?.detail) || "Connexion impossible");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="flex min-h-screen items-center justify-center bg-slate-50 px-4">
      <div className="w-full max-w-md">
        <div className="mb-8 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-slate-900 text-white">
            <Layers3 className="h-6 w-6" />
          </div>
          <div className="leading-tight">
            <p className="font-display text-xl font-extrabold tracking-tight text-slate-900">LogiTrak</p>
            <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Fleet Admin</p>
          </div>
        </div>

        <div className="rounded-2xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="font-display text-lg font-bold text-slate-900">Connexion</h1>
          <p className="mt-1 text-sm text-slate-500">Accès réservé — identifiez-vous pour continuer.</p>

          <form onSubmit={submit} className="mt-6 space-y-4">
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-400">Email</label>
              <div className="relative">
                <Mail className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  data-testid="login-email-input"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="admin@logitrak.ch"
                  className="pl-9"
                />
              </div>
            </div>
            <div>
              <label className="mb-1.5 block text-xs font-semibold uppercase tracking-wide text-slate-400">Mot de passe</label>
              <div className="relative">
                <Lock className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
                <Input
                  data-testid="login-password-input"
                  type="password"
                  autoComplete="current-password"
                  required
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  placeholder="••••••••••"
                  className="pl-9"
                />
              </div>
            </div>

            {error && (
              <p data-testid="login-error" className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700">
                {error}
              </p>
            )}

            <Button
              data-testid="login-submit-btn"
              type="submit"
              disabled={loading}
              className="w-full gap-2 bg-slate-900 hover:bg-slate-800"
            >
              {loading && <Loader2 className="h-4 w-4 animate-spin" />}
              Se connecter
            </Button>
          </form>
        </div>

        <div className="mt-4 rounded-2xl border border-slate-200 bg-white p-5" data-testid="demo-accounts">
          <p className="text-[10px] font-semibold uppercase tracking-[0.18em] text-slate-400">Comptes démo</p>
          <div className="mt-3">
            <button
              type="button"
              data-testid="demo-admin-btn"
              onClick={() => {
                setEmail("admin@logitrak.ch");
                setPassword("LT-OSTR72MutpBKWB!");
                setError("");
              }}
              className="rounded-lg border border-slate-300 px-6 py-2 text-sm font-semibold text-slate-900 transition-colors hover:bg-slate-50"
            >
              Admin
            </button>
          </div>
        </div>

        <p className="mt-6 text-center text-xs text-slate-400">
          Gestion administrative de flotte · session de 24 heures
        </p>
      </div>
    </div>
  );
}
