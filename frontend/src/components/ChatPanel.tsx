import { AnimatePresence, motion } from "framer-motion";
import { Bot, Cpu, Loader2, Send, Sparkles, User, Wrench } from "lucide-react";
import { useRef, useState } from "react";
import { chatWithCase, type ChatAnswer } from "../lib/api";
import { cx } from "../lib/utils";

interface Msg {
  role: "user" | "assistant";
  content: string;
  meta?: ChatAnswer;
}

const SUGGESTED = [
  "What typology is this and how confident are we?",
  "How much money is involved?",
  "Any sanctions or PEP hits?",
  "Have we seen similar cases before?",
  "What's the overall risk and why?",
];

/** Conversational Q&A over a case — planner routes to tools + case memory. */
export default function ChatPanel({ caseId }: { caseId: string }) {
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const endRef = useRef<HTMLDivElement>(null);

  const send = async (q: string) => {
    if (!q.trim() || loading) return;
    const history = messages.map((m) => ({ role: m.role, content: m.content }));
    setMessages((m) => [...m, { role: "user", content: q }]);
    setInput("");
    setLoading(true);
    try {
      const ans = await chatWithCase(caseId, q, history);
      setMessages((m) => [...m, { role: "assistant", content: ans.answer, meta: ans }]);
    } catch (e) {
      setMessages((m) => [...m, { role: "assistant", content: `Error: ${(e as Error).message}` }]);
    } finally {
      setLoading(false);
      setTimeout(() => endRef.current?.scrollIntoView({ behavior: "smooth" }), 50);
    }
  };

  return (
    <div className="glass flex h-[560px] flex-col p-4">
      <div className="mb-3 flex items-center gap-2">
        <Bot size={16} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">Analyst Chat</h3>
        <span className="ml-auto text-[11px] text-ink-faint">planner · tool-use · case memory</span>
      </div>

      <div className="min-h-0 flex-1 space-y-3 overflow-y-auto pr-1">
        {messages.length === 0 && (
          <div className="space-y-3">
            <div className="glass-soft flex items-center gap-2 p-3 text-[13px] text-ink-muted">
              <Sparkles size={15} className="text-brand" />
              Ask anything about this case — I route your question to the right evidence, screening,
              risk, and similar past cases.
            </div>
            <div className="flex flex-wrap gap-1.5">
              {SUGGESTED.map((s) => (
                <button key={s} onClick={() => send(s)} className="chip bg-surface-raised/70 text-ink-muted hover:bg-surface-overlay">
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        <AnimatePresence>
          {messages.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              className={cx("flex gap-2.5", m.role === "user" ? "flex-row-reverse" : "")}
            >
              <span
                className={cx(
                  "flex h-7 w-7 shrink-0 items-center justify-center rounded-lg",
                  m.role === "user" ? "bg-brand text-white" : "bg-brand-soft text-brand",
                )}
              >
                {m.role === "user" ? <User size={14} /> : <Bot size={14} />}
              </span>
              <div className={cx("max-w-[80%] rounded-xl border border-line p-3",
                                 m.role === "user" ? "bg-brand-soft/40" : "bg-surface-raised/60")}>
                <p className="whitespace-pre-wrap text-[13px] leading-relaxed text-ink-muted">{m.content}</p>
                {m.meta && m.meta.tools_used.length > 0 && (
                  <div className="mt-2 flex flex-wrap items-center gap-1.5">
                    {m.meta.tools_used.map((t) => (
                      <span key={t} className="chip bg-surface-base/70 py-0 text-[10px] text-ink-faint">
                        <Wrench size={9} /> {t}
                      </span>
                    ))}
                    {m.meta.llm_provider && (
                      <span className="chip bg-brand-soft py-0 text-[10px] text-brand">
                        <Cpu size={9} /> {m.meta.llm_provider}
                      </span>
                    )}
                  </div>
                )}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
        {loading && (
          <div className="flex items-center gap-2 text-sm text-ink-faint">
            <Loader2 size={14} className="animate-spin text-brand" /> Thinking…
          </div>
        )}
        <div ref={endRef} />
      </div>

      <form
        onSubmit={(e) => {
          e.preventDefault();
          send(input);
        }}
        className="mt-3 flex items-center gap-2"
      >
        <input
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="Ask about this case…"
          className="flex-1 rounded-xl border border-line bg-surface-raised/60 px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none"
        />
        <button type="submit" disabled={loading || !input.trim()} className="btn-brand">
          <Send size={15} />
        </button>
      </form>
    </div>
  );
}
