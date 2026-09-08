import { useQuery } from "@tanstack/react-query";
import { ArrowRight, Send } from "lucide-react";
import { adminListTransfers } from "@/lib/api";
import { dateFr } from "@/lib/format";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";

export default function TransfersHistory() {
  const { data: rows = [], isLoading } = useQuery({
    queryKey: ["admin-transfers"],
    queryFn: adminListTransfers,
  });
  if (isLoading || rows.length === 0) return null;
  return (
    <div className="space-y-3" data-testid="admin-transfers-section">
      <h2 className="flex items-center gap-2 font-display text-lg font-bold text-slate-900">
        <Send className="h-4 w-4 text-slate-400" /> Transferts de documents entre clients
      </h2>
      <div className="overflow-hidden rounded-2xl border border-slate-200 bg-white">
        <Table>
          <TableHeader>
            <TableRow className="bg-slate-50">
              <TableHead>Date</TableHead>
              <TableHead>Par</TableHead>
              <TableHead>Source</TableHead>
              <TableHead />
              <TableHead>Destination</TableHead>
              <TableHead className="text-right">Documents</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id} data-testid={`transfer-row-${r.id}`}>
                <TableCell className="text-sm text-slate-600">{dateFr(r.at)}</TableCell>
                <TableCell className="text-sm text-slate-600">{r.by || "—"}</TableCell>
                <TableCell>
                  <p className="text-sm font-semibold text-slate-800">{r.source_plaque || "—"}</p>
                  <p className="text-xs text-slate-400">{r.source_tenant_name}</p>
                </TableCell>
                <TableCell><ArrowRight className="h-4 w-4 text-slate-300" /></TableCell>
                <TableCell>
                  <p className="text-sm font-semibold text-slate-800">{r.target_plaque || "—"}</p>
                  <p className="text-xs text-slate-400">{r.target_tenant_name}</p>
                </TableCell>
                <TableCell className="text-right">
                  <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-semibold text-slate-600">{r.documents}</span>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}
