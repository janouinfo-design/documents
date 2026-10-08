import { Lock, AlertTriangle } from "lucide-react";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import Pill from "@/components/energy/Pill";
import { MATCH_META } from "@/lib/fuelImport";
import { BLOCKER_META, na } from "@/lib/fuelStatements";
import { chfExact, dateFr } from "@/lib/format";

// G. Lignes du snapshot : transactions Documents incluses, verrou, anomalies, blockers[] — clic → fiche transaction
export default function StatementLines({ st, onOpenTransaction }) {
  const lines = st.lines || [];
  return (
    <section className="space-y-2" data-testid="fuel-statement-lines-section">
      <h3 className="font-display text-sm font-bold uppercase tracking-wide text-slate-500">G. Lignes du snapshot ({lines.length})</h3>
      <div className="overflow-x-auto rounded-lg border border-slate-200">
        <Table data-testid="fuel-statement-lines-table">
          <TableHeader><TableRow className="bg-slate-50">
            <TableHead>Date</TableHead><TableHead>Véhicule</TableHead><TableHead>Fournisseur / station</TableHead><TableHead className="text-right">Montant</TableHead><TableHead className="text-right">CHF</TableHead>
            <TableHead className="text-right">L / kWh</TableHead><TableHead>Rattachement</TableHead><TableHead>Blockers</TableHead><TableHead>Verrou</TableHead>
          </TableRow></TableHeader>
          <TableBody>
            {lines.length === 0 && <TableRow><TableCell colSpan={9}><p className="py-6 text-center text-xs text-slate-400" data-testid="fuel-statement-lines-empty">Aucune transaction éligible dans ce snapshot.</p></TableCell></TableRow>}
            {lines.map((ln) => (
              <TableRow key={ln.transaction_id} data-testid={`fuel-statement-line-${ln.transaction_id}`} onClick={() => onOpenTransaction?.(ln.transaction_id)} className={`cursor-pointer hover:bg-slate-50 ${ln.blockers?.length ? "bg-rose-50/40" : ""}`}>
                <TableCell className="whitespace-nowrap text-xs text-slate-700">{dateFr(ln.date)}{ln.heure ? ` ${ln.heure}` : ""}{ln.late && <span className="ml-1 rounded bg-violet-100 px-1 text-[10px] font-bold text-violet-800" data-testid={`fuel-statement-line-late-${ln.transaction_id}`}>tardive</span>}</TableCell>
                <TableCell className="text-xs font-semibold text-slate-800">{ln.plaque || ln.vehicle_id || "—"}</TableCell>
                <TableCell className="text-xs text-slate-600">{[ln.fournisseur, ln.station].filter(Boolean).join(" · ") || "—"}{ln.carte_last4 ? <span className="ml-1 font-mono text-[10px] text-slate-400">••••{ln.carte_last4}</span> : null}</TableCell>
                <TableCell className="text-right text-xs font-semibold text-slate-900">{ln.montant != null ? chfExact(ln.montant, ln.devise || "CHF") : "—"}</TableCell>
                <TableCell className="text-right text-xs text-slate-700">{ln.montant_chf != null ? chfExact(ln.montant_chf) : <span className="text-amber-700">FX en attente</span>}</TableCell>
                <TableCell className="text-right text-xs text-slate-600">{ln.litres != null ? na(ln.litres, " L") : ln.kwh != null ? na(ln.kwh, " kWh") : "—"}</TableCell>
                <TableCell>{ln.match_status ? <Pill map={MATCH_META} code={ln.match_status} /> : <span className="text-[10px] text-slate-400">document</span>}</TableCell>
                <TableCell data-testid={`fuel-statement-blocked-line-${ln.transaction_id}`}>
                  {ln.blockers?.length ? <div className="flex flex-wrap gap-1">{ln.blockers.map((b) => <Pill key={b} map={BLOCKER_META} code={b} />)}</div> : <span className="text-[10px] text-slate-300">—</span>}
                  {ln.open_anomalies > 0 && <span className="ml-1 inline-flex items-center gap-0.5 text-[10px] text-rose-700"><AlertTriangle className="h-3 w-3" /> {ln.open_anomalies}</span>}
                </TableCell>
                <TableCell>{(ln.locked || st.status === "cloture") ? <span className="inline-flex items-center gap-1 rounded-full bg-slate-900 px-2 py-0.5 text-[10px] font-bold text-white" title={`Incluse dans le décompte clôturé ${st.number}`} data-testid={`fuel-statement-line-locked-${ln.transaction_id}`}><Lock className="h-2.5 w-2.5" /> Verrouillée</span> : <span className="text-[10px] text-slate-400">brouillon</span>}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </section>
  );
}
