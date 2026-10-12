import { Navigate } from "react-router-dom";
import { Wrench, Send, GitMerge } from "lucide-react";
import { useAuth } from "@/context/AuthContext";
import TransfersHistory from "@/components/admin/TransfersHistory";
import LegacyTenantMap from "@/components/admin/LegacyTenantMap";

// Outils techniques Super Admin : traçabilité des transferts et préparation migration Journal → Documents.
export default function AdminToolsPage() {
  const { user } = useAuth();
  if (user && user.role !== "superadmin") return <Navigate to="/" replace />;
  return (
    <div className="space-y-8" data-testid="admin-tools-page">
      <div>
        <h1 className="flex items-center gap-3 font-display text-2xl font-extrabold tracking-tight text-slate-900 sm:text-3xl">
          <Wrench className="h-7 w-7 text-slate-400" /> Outils techniques
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Section secondaire réservée au Super Admin : traçabilité des imports / transferts et correspondances de migration. Lecture seule sauf mention contraire.
        </p>
      </div>
      <section className="space-y-3" data-testid="admin-tools-transfers">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
          <Send className="h-4 w-4" /> Historique des transferts
        </h2>
        <TransfersHistory emptyState />
      </section>
      <section className="space-y-3" data-testid="admin-tools-migration">
        <h2 className="flex items-center gap-2 text-sm font-semibold uppercase tracking-wide text-slate-400">
          <GitMerge className="h-4 w-4" /> Migration Journal → Documents
        </h2>
        <LegacyTenantMap />
      </section>
    </div>
  );
}
