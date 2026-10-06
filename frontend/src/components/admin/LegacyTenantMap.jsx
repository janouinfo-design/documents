import { useState } from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { toast } from "sonner";
import { Loader2, KeyRound } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { adminLegacyTenantMap, adminLegacyTenantCandidates, adminLegacyTenantConfirm, adminLegacyTenantRevoke } from "@/lib/api";

const STATUS_LABEL = { found: "clé technique trouvée", not_found: "aucun client avec cette clé", ambiguous: "plusieurs clients", no_technical_key: "sans clé technique — non migrable automatiquement" };
const PLACEHOLDER = `[{"legacy_tenant_id":"default","navixy_master_user_id":121349,"name":"ignoré"}]`;

// Correspondance tenant Journal → Documents : clé technique navixy_master_user_id uniquement (D3), confirmation superadmin.
export default function LegacyTenantMap() {
  const qc = useQueryClient();
  const [text, setText] = useState("");
  const [items, setItems] = useState(null);
  const [busy, setBusy] = useState(false);
  const { data, isLoading } = useQuery({ queryKey: ["admin-legacy-tenant-map"], queryFn: adminLegacyTenantMap });
  const refresh = () => qc.invalidateQueries({ queryKey: ["admin-legacy-tenant-map"] });
  const fail = (e) => toast.error(String(e?.response?.data?.detail?.message || e?.response?.data?.detail || "Échec"));

  const analyze = async () => {
    let tenants;
    try { tenants = JSON.parse(text); } catch { return toast.warning("JSON invalide"); }
    setBusy(true);
    try { setItems((await adminLegacyTenantCandidates({ tenants: Array.isArray(tenants) ? tenants : [tenants] })).items); }
    catch (e) { fail(e); } finally { setBusy(false); }
  };
  const confirm = async (it) => {
    setBusy(true);
    try {
      await adminLegacyTenantConfirm({ legacy_tenant_id: it.legacy_tenant_id, tenant_id: it.candidates[0].tenant_id, match_value: it.match_value });
      toast.success("Correspondance tenant confirmée"); setItems(null); setText(""); refresh();
    } catch (e) { fail(e); } finally { setBusy(false); }
  };
  const revoke = async (m) => {
    const reason = window.prompt("Motif de révocation (obligatoire)");
    if (!reason?.trim()) return;
    try { await adminLegacyTenantRevoke({ legacy_source: m.legacy_source, legacy_tenant_id: m.legacy_tenant_id, reason: reason.trim() }); toast.success("Correspondance révoquée"); refresh(); }
    catch (e) { fail(e); }
  };

  return (
    <section className="rounded-2xl border border-slate-200 bg-white p-5" data-testid="legacy-tenant-section">
      <h2 className="flex items-center gap-2 text-base font-semibold text-slate-900 md:text-lg"><KeyRound className="h-5 w-5 text-slate-400" /> Correspondance tenant Journal → Documents</h2>
      <p className="mt-1 text-sm text-slate-500">Clé technique <code>navixy_master_user_id</code> uniquement — jamais par nom, jamais « default » implicite. Clients Documents avec clé : {isLoading ? "…" : (data?.documents_tenants || []).map((t) => `${t.name} (${t.master_user_id})`).join(", ") || "aucun"}.</p>
      <Textarea data-testid="legacy-tenant-input" value={text} onChange={(e) => setText(e.target.value)} placeholder={PLACEHOLDER} rows={3} className="mt-3 font-mono text-xs" />
      <Button data-testid="legacy-tenant-analyze-btn" variant="outline" className="mt-2" disabled={busy} onClick={analyze}>{busy ? <Loader2 className="h-4 w-4 animate-spin" /> : "Analyser (lecture seule)"}</Button>
      {items && (
        <ul className="mt-3 space-y-2 text-sm" data-testid="legacy-tenant-candidates">
          {items.map((it) => (
            <li key={it.legacy_tenant_id} className="flex flex-wrap items-center justify-between gap-2 rounded-lg bg-slate-50 px-3 py-2" data-testid={`legacy-tenant-candidate-${it.legacy_tenant_id}`}>
              <span><span className="font-mono text-xs">{it.legacy_tenant_id}</span> · {STATUS_LABEL[it.status] || it.status}{it.candidates[0] ? ` → ${it.candidates[0].name} (${it.candidates[0].tenant_id})` : ""}{it.existing ? ` · déjà ${it.existing.status}` : ""}</span>
              {it.status === "found" && it.existing?.status !== "confirmed" && (
                <Button size="sm" data-testid={`legacy-tenant-confirm-${it.legacy_tenant_id}`} disabled={busy} onClick={() => confirm(it)} className="bg-slate-900 hover:bg-slate-800">Confirmer (superadmin)</Button>
              )}
            </li>
          ))}
        </ul>
      )}
      <ul className="mt-4 divide-y divide-slate-100 text-sm" data-testid="legacy-tenant-maps">
        {(data?.maps || []).map((m) => (
          <li key={`${m.legacy_source}-${m.legacy_tenant_id}`} className="flex flex-wrap items-center justify-between gap-2 py-2" data-testid={`legacy-tenant-map-row-${m.legacy_tenant_id}`}>
            <span><span className="font-mono text-xs">{m.legacy_source}:{m.legacy_tenant_id}</span> → <strong>{m.tenant_id}</strong> · {m.match_key}={m.match_value} · <span className={m.status === "confirmed" ? "text-emerald-700" : "text-slate-500"}>{m.status}</span>{m.confirmed_by ? ` · ${m.confirmed_by}` : ""}</span>
            {m.status === "confirmed" && <Button size="sm" variant="outline" data-testid={`legacy-tenant-revoke-${m.legacy_tenant_id}`} onClick={() => revoke(m)}>Révoquer</Button>}
          </li>
        ))}
        {!isLoading && !(data?.maps || []).length && <li className="py-2 text-slate-400" data-testid="legacy-tenant-empty">Aucune correspondance tenant confirmée.</li>}
      </ul>
    </section>
  );
}
