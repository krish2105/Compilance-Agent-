import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Bot,
  FileDown,
  FileText,
  Landmark,
  Play,
  RotateCw,
  ScrollText,
  Sparkles,
  Table2,
  Target,
} from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { downloadAuditCsv, getCaseDetail, openCaseReport } from "../lib/api";
import { useAgentStream } from "../hooks/useAgentStream";
import { useUi } from "../lib/store";
import type { InvestigationResult } from "../lib/types";
import { cx, priorityStyles } from "../lib/utils";
import ApprovalGate from "./ApprovalGate";
import AuditLogViewer from "./AuditLogViewer";
import EvidenceCitation from "./EvidenceCitation";
import ChatPanel from "./ChatPanel";
import NarrativePanel from "./NarrativePanel";
import ReasoningTracePanel from "./ReasoningTracePanel";
import SarPanel from "./SarPanel";
import TypologyPanel from "./TypologyPanel";

type Tab = "narrative" | "evidence" | "typology" | "chat" | "audit";

const TABS: { key: Tab; label: string; icon: JSX.Element }[] = [
  { key: "narrative", label: "Narrative & Verification", icon: <FileText size={15} /> },
  { key: "evidence", label: "Evidence & Citations", icon: <Table2 size={15} /> },
  { key: "typology", label: "Typology & Regulation", icon: <Target size={15} /> },
  { key: "chat", label: "Analyst Chat", icon: <Bot size={15} /> },
  { key: "audit", label: "Audit Log", icon: <ScrollText size={15} /> },
];

