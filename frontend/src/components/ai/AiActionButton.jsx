import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Sparkles, Loader2, Copy, Check, Download } from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription,
} from "@/components/ui/dialog";
import { aiStatus } from "@/lib/api";
import { useAuth } from "@/context/AuthContext";
import { can } from "@/lib/rbac";
import { cn } from "@/lib/utils";

export function useAiAvailable() {
  const { user } = useAuth();
  const allowed = can(user, "ai.use");
  const { data } = useQuery({
    queryKey: ["ai-status"],
    queryFn: aiStatus,
    enabled: allowed,
    staleTime: 5 * 60 * 1000,
  });
  return allowed && !!data?.available;
}

export default function AiActionButton({
  label = "Assistant IA", title = "Assistant IA", testId,
  run, downloadName, iconOnly = false, size = "sm", variant = "outline", className,
}) {
  const available = useAiAvailable();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [text, setText] = useState("");
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  if (!available) return null;

  const go = async () => {
    setOpen(true); setLoading(true); setError(""); setText(""); setCopied(false);
    try {
      const d = await run();
      setText(d?.text || "");
    } catch (e) {
      setError(e?.response?.data?.detail || "Échec de la génération. Veuillez réessayer.");
    } finally {
      setLoading(false);
    }
  };

  const copy = async () => {
    try { await navigator.clipboard.writeText(text); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { /* noop */ }
  };

  const download = () => {
    const blob = new Blob([text], { type: "text/plain;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url; a.download = downloadName || "assistant-ia.txt"; a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <>
      {iconOnly ? (
        <button
          type="button" onClick={go} data-testid={testId} title={title} aria-label={title}
          className="flex h-8 w-8 items-center justify-center rounded-lg text-slate-400 transition-colors hover:bg-indigo-50 hover:text-indigo-600"
        >
          <Sparkles className="h-4 w-4" />
        </button>
      ) : (
        <Button variant={variant} size={size} onClick={go} data-testid={testId} className={cn("gap-1.5", className)}>
          <Sparkles className="h-4 w-4 text-indigo-500" /> {label}
        </Button>
      )}

      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="max-w-2xl" data-testid="ai-result-dialog">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2 text-base">
              <Sparkles className="h-4 w-4 text-indigo-500" /> {title}
            </DialogTitle>
            <DialogDescription className="text-xs text-slate-500">
              Généré par IA (Gemini) — brouillon à vérifier avant usage.
            </DialogDescription>
          </DialogHeader>

          {loading ? (
            <div className="flex items-center justify-center gap-2 py-16 text-sm text-slate-500" data-testid="ai-loading">
              <Loader2 className="h-5 w-5 animate-spin text-indigo-500" /> Génération en cours…
            </div>
          ) : error ? (
            <p className="rounded-lg border border-red-200 bg-red-50 p-4 text-sm text-red-700" data-testid="ai-error">{error}</p>
          ) : (
            <>
              <div
                data-testid="ai-result-text"
                className="max-h-[55vh] overflow-auto whitespace-pre-wrap rounded-lg border border-slate-200 bg-slate-50 p-4 text-sm leading-relaxed text-slate-800"
              >
                {text}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" size="sm" onClick={copy} data-testid="ai-copy-btn" className="gap-1.5">
                  {copied ? <Check className="h-4 w-4 text-emerald-600" /> : <Copy className="h-4 w-4" />}
                  {copied ? "Copié" : "Copier"}
                </Button>
                <Button variant="outline" size="sm" onClick={download} data-testid="ai-download-btn" className="gap-1.5">
                  <Download className="h-4 w-4" /> Télécharger
                </Button>
              </div>
            </>
          )}
        </DialogContent>
      </Dialog>
    </>
  );
}
