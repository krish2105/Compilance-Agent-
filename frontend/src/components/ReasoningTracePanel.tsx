import { AnimatePresence, motion } from "framer-motion";
import {
  Boxes,
  BrainCircuit,
  CheckCircle2,
  ChevronDown,
  Database,
  FileText,
  Loader2,
  RefreshCw,
  ScrollText,
  ShieldCheck,
  XCircle,
} from "lucide-react";
import { useState } from "react";
import type { AgentStepEvent } from "../lib/types";
import type { StreamPhase } from "../hooks/useAgentStream";
import { cx } from "../lib/utils";

const AGENT_META: Record<string, { icon: JSX.Element; blurb: string }> = {
  EvidenceAgent: { icon: <Database size={16} />, blurb: "Queries DuckDB for the case network, KYC & history" },
  TypologyMatchAgent: { icon: <BrainCircuit size={16} />, blurb: "Scores the pattern against 28 SAML-D typologies" },
  RegulatoryContextAgent: { icon: <Boxes size={16} />, blurb: "RAG lookup over the typology knowledge base" },
  NarrativeAgent: { icon: <FileText size={16} />, blurb: "Drafts the case narrative & EDD report" },
  Verifier: { icon: <ShieldCheck size={16} />, blurb: "Checks every claim against source evidence" },
  Orchestrator: { icon: <ScrollText size={16} />, blurb: "LangGraph state machine coordinating the agents" },
};

const PIPELINE = [
  "EvidenceAgent",
  "TypologyMatchAgent",
  "RegulatoryContextAgent",
  "NarrativeAgent",
  "Verifier",
  "Orchestrator",
];

export default function ReasoningTracePanel({
  steps,
  phase,
}: {
  steps: AgentStepEvent[];
  phase: StreamPhase;
}) {
  const lastAgent = steps.length ? steps[steps.length - 1].agent : null;

  return (
    <div className="space-y-4">
      {/* Pipeline rail */}
      <div className="glass p-4">
        <div className="mb-3 flex items-center gap-2">
          <BrainCircuit size={16} className="text-brand" />
          <h3 className="text-sm font-bold text-ink">Multi-Agent Reasoning Pipeline</h3>
          {phase === "running" && (
            <span className="chip ml-auto animate-pulse-glow bg-brand-soft text-brand">
              <Loader2 size={12} className="animate-spin" /> Investigating
            </span>
          )}
          {phase === "done" && (
            <span className="chip ml-auto bg-ok/15 text-ok">
              <CheckCircle2 size={12} /> Complete
            </span>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-1.5">
          {PIPELINE.map((agent, i) => {
            const reached = steps.some((s) => s.agent === agent);
            const isCurrent = agent === lastAgent && phase === "running";
            return (
              <div key={agent} className="flex items-center gap-1.5">
                <motion.div
                  initial={false}
                  animate={{
                    scale: isCurrent ? 1.05 : 1,
                  }}
                  className={cx(
                    "flex items-center gap-1.5 rounded-lg border px-2.5 py-1.5 text-[11px] font-semibold transition-colors",
                    reached
                      ? "border-brand/40 bg-brand-soft/50 text-brand"
                      : "border-line bg-surface-raised/40 text-ink-faint",
                  )}
                >
                  {AGENT_META[agent]?.icon}
                  <span className="hidden sm:inline">{agent.replace("Agent", "")}</span>
                </motion.div>
                {i < PIPELINE.length - 1 && (
                  <div
                    className={cx(
                      "h-0.5 w-3 rounded-full transition-colors",
                      reached ? "bg-brand/50" : "bg-line",
                    )}
                  />
                )}
              </div>
            );
          })}
        </div>
      </div>

      {/* Step timeline */}
      <div className="glass p-4">
        <h3 className="mb-3 text-sm font-bold text-ink">Live Reasoning Trace</h3>
        {steps.length === 0 && phase !== "running" && (
          <p className="py-6 text-center text-sm text-ink-faint">
            Run the investigation to stream the agents' reasoning here.
          </p>
        )}
        {steps.length === 0 && phase === "running" && (
          <div className="flex items-center gap-2 py-6 text-sm text-ink-muted">
            <Loader2 size={16} className="animate-spin text-brand" /> Spinning up the orchestrator…
          </div>
        )}
        <ol className="relative space-y-2.5">
          <AnimatePresence>
            {steps.map((s, i) => (
              <StepRow key={`${s.agent}-${s.step}-${i}`} step={s} index={i} />
            ))}
          </AnimatePresence>
        </ol>
      </div>
    </div>
  );
}

function StepRow({ step, index }: { step: AgentStepEvent; index: number }) {
  const [open, setOpen] = useState(false);
  const meta = AGENT_META[step.agent];
  const isRetry = step.status === "retry";
  const isError = step.status === "error";

  const statusIcon = isError ? (
    <XCircle size={16} className="text-danger" />
  ) : isRetry ? (
    <RefreshCw size={16} className="text-warn" />
  ) : (
    <CheckCircle2 size={16} className="text-ok" />
  );

  return (
    <motion.li
      initial={{ opacity: 0, x: -12 }}
      animate={{ opacity: 1, x: 0 }}
      transition={{ duration: 0.35, delay: Math.min(index * 0.02, 0.2) }}
      className={cx(
        "rounded-xl border p-3 transition-colors",
        isError
          ? "border-danger/40 bg-danger/5"
          : isRetry
            ? "border-warn/40 bg-warn/5"
            : "border-line bg-surface-raised/50",
      )}
    >
      <button
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-3 text-left"
      >
        <span
          className={cx(
            "flex h-8 w-8 shrink-0 items-center justify-center rounded-lg",
            isError ? "bg-danger/10 text-danger" : "bg-brand-soft/60 text-brand",
          )}
        >
          {meta?.icon ?? <BrainCircuit size={16} />}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex items-center gap-2">
            <span className="text-xs font-bold text-ink">{step.agent}</span>
            {statusIcon}
          </div>
          <p className="truncate text-[13px] text-ink-muted">{step.title}</p>
        </div>
        <ChevronDown
          size={16}
          className={cx("shrink-0 text-ink-faint transition-transform", open && "rotate-180")}
        />
      </button>
      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden"
          >
            <pre className="mt-3 max-h-72 overflow-auto rounded-lg border border-line bg-surface-base/70 p-3 font-mono text-[11px] leading-relaxed text-ink-muted">
              {JSON.stringify(step.detail, null, 2)}
            </pre>
          </motion.div>
        )}
      </AnimatePresence>
    </motion.li>
  );
}