export default function CaseDetail() {
  const { selectedCaseId } = useUi();
  const stream = useAgentStream();
  const [tab, setTab] = useState<Tab>("narrative");
  const [editedNarrative, setEditedNarrative] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["case", selectedCaseId],
    queryFn: () => getCaseDetail(selectedCaseId!),
    enabled: !!selectedCaseId,
  });

  // Reset when switching cases.
  useEffect(() => {
    stream.reset();
    setTab("narrative");
    setEditedNarrative(null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [selectedCaseId]);

  // Prefer the freshly streamed result; fall back to the cached detail result.
  const result: InvestigationResult | null = useMemo(
    () => stream.result ?? detailQuery.data?.result ?? null,
    [stream.result, detailQuery.data],
  );
  const review = detailQuery.data?.review ?? null;

  if (!selectedCaseId) return <EmptyState />;

  const caseInfo = detailQuery.data?.case;
  const priority = caseInfo ? priorityStyles[caseInfo.priority] ?? priorityStyles.Medium : null;

  return (
    <div className="flex h-full flex-col">
      {/* Sub-header */}
      <motion.div
        key={selectedCaseId}
        initial={{ opacity: 0, y: -6 }}
        animate={{ opacity: 1, y: 0 }}
        className="glass mb-4 p-4"
      >
        {/* Title + priority + summary (own row, never overlaps the actions) */}
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="font-mono text-sm font-bold text-ink">{selectedCaseId}</span>
            {priority && caseInfo && (
              <span className={cx("chip shrink-0", priority.chip)}>
                <span className={cx("h-1.5 w-1.5 rounded-full", priority.dot)} /> {priority.label}
              </span>
            )}
          </div>
          {caseInfo && (
            <p className="mt-1 line-clamp-2 text-[13px] text-ink-muted">{caseInfo.alert_summary}</p>
          )}
        </div>

        {/* Actions — their own wrapping row; full-width Re-run on mobile */}
        <div className="mt-3 flex flex-wrap items-center gap-2">
          {result && !result.error && (
            <>
              <button
                onClick={() => openCaseReport(selectedCaseId).catch(() => undefined)}
                className="btn-ghost flex-1 justify-center sm:flex-none"
                title="Open a printable case report (save as PDF)"
              >
                <FileDown size={15} /> Report
              </button>
              <button
                onClick={() => downloadAuditCsv(selectedCaseId).catch(() => undefined)}
                className="btn-ghost flex-1 justify-center sm:flex-none"
                title="Export the audit trail as CSV"
              >
                <FileDown size={15} /> Audit CSV
              </button>
            </>
          )}
          <button
            onClick={() => stream.start(selectedCaseId)}
            disabled={stream.phase === "running"}
            className="btn-brand w-full justify-center sm:ms-auto sm:w-auto"
          >
            {stream.phase === "running" ? (
              <>
                <RotateCw size={15} className="animate-spin" /> Investigating…
              </>
            ) : stream.phase === "done" || result ? (
              <>
                <RotateCw size={15} /> Re-run
              </>
            ) : (
              <>
                <Play size={15} /> Run investigation
              </>
            )}
          </button>
        </div>
      </motion.div>

      <div className="min-h-0 flex-1 space-y-4 overflow-y-auto pr-1">
        {/* Auto-hint to run */}
        {!result && stream.phase === "idle" && (
          <div className="glass flex items-center gap-3 p-4">
            <Sparkles size={18} className="text-brand" />
            <p className="text-sm text-ink-muted">
              Click <span className="font-semibold text-ink">Run investigation</span> to stream the
              multi-agent pipeline for this case.
            </p>
          </div>
        )}

        {/* Reasoning trace (during & after run) */}
        {(stream.phase !== "idle" || stream.steps.length > 0) && (
          <ReasoningTracePanel steps={stream.steps} phase={stream.phase} />
        )}

        {/* Result: approval gate + tabbed detail */}
        <AnimatePresence>
          {result && !result.error && (
            <motion.div
              initial={{ opacity: 0, y: 12 }}
              animate={{ opacity: 1, y: 0 }}
              className="space-y-4"
            >
              <ApprovalGate
                caseId={selectedCaseId}
                result={result}
                existingReview={review}
                onEdited={setEditedNarrative}
              />

              {/* Tabs */}
              <div className="glass-soft flex flex-wrap gap-1 p-1.5">
                {TABS.map((t) => (
                  <button
                    key={t.key}
                    onClick={() => setTab(t.key)}
                    className={cx(
                      "flex items-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-all",
                      tab === t.key
                        ? "bg-brand text-white shadow-glow"
                        : "text-ink-muted hover:bg-surface-overlay",
                    )}
                  >
                    {t.icon}
                    <span className="hidden md:inline">{t.label}</span>
                  </button>
                ))}
              </div>

              <AnimatePresence mode="wait">
                <motion.div
                  key={tab}
                  initial={{ opacity: 0, y: 8 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -8 }}
                  transition={{ duration: 0.2 }}
                >
                  {tab === "narrative" && (
                    <div className="space-y-4">
                      <NarrativePanel result={result} editedNarrative={editedNarrative} />
                      <SarPanel caseId={selectedCaseId} />
                    </div>
                  )}
                  {tab === "evidence" && <EvidenceCitation result={result} />}
                  {tab === "typology" && <TypologyPanel result={result} />}
                  {tab === "chat" && <ChatPanel caseId={selectedCaseId} />}
                  {tab === "audit" && <AuditLogViewer caseId={selectedCaseId} />}
                </motion.div>
              </AnimatePresence>
            </motion.div>
          )}
        </AnimatePresence>

        {result?.error && (
          <div className="glass border border-danger/40 p-4 text-sm text-danger">
            Investigation error: {result.error}
          </div>
        )}
      </div>
    </div>
  );
}

function EmptyState() {
  return (
    <div className="flex h-full items-center justify-center">
      <motion.div
        initial={{ opacity: 0, scale: 0.96 }}
        animate={{ opacity: 1, scale: 1 }}
        className="glass max-w-md p-8 text-center"
      >
        <div className="mx-auto mb-4 flex h-14 w-14 animate-float items-center justify-center rounded-2xl bg-brand text-white shadow-glow">
          <Landmark size={26} />
        </div>
        <h2 className="text-lg font-bold text-ink">Select a case to investigate</h2>
        <p className="mt-2 text-sm text-ink-muted">
          ComplianceAgent pre-screens flagged transactions, drafts EDD narratives with cited
          evidence, verifies every claim, and routes each case through a human approval gate.
        </p>
        <p className="mt-3 text-[11px] text-ink-faint">
          Draft-only · synthetic data · human sign-off required.
        </p>
      </motion.div>
    </div>
  );
}
