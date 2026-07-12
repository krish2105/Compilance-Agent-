import { motion } from "framer-motion";
import { Boxes, Cpu, ShieldAlert, TrendingUp } from "lucide-react";
import type { InvestigationResult } from "../lib/types";
import { cx } from "../lib/utils";

/** GNN detector output: case risk, ensemble score, top-risk accounts, model metrics. */
export default function GnnPanel({ result }: { result: InvestigationResult }) {
  const gnn = result.gnn;
  const risk = result.risk;
  if (!gnn?.available || !risk) return null;

  const pct = (v?: number | null) => (v == null ? "—" : `${Math.round(v * 100)}%`);
  const bandColor: Record<string, string> = {
    Critical: "text-priority-critical",
    High: "text-priority-high",
    Medium: "text-priority-medium",
    Low: "text-priority-low",
  };
  const overall = Math.round(risk.overall_risk * 100);

  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <Boxes size={16} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">GNN Detector &amp; Ensemble Risk</h3>
        <span className="ml-auto text-[11px] text-ink-faint">{gnn.model?.architecture}</span>
      </div>

      {/* Ensemble risk meter */}
      <div className="rounded-xl border border-line bg-surface-raised/50 p-4">
        <div className="flex items-end justify-between">
          <div>
            <p className="label">Ensemble risk (typology + GNN)</p>
            <p className={cx("text-2xl font-extrabold", bandColor[risk.risk_band])}>
              {overall}% · {risk.risk_band}
            </p>
          </div>
          <div className="text-right text-[11px] text-ink-faint">
            <div>typology: {pct(risk.components.typology_confidence)}</div>
            <div>GNN: {pct(risk.components.gnn_case_risk)}</div>
            <div>screening: {pct(risk.components.screening_risk)}</div>
            {risk.sanctions_override && <div className="text-danger">⚠ sanctions override</div>}
          </div>
        </div>
        <div className="mt-3 h-2 overflow-hidden rounded-full bg-surface-base">
          <motion.div
            initial={{ width: 0 }}
            animate={{ width: `${overall}%` }}
            transition={{ duration: 0.8, ease: "easeOut" }}
            className={cx(
              "h-full rounded-full",
              overall >= 85 ? "bg-priority-critical" : overall >= 60 ? "bg-priority-high"
                : overall >= 40 ? "bg-priority-medium" : "bg-priority-low",
            )}
          />
        </div>
      </div>

      {/* GNN sub-scores + model metrics */}
      <div className="mt-3 grid grid-cols-2 gap-2.5 sm:grid-cols-4">
        <Tile label="GNN case risk" value={pct(gnn.case_risk)} icon={<ShieldAlert size={13} />} />
        <Tile label="Subject risk" value={pct(gnn.subject_risk)} icon={<TrendingUp size={13} />} />
        <Tile label="Model F1" value={gnn.model?.test_f1?.toFixed(2) ?? "—"} icon={<Cpu size={13} />} />
        <Tile label="Model PR-AUC" value={gnn.model?.test_pr_auc?.toFixed(2) ?? "—"} icon={<Cpu size={13} />} />
      </div>

      {/* GNNExplainer-lite: top-risk accounts */}
      <div className="mt-3">
        <p className="label mb-1.5">Highest-risk accounts (GNNExplainer-lite)</p>
        <div className="space-y-1.5">
          {gnn.top_risk_accounts?.slice(0, 5).map((a) => (
            <div key={a.account} className="flex items-center gap-2">
              <span className="w-24 font-mono text-[11px] text-ink-muted">…{a.account.slice(-8)}</span>
              <div className="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-base">
                <div className="h-full rounded-full bg-priority-critical/80"
                     style={{ width: `${Math.round(a.score * 100)}%` }} />
              </div>
              <span className="w-9 text-right font-mono text-[11px] text-ink-faint">
                {Math.round(a.score * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>

      <p className="mt-3 text-[11px] text-ink-faint">
        2-layer GCN (from-scratch NumPy) · trained on {gnn.model?.trained_on_accounts} accounts ·
        ROC-AUC {gnn.model?.test_roc_auc?.toFixed(2)} · class-imbalance-aware loss. The GNN score is
        an independent, graph-based signal that corroborates the typology match.
      </p>
    </div>
  );
}

function Tile({ label, value, icon }: { label: string; value: string; icon: JSX.Element }) {
  return (
    <div className="rounded-xl border border-line bg-surface-raised/50 p-3">
      <div className="mb-1 flex items-center gap-1.5 text-ink-faint">
        {icon}
        <span className="label">{label}</span>
      </div>
      <p className="font-mono text-sm font-semibold text-ink">{value}</p>
    </div>
  );
}
