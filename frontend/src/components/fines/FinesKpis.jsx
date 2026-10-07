import { Gavel, AlertTriangle, CalendarClock, CheckCircle2, Ban, Scale } from "lucide-react";
import KpiCard from "@/components/KpiCard";
import { chfExact } from "@/lib/format";

// KPI synthétiques — même source que la liste (/api/fines/stats), D9 : annulées jamais dans les montants comptés.
export default function FinesKpis({ stats, onPick, active }) {
  const c = stats?.counts, m = stats?.montants;
  const v = (n) => (c ? n : "—");
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6" data-testid="fines-kpis">
      <KpiCard testId="fines-kpi-ouvertes" label="Ouvertes" value={v(c?.ouvertes)} accent="slate" icon={Gavel}
        sub={m ? `${chfExact(m.ouvert_chf)} à encaisser` : ""} onClick={() => onPick("open")} active={active === "open"} />
      <KpiCard testId="fines-kpi-en-retard" label="En retard" value={v(c?.en_retard)} accent="red" icon={AlertTriangle}
        sub={m ? chfExact(m.en_retard_chf) : ""} onClick={() => onPick("late")} active={active === "late"} />
      <KpiCard testId="fines-kpi-bientot" label={`À payer ≤ ${stats?.urgent_days ?? 30} j`} value={v(c?.a_payer_bientot)} accent="amber" icon={CalendarClock}
        sub={m ? chfExact(m.a_payer_bientot_chf) : ""} onClick={() => onPick("soon")} active={active === "soon"} />
      <KpiCard testId="fines-kpi-contestees" label="Contestées" value={v(c?.contestees)} accent="indigo" icon={Scale}
        onClick={() => onPick("contestee")} active={active === "contestee"} />
      <KpiCard testId="fines-kpi-payees" label="Payées" value={v(c?.payees)} accent="emerald" icon={CheckCircle2}
        sub={m ? `${chfExact(m.paye_chf)}${c?.refacturees ? ` · ${c.refacturees} refacturée(s)` : ""}` : ""} onClick={() => onPick("paid")} active={active === "paid"} />
      <KpiCard testId="fines-kpi-annulees" label="Annulées" value={v(c?.annulees)} accent="slate" icon={Ban}
        sub={m ? `${chfExact(m.annule_chf)} hors coûts (D9)` : ""} onClick={() => onPick("annulee")} active={active === "annulee"} />
    </div>
  );
}
