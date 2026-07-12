import { motion } from "framer-motion";
import { CheckCircle2, Globe2, ShieldAlert, ShieldX, UserCheck } from "lucide-react";
import type { InvestigationResult } from "../lib/types";
import { cx } from "../lib/utils";

/** Sanctions / PEP / jurisdiction screening results. */
export default function ScreeningPanel({ result }: { result: InvestigationResult }) {
  const s = result.screening;
  if (!s) return null;

  const hasSanctions = s.name_hits.length > 0 || s.sanctioned_jurisdictions.length > 0;
  const tone = hasSanctions ? "danger" : s.cleared ? "ok" : "warn";
  const toneCls = {
    danger: "border-danger/50 bg-danger/5",
    warn: "border-warn/40 bg-warn/5",
    ok: "border-ok/30 bg-ok/5",
  }[tone];

  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      className={cx("glass border-2 p-4", toneCls)}
    >
      <div className="mb-3 flex items-center gap-2">
        <div
          className={cx(
            "flex h-8 w-8 items-center justify-center rounded-lg text-white",
            hasSanctions ? "bg-danger" : s.cleared ? "bg-ok" : "bg-warn",
          )}
        >
          {hasSanctions ? <ShieldX size={16} /> : s.cleared ? <CheckCircle2 size={16} /> : <ShieldAlert size={16} />}
        </div>
        <div>
          <h3 className="text-sm font-bold text-ink">Sanctions &amp; PEP Screening</h3>
          <p className="text-[11px] text-ink-faint">{s.risk_level}</p>
        </div>
        <span className="ml-auto text-[11px] text-ink-faint">
          {(s.watchlist.watchlist_entries as number) ?? 0} watchlist entries
        </span>
      </div>

      {s.cleared ? (
        <p className="rounded-lg border border-ok/30 bg-ok/5 px-3 py-2 text-sm text-ok">
          <CheckCircle2 size={14} className="mr-1 inline" /> No sanctions, PEP, or high-risk-jurisdiction hits — screening cleared.
        </p>
      ) : (
        <div className="space-y-2">
          {s.name_hits.map((h, i) => (
            <div key={i} className="rounded-lg border border-danger/30 bg-danger/5 p-2.5">
              <div className="flex items-center gap-2">
                <ShieldX size={14} className="text-danger" />
                <span className="text-[13px] font-semibold text-ink">{h.matched_entry}</span>
                <span className="chip bg-danger/15 text-danger">{h.type} · {Math.round(h.score * 100)}% match</span>
              </div>
              <p className="mt-0.5 text-[11px] text-ink-muted">
                {h.program} · {h.country} · matched account {h.screened_account?.slice(-6)} ({h.query})
              </p>
            </div>
          ))}
          {s.sanctioned_jurisdictions.map((j) => (
            <div key={j.country} className="flex items-center gap-2 rounded-lg border border-danger/30 bg-danger/5 p-2.5">
              <Globe2 size={14} className="text-danger" />
              <span className="text-[13px] font-semibold text-ink">{j.country}</span>
              <span className="chip bg-danger/15 text-danger">sanctioned jurisdiction</span>
              <span className="ml-auto text-[11px] text-ink-faint">{j.program}</span>
            </div>
          ))}
          {s.pep_flagged.map((p, i) => (
            <div key={`pep-${i}`} className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/5 p-2.5">
              <UserCheck size={14} className="text-warn" />
              <span className="text-[13px] font-semibold text-ink">{p.name}</span>
              <span className="chip bg-warn/15 text-warn">PEP {p.is_subject ? "(subject)" : "(counterparty)"}</span>
              <span className="ml-auto text-[11px] text-ink-faint">{p.source}</span>
            </div>
          ))}
          {s.jurisdiction_hits
            .filter((j) => j.status === "high_risk")
            .map((j) => (
              <div key={j.country} className="flex items-center gap-2 rounded-lg border border-warn/30 bg-warn/5 p-2.5">
                <Globe2 size={14} className="text-warn" />
                <span className="text-[13px] font-semibold text-ink">{j.country}</span>
                <span className="chip bg-warn/15 text-warn">high-risk jurisdiction</span>
                <span className="ml-auto text-[11px] text-ink-faint">{j.program}</span>
              </div>
            ))}
        </div>
      )}
      <p className="mt-2 text-[11px] text-ink-faint">{s.summary}</p>
    </motion.div>
  );
}
