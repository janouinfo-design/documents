import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import {
  Bell, BellRing, AlertTriangle, ShieldAlert, CheckCircle2, RefreshCw, Loader2,
  Mail, MailWarning, ArrowRight, History,
} from "lucide-react";
import { getAlerts, getAlertsLog, runAlerts } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { EVENT_TYPES } from "@/lib/status";
import { cn } from "@/lib/utils";
import KpiCard from "@/components/KpiCard";
import StatusBadge from "@/components/StatusBadge";
import { Button } from "@/components/ui/button";
import { useVehicleDrawer } from "@/context/VehicleDrawerContext";

const STATUS_LABEL = { mocked: "Simulé", sent: "Envoyé", failed: "Échec", skipped: "Ignoré" };
const STATUS_CLS = {
  mocked: "bg-slate-100 text-slate-600",
  sent: "bg-emerald-50 text-emerald-700",
  failed: "bg-red-50 text-red-700",
  skipped: "bg-slate-100 text-slate-500",
};

export default function AlertsPage() {
  const qc = useQueryClient();
  const { openVehicle } = useVehicleDrawer();
  const [running, setRunning] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["alerts"], queryFn: getAlerts });
  const { data: log = [] } = useQuery({ queryKey: ["alerts-log"], queryFn: getAlertsLog });

  const items = data?.items || [];
  const stats = data?.stats || { total: 0, expired: 0, critical: 0, warning: 0 };
  const emailOn = data?.email_enabled;

  const onRun = async () => {
    setRunning(true);
    try {
      const r = await runAlerts();
      toast.success(`Vérification terminée · ${r.created} nouvelle(s) alerte(s)`);
      ["alerts", "alerts-log"].forEach((k) => qc.invalidateQueries({ queryKey: [k] }));
    } catch {
      toast.error("Échec de la vérification");
    } finally {
      setRunning(false);
    }
  };

  return (
    <div className="space-y-6 animate-fade-in" data-testid="alerts-page">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h2 className="font-display text-3xl font-bold tracking-tight text-slate-900 sm:text-4xl">Alertes d'échéances</h2>
          <p className="mt-1 text-sm text-slate-500">Leasing (180/90/30 j) · Assurance (90/60/30 j) · Contrôle technique (90/60/30/7 j)</p>
        </div>
        <Button onClick={onRun} disabled={running} data-testid="alerts-run-btn" className="gap-2 bg-slate-900 hover:bg-slate-800">
          {running ? <Loader2 className="h-4 w-4 animate-spin" /> : <RefreshCw className="h-4 w-4" />}
          Lancer la vérification
        </Button>
      </div>

      {/* Email status banner */}
      <div
        data-testid="email-status-banner"
        className={cn(
          "flex flex-col gap-2 rounded-xl border p-4 sm:flex-row sm:items-center sm:justify-between",
          emailOn ? "border-emerald-200 bg-emerald-50" : "border-amber-200 bg-amber-50"
        )}
      >
        <div className="flex items-start gap-3">
          {emailOn ? <Mail className="mt-0.5 h-5 w-5 text-emerald-600" /> : <MailWarning className="mt-0.5 h-5 w-5 text-amber-600" />}
          <div>
            <p className={cn("text-sm font-semibold", emailOn ? "text-emerald-800" : "text-amber-800")}>
              {emailOn ? `Envoi d'e-mails activé` : "Envoi d'e-mails non configuré — mode démonstration"}
            </p>
            <p className={cn("text-xs", emailOn ? "text-emerald-700" : "text-amber-700")}>
              {emailOn
                ? `Destinataires : ${(data.recipients || []).join(", ")}`
                : "Les alertes sont calculées et journalisées (envoi simulé). Fournissez un fournisseur + clé API + expéditeur pour activer l'envoi réel."}
            </p>
          </div>
        </div>
      </div>

      {/* KPI */}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
        <KpiCard testId="alert-kpi-total" label="Alertes actives" value={isLoading ? "—" : stats.total} accent="slate" icon={BellRing} />
        <KpiCard testId="alert-kpi-expired" label="Échues" value={isLoading ? "—" : stats.expired} accent="red" icon={ShieldAlert} />
        <KpiCard testId="alert-kpi-critical" label="Urgentes (< 30 j)" value={isLoading ? "—" : stats.critical} accent="red" icon={AlertTriangle} />
        <KpiCard testId="alert-kpi-warning" label="À surveiller (< 90 j)" value={isLoading ? "—" : stats.warning} accent="amber" icon={Bell} />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* Active alerts */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm lg:col-span-2" data-testid="active-alerts">
          <div className="border-b border-slate-100 px-6 py-4">
            <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">Alertes actives</h3>
          </div>
          <div className="divide-y divide-slate-100">
            {items.length === 0 && (
              <div className="flex flex-col items-center gap-2 px-6 py-12 text-center">
                <CheckCircle2 className="h-8 w-8 text-emerald-500" />
                <p className="text-sm font-medium text-slate-700">Aucune alerte active</p>
                <p className="text-xs text-slate-400">Toutes les échéances sont à jour.</p>
              </div>
            )}
            {items.map((a, i) => {
              const t = EVENT_TYPES[a.type] || {};
              return (
                <button
                  key={`${a.vehicle_id}-${a.type}-${i}`}
                  onClick={() => openVehicle(a.vehicle_id, a.type)}
                  data-testid={`alert-row-${i}`}
                  className="flex w-full items-center gap-4 px-6 py-3.5 text-left transition-colors hover:bg-slate-50"
                >
                  <span className="h-9 w-1 shrink-0 rounded-full" style={{ backgroundColor: t.color || "#94a3b8" }} />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-semibold text-slate-900">{a.plaque}</span>
                      <span className="truncate text-xs text-slate-400">{a.marque} {a.modele}</span>
                    </div>
                    <p className="text-xs text-slate-500"><span className={cn("font-medium", t.text)}>{a.label}</span> · {dateFr(a.due_date)}</p>
                  </div>
                  <StatusBadge level={a.level} days={a.days_remaining} showDays />
                  <ArrowRight className="h-4 w-4 text-slate-300" />
                </button>
              );
            })}
          </div>
        </div>

        {/* Email log */}
        <div className="rounded-xl border border-slate-200 bg-white shadow-sm" data-testid="alerts-log">
          <div className="flex items-center gap-2 border-b border-slate-100 px-6 py-4">
            <History className="h-4 w-4 text-slate-400" />
            <h3 className="font-display text-lg font-semibold tracking-tight text-slate-900">Journal des envois</h3>
          </div>
          <div className="max-h-[460px] divide-y divide-slate-100 overflow-y-auto">
            {log.length === 0 && <p className="px-6 py-10 text-center text-sm text-slate-400">Aucun envoi pour le moment.</p>}
            {log.map((l) => (
              <div key={l.id} className="px-6 py-3" data-testid={`log-${l.id}`}>
                <div className="flex items-center justify-between gap-2">
                  <span className="flex items-center gap-1.5 text-xs font-semibold text-slate-700">
                    {l.kind === "digest" ? <Mail className="h-3.5 w-3.5 text-slate-400" /> : <BellRing className="h-3.5 w-3.5 text-slate-400" />}
                    {l.kind === "digest" ? "Récapitulatif" : l.label}
                  </span>
                  <span className={cn("rounded-full px-2 py-0.5 text-[10px] font-semibold", STATUS_CLS[l.status] || "bg-slate-100 text-slate-500")}>
                    {STATUS_LABEL[l.status] || l.status}
                  </span>
                </div>
                <p className="mt-1 text-xs text-slate-500">{l.message}</p>
                <p className="mt-0.5 text-[10px] text-slate-400">{dateFr(l.created_at)}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
