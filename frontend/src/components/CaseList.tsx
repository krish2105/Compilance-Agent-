import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { AlertTriangle, Search, ShieldCheck } from "lucide-react";
import { useMemo, useState } from "react";
import { listCases } from "../lib/api";
import { useUi } from "../lib/store";
import type { CaseSummary } from "../lib/types";
import { cx, prettyStatus, priorityStyles, reviewStatusStyle } from "../lib/utils";

export default function CaseList() {
  const { selectedCaseId, selectCase } = useUi();
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["cases"],
    queryFn: listCases,
  });
  const [q, setQ] = useState("");
  const [priorityFilter, setPriorityFilter] = useState<string>("all");
  const [statusFilter, setStatusFilter] = useState<string>("all");

  const cases = useMemo(() => {
    let list = data ?? [];
    if (q.trim()) {
      const needle = q.toLowerCase();
      list = list.filter(
        (c) =>
          c.case_id.toLowerCase().includes(needle) ||
          c.subject_account.toLowerCase().includes(needle) ||
          c.alert_summary.toLowerCase().includes(needle),
      );
    }
    if (priorityFilter !== "all") list = list.filter((c) => c.priority === priorityFilter);
    if (statusFilter === "pending") list = list.filter((c) => c.review_status === "PENDING_REVIEW");
    if (statusFilter === "reviewed") list = list.filter((c) => c.review_status !== "PENDING_REVIEW");
    return list;
  }, [data, q, priorityFilter, statusFilter]);

  const pending = (data ?? []).filter((c) => c.review_status === "PENDING_REVIEW").length;

  return (
    <div className="flex h-full flex-col">
      <div className="mb-3 flex items-center justify-between px-0.5">
        <div>
          <h2 className="text-[15px] font-bold tracking-tight text-ink">Case Queue</h2>
          <p className="mt-0.5 text-xs text-ink-faint">
            {data ? `${data.length} cases · ${pending} pending review` : "Loading…"}
          </p>
        </div>
        <span className="chip bg-warn/10 text-warn ring-1 ring-inset ring-warn/25">
          <AlertTriangle size={12} /> {pending}
        </span>
      </div>

      <div className="relative mb-3">
        <Search
          size={15}
          className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-faint"
        />
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Search case, account, pattern…"
          className="w-full rounded-xl border border-line bg-surface-raised/60 py-2.5 pl-9 pr-3 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none focus:ring-2 focus:ring-brand/25"
        />
      </div>

      <div className="mb-3 flex gap-2">
        <select
          value={priorityFilter}
          onChange={(e) => setPriorityFilter(e.target.value)}
          className="flex-1 rounded-lg border border-line bg-surface-raised/60 px-2 py-1.5 text-xs text-ink focus:border-brand/60 focus:outline-none"
        >
          <option value="all">All priorities</option>
          <option value="Critical">Critical</option>
          <option value="High">High</option>
          <option value="Medium">Medium</option>
          <option value="Low">Low</option>
        </select>
        <select
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          className="flex-1 rounded-lg border border-line bg-surface-raised/60 px-2 py-1.5 text-xs text-ink focus:border-brand/60 focus:outline-none"
        >
          <option value="all">All statuses</option>
          <option value="pending">Pending review</option>
          <option value="reviewed">Reviewed</option>
        </select>
      </div>

      <div className="-mr-2 flex-1 space-y-1.5 overflow-y-auto pr-2">
        {isLoading &&
          Array.from({ length: 7 }).map((_, i) => (
            <div key={i} className="h-[74px] animate-pulse rounded-xl bg-surface-raised/50" />
          ))}
        {isError && (
          <div className="glass-soft p-4 text-sm text-danger">
            Failed to load cases: {(error as Error).message}. Is the backend running?
          </div>
        )}
        <AnimatePresence>
          {cases.map((c, i) => (
            <CaseCard
              key={c.case_id}
              c={c}
              index={i}
              active={c.case_id === selectedCaseId}
              onClick={() => selectCase(c.case_id)}
            />
          ))}
        </AnimatePresence>
        {data && cases.length === 0 && (
          <div className="glass-soft p-4 text-center text-sm text-ink-faint">No matching cases.</div>
        )}
      </div>
    </div>
  );
}

function CaseCard({
  c,
  index,
  active,
  onClick,
}: {
  c: CaseSummary;
  index: number;
  active: boolean;
  onClick: () => void;
}) {
  const p = priorityStyles[c.priority] ?? priorityStyles.Medium;
  const reviewed = c.review_status !== "PENDING_REVIEW";
  return (
    <motion.button
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0 }}
      transition={{ delay: Math.min(index * 0.02, 0.2), duration: 0.22 }}
      onClick={onClick}
      className={cx(
        "group relative w-full overflow-hidden rounded-xl border p-3 text-left transition-colors duration-150",
        active
          ? "border-line bg-brand/[0.06]"
          : "border-line bg-surface-raised/50 hover:border-line hover:bg-surface-overlay",
      )}
    >
      {/* Active accent rail */}
      <span
        className={cx(
          "absolute inset-y-0 left-0 w-0.5 rounded-r bg-brand transition-opacity",
          active ? "opacity-100" : "opacity-0",
        )}
      />
      <div className="mb-1 flex items-center justify-between gap-2">
        <span className="font-mono text-[11px] font-semibold tracking-tight text-ink">{c.case_id}</span>
        <span className={cx("chip px-2 py-0.5 text-[10.5px]", p.chip)}>
          <span className={cx("h-1.5 w-1.5 rounded-full", p.dot)} /> {p.label}
        </span>
      </div>
      <p className="line-clamp-2 text-[12.5px] leading-snug text-ink-muted">{c.alert_summary}</p>
      <div className="mt-2 flex items-center justify-between">
        <span className="font-mono text-[10.5px] text-ink-faint">{c.transaction_count} txns</span>
        <span
          className={cx(
            "chip px-2 py-0.5 text-[10px]",
            reviewed ? reviewStatusStyle(c.review_status) : "text-ink-faint",
          )}
        >
          {reviewed ? <ShieldCheck size={10} /> : null}
          {prettyStatus(c.review_status)}
        </span>
      </div>
    </motion.button>
  );
}
