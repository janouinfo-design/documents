import { useState, useRef, useEffect } from "react";
import { Sparkles, Send, Loader2, User2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { aiAssistant } from "@/lib/api";
import { useAiAvailable } from "@/components/ai/AiActionButton";
import { cn } from "@/lib/utils";

const SUGGESTIONS = [
  "Quels véhicules ont un document expiré ?",
  "Quelles échéances arrivent dans les 30 prochains jours ?",
  "Combien d'amendes sont encore à payer ?",
  "Quels véhicules électriques ai-je dans la flotte ?",
];

export default function AiAssistantPage() {
  const available = useAiAvailable();
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef(null);

  useEffect(() => { endRef.current?.scrollIntoView({ behavior: "smooth" }); }, [messages, loading]);

  const ask = async (q) => {
    const question = (q ?? input).trim();
    if (!question || loading) return;
    setInput("");
    setMessages((m) => [...m, { role: "user", text: question }]);
    setLoading(true);
    try {
      const d = await aiAssistant(question);
      setMessages((m) => [...m, { role: "ai", text: d.text }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "ai", error: true, text: "⚠️ " + (e?.response?.data?.detail || "Échec de la génération.") }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="mx-auto flex h-[calc(100vh-210px)] max-w-3xl flex-col" data-testid="ai-assistant-page">
      <header className="mb-4">
        <h1 className="flex items-center gap-2 font-display text-2xl font-bold tracking-tight text-slate-900">
          <Sparkles className="h-6 w-6 text-indigo-500" /> Assistant IA
        </h1>
        <p className="mt-1 text-sm text-slate-500">
          Posez vos questions en langage naturel sur votre flotte — réponses basées sur vos données.
        </p>
      </header>

      {!available ? (
        <div className="flex flex-1 items-center justify-center rounded-xl border border-dashed border-slate-300 bg-white p-8 text-center" data-testid="ai-unavailable">
          <p className="max-w-md text-sm text-slate-500">
            L'assistant IA n'est pas configuré pour ce client (clé Gemini absente côté serveur).
            Contactez votre administrateur pour l'activer.
          </p>
        </div>
      ) : (
        <>
          <div className="flex-1 space-y-4 overflow-y-auto rounded-xl border border-slate-200 bg-white p-4" data-testid="ai-chat-log">
            {messages.length === 0 && (
              <div className="flex flex-wrap gap-2" data-testid="ai-suggestions">
                {SUGGESTIONS.map((s) => (
                  <button
                    key={s} onClick={() => ask(s)} data-testid="ai-suggestion"
                    className="rounded-full border border-slate-200 bg-slate-50 px-3 py-1.5 text-xs text-slate-600 transition-colors hover:border-indigo-300 hover:text-indigo-600"
                  >
                    {s}
                  </button>
                ))}
              </div>
            )}
            {messages.map((m, i) => (
              <div key={i} className={cn("flex gap-3", m.role === "user" ? "justify-end" : "justify-start")} data-testid={`ai-msg-${m.role}`}>
                {m.role === "ai" && (
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-indigo-100">
                    <Sparkles className="h-4 w-4 text-indigo-600" />
                  </div>
                )}
                <div className={cn(
                  "max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2.5 text-sm leading-relaxed",
                  m.role === "user" ? "bg-slate-900 text-white" : m.error ? "bg-red-50 text-red-700" : "bg-slate-100 text-slate-800",
                )}>
                  {m.text}
                </div>
                {m.role === "user" && (
                  <div className="mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-slate-200">
                    <User2 className="h-4 w-4 text-slate-500" />
                  </div>
                )}
              </div>
            ))}
            {loading && (
              <div className="flex items-center gap-2 text-sm text-slate-400" data-testid="ai-chat-loading">
                <Loader2 className="h-4 w-4 animate-spin" /> L'assistant réfléchit…
              </div>
            )}
            <div ref={endRef} />
          </div>

          <div className="mt-3 flex items-end gap-2">
            <Textarea
              value={input} onChange={(e) => setInput(e.target.value)} rows={2}
              data-testid="ai-input" placeholder="Posez une question sur votre flotte…"
              onKeyDown={(e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); ask(); } }}
              className="resize-none"
            />
            <Button onClick={() => ask()} disabled={loading || !input.trim()} data-testid="ai-send-btn" className="h-[62px] gap-1.5">
              <Send className="h-4 w-4" /> Envoyer
            </Button>
          </div>
        </>
      )}
    </div>
  );
}
