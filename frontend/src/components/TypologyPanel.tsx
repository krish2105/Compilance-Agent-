import { motion } from "framer-motion";
import { BrainCircuit, Flag, Target } from "lucide-react";
import type { InvestigationResult } from "../lib/types";
import { cx } from "../lib/utils";

/** Shows the ranked typology match with a confidence meter + drivers + regulatory context. */
export default function TypologyPanel({ result }: { result: InvestigationResult }) {
  const tm = result.typology_match;
  const best = tm.best_match;
  const reg = result.regulatory.primary;
  const confPct = Math.round(tm.confidence * 100);

  return (
    <div className="space-y-4">
      <div className="glass p-4">
        <div className="mb-3 flex items-center gap-2">
          <Target size={16} className="text-brand" />
          <h3 className="text-sm font-bold text-ink">Typology Assessment</h3>
          <span className="ml-auto text-[11px] text-ink-faint">deterministic cosine match</span>
        </div>

        <div className="rounded-xl border border-brand/30 bg-brand-soft/40 p-4">
          <div className="flex items-center justify-between">
            <div>
              <p className="label">Best match</p>
              <p className="text-lg font-bold text-ink">{best.typology_label}</p>
            </div>
            <div className="text-right">
              <p className="label">Confidence</p>
              <p className="text-2xl font-extrabold text-brand">{confPct}%</p>
            </div>
          </div>
          <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-base">
            <motion.div
              initial={{ width: 0 }}
              animate={{ width: `${confPct}%` }}
              transition={{ duration: 0.8, ease: "easeOut" }}
              className={cx(
                "h-full rounded-full",
                confPct >= 70 ? "bg-ok" : confPct >= 45 ? "bg-warn" : "bg-danger",
              )}
            />
          </div>
          <p className="mt-3 text-[13px] leading-relaxed text-ink-muted">{best.definition}</p>
          <div className="mt-3 flex flex-wrap gap-1.5">
            {best.drivers.map((d) => (
              <span key={d.dimension} className="chip bg-surface-raised/70 text-ink-muted">
                <BrainCircuit size={11} /> {d.dimension} · {d.contribution.toFixed(2)}
              </span>
            ))}
          </div>
        </div>

        {/* Ranked alternatives */}
        <div className="mt-3 space-y-2">
          <p className="label">Ranked candidates</p>
          {tm.ranked.map((r, i) => (
            <div key={r.typology_key} className="flex items-center gap-3">
              <span className="w-4 font-mono text-xs text-ink-faint">{i + 1}</span>
              <span className="flex-1 text-[13px] text-ink-muted">{r.typology_label}</span>
              <div className="h-1.5 w-24 overflow-hidden rounded-full bg-surface-base">
                <div
                  className="h-full rounded-full bg-brand/70"
                  style={{ width: `${Math.round(r.similarity * 100)}%` }}
                />
              </div>
              <span className="w-10 text-right font-mono text-[11px] text-ink-faint">
                {r.similarity.toFixed(2)}
              </span>
            </div>
          ))}
        </div>
      </div>

      {/* Red flags + regulatory context */}
      <div className="glass p-4">
        <div className="mb-3 flex items-center gap-2">
          <Flag size={16} className="text-brand" />
          <h3 className="text-sm font-bold text-ink">Indicators & Regulatory Context</h3>
        </div>
        <ul className="mb-3 space-y-1.5">
          {best.red_flags.map((f) => (
            <li key={f} className="flex items-start gap-2 text-[13px] text-ink-muted">
              <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-warn" />
              {f}
            </li>
          ))}
        </ul>
        <div className="rounded-lg border-l-4 border-accent/60 bg-accent/10 px-3 py-2 text-xs leading-relaxed text-ink-muted">
          {reg.regulatory_note}
        </div>
        <p className="mt-2 text-[11px] text-ink-faint">
          Knowledge base: {result.regulatory.rag_backend}
        </p>
      </div>
    </div>
  );
}
