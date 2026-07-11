import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Bot, ScrollText, User } from "lucide-react";
import { getAudit } from "../lib/api";
import { cx } from "../lib/utils";

/** Displays the persisted audit trail (every agent step + every human action). */
export default function AuditLogViewer({ caseId }: { caseId: string }) {
  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["audit", caseId],
    queryFn: () => getAudit(caseId),
  });

  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <ScrollText size={16} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">Persistent Audit Trail</h3>
        <span className="ml-auto text-[11px] text-ink-faint">
          {data ? `${data.events.length} events` : ""} · SQLite
        </span>
      </div>

      {isLoading && <p className="py-6 text-center text-sm text-ink-faint">Loading audit log…</p>}
      {isError && (
        <p className="text-sm text-danger">Failed to load audit log: {(error as Error).message}</p>
      )}

      <ol className="relative space-y-2 border-l border-line pl-4">
        {data?.events.map((e, i) => {
          const human = e.actor_type === "human";
          const system = e.actor_type === "system";
          return (
            <motion.li
              key={e.id}
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              transition={{ delay: Math.min(i * 0.02, 0.4) }}
              className="relative"
            >
              <span
                className={cx(
                  "absolute -left-[22px] top-1 flex h-4 w-4 items-center justify-center rounded-full ring-4 ring-surface-raised",
                  human ? "bg-warn" : system ? "bg-accent" : "bg-brand",
                )}
              />
              <div className="rounded-lg border border-line bg-surface-raised/50 p-2.5">
                <div className="flex items-center gap-2">
                  {human ? (
                    <User size={13} className="text-warn" />
                  ) : (
                    <Bot size={13} className="text-brand" />
                  )}
                  <span className="text-xs font-semibold text-ink">{e.actor}</span>
                  <span className="chip bg-surface-base/60 py-0 text-[10px] text-ink-faint">
                    {e.action}
                  </span>
                  {e.llm_provider && (
                    <span className="chip bg-brand-soft py-0 text-[10px] text-brand">
                      {e.llm_provider}
                    </span>
                  )}
                  <span className="ml-auto font-mono text-[10px] text-ink-faint">
                    {new Date(e.ts).toLocaleTimeString()}
                  </span>
                </div>
                {e.summary && <p className="mt-1 text-[12px] text-ink-muted">{e.summary}</p>}
              </div>
            </motion.li>
          );
        })}
      </ol>
      {data && data.events.length === 0 && (
        <p className="py-4 text-center text-sm text-ink-faint">
          No audit events yet — run the investigation.
        </p>
      )}
    </div>
  );
}
