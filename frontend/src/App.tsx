import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, ShieldHalf, TriangleAlert } from "lucide-react";
import CaseDetail from "./components/CaseDetail";
import CaseList from "./components/CaseList";
import ThemeToggle from "./components/ThemeToggle";
import { fetchHealth } from "./lib/api";

export default function App() {
  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1 });
  const online = health.isSuccess;
  const provider =
    (health.data?.llm as { provider?: string } | undefined)?.provider ?? "…";

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="z-20 border-b border-line/70 bg-surface-raised/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1500px] items-center gap-3 px-4 py-3">
          <motion.div
            initial={{ rotate: -12, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-white shadow-glow"
          >
            <ShieldHalf size={22} />
          </motion.div>
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-base font-extrabold tracking-tight text-ink">
              ComplianceAgent
              <span className="chip bg-brand-soft text-brand">AML / KYC Copilot</span>
            </h1>
            <p className="hidden text-[11px] text-ink-faint sm:block">
              Multi-agent case investigation · evidence-cited drafts · human-in-the-loop
            </p>
          </div>

          <div className="ml-auto flex items-center gap-2.5">
            <span
              className={`chip ${
                online ? "bg-ok/15 text-ok" : "bg-danger/15 text-danger"
              }`}
              title={online ? "Backend connected" : "Backend unreachable"}
            >
              <Activity size={13} />
              {online ? "API connected" : "API offline"}
            </span>
            {online && (
              <span className="chip hidden bg-brand-soft text-brand sm:inline-flex" title="Active LLM provider">
                LLM · {provider}
              </span>
            )}
            <ThemeToggle />
          </div>
        </div>

        {/* Disclaimer banner */}
        <div className="flex items-center gap-2 border-t border-warn/20 bg-warn/10 px-4 py-1.5 text-[11px] text-warn">
          <TriangleAlert size={13} className="shrink-0" />
          <span className="truncate">
            Portfolio/demo on synthetic data. Not certified compliance software. Every output is a
            <strong className="mx-1">draft requiring human sign-off</strong>— nothing is auto-cleared or
            auto-reported.
          </span>
        </div>
      </header>

      {/* Body: floating two-pane layout */}
      <main className="mx-auto grid w-full max-w-[1500px] flex-1 grid-cols-1 gap-4 overflow-hidden p-4 lg:grid-cols-[360px_1fr]">
        <aside className="glass hidden min-h-0 flex-col p-3 lg:flex">
          <CaseList />
        </aside>

        {/* Mobile: case list collapses above detail */}
        <aside className="glass min-h-0 p-3 lg:hidden">
          <CaseList />
        </aside>

        <section className="min-h-0">
          <CaseDetail />
        </section>
      </main>
    </div>
  );
}
