import { CheckCircle2, Cpu, FileText, ShieldCheck, XCircle } from "lucide-react";
import type { InvestigationResult } from "../lib/types";
import { cx, renderMarkdown } from "../lib/utils";

/** Renders the drafted narrative + the Verifier's per-claim verification. */
export default function NarrativePanel({
  result,
  editedNarrative,
}: {
  result: InvestigationResult;
  editedNarrative?: string | null;
}) {
  const v = result.verification;
  const narrative = editedNarrative ?? result.narrative;

  return (
    <div className="space-y-4">
      {/* Provider + verification summary bar */}
      <div className="glass flex flex-wrap items-center gap-2 p-3">
        <span className="chip bg-brand-soft text-brand">
          <Cpu size={12} /> LLM: {result.llm_provider}
          {result.llm_fallback_used ? " (deterministic)" : ""}
        </span>
        <span
          className={cx(
            "chip",
            v.passed ? "bg-ok/15 text-ok" : "bg-warn/15 text-warn",
          )}
        >
          <ShieldCheck size={12} /> {v.passed ? "Verification passed" : "Issues flagged"}
        </span>
        {v.low_confidence && (
          <span className="chip bg-warn/15 text-warn">Low typology confidence</span>
        )}
        <span className="ml-auto text-[11px] text-ink-faint">{v.summary}</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1.6fr_1fr]">
        {/* Narrative */}
        <div className="glass p-5">
          <div className="mb-2 flex items-center gap-2">
            <FileText size={16} className="text-brand" />
            <h3 className="text-sm font-bold text-ink">
              Case Narrative & EDD Draft {editedNarrative ? "(analyst-edited)" : ""}
            </h3>
          </div>
          <div
            className="markdown"
            dangerouslySetInnerHTML={{ __html: renderMarkdown(narrative) }}
          />
        </div>

        {/* Verified claims */}
        <div className="glass h-fit p-4">
          <div className="mb-3 flex items-center gap-2">
            <ShieldCheck size={16} className="text-brand" />
            <h3 className="text-sm font-bold text-ink">Claim Verification</h3>
          </div>
          <p className="mb-3 text-[11px] text-ink-faint">
            Each claim is independently recomputed from the queried evidence.
          </p>
          <ul className="space-y-2">
            {v.verified_claims.map((c) => (
              <li
                key={c.id}
                className={cx(
                  "rounded-lg border p-2.5",
                  c.verified ? "border-ok/30 bg-ok/5" : "border-danger/30 bg-danger/5",
                )}
              >
                <div className="flex items-start gap-2">
                  {c.verified ? (
                    <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-ok" />
                  ) : (
                    <XCircle size={15} className="mt-0.5 shrink-0 text-danger" />
                  )}
                  <div className="min-w-0">
                    <p className="text-[12px] leading-snug text-ink-muted">{c.statement}</p>
                    <p className="mt-0.5 font-mono text-[10px] text-ink-faint">
                      {c.fact_path}: expected {String(c.expected)} · actual {String(c.actual)}
                    </p>
                  </div>
                </div>
              </li>
            ))}
          </ul>
          {v.issues.length > 0 && (
            <div className="mt-3 rounded-lg border border-danger/30 bg-danger/5 p-2.5">
              <p className="mb-1 text-[11px] font-semibold text-danger">Flagged issues</p>
              {v.issues.map((iss, i) => (
                <p key={i} className="text-[11px] text-ink-muted">
                  • {iss.detail}
                </p>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
