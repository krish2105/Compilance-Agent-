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

  // Honest confidence: how much the independent signals AGREE + how well-calibrated
  // the GNN is + how decisive the score is (mid-range ~50% = least certain).
  const signals = [
    risk.components.typology_confidence,
    risk.components.gnn_case_risk ?? undefined,
    risk.components.screening_risk ?? undefined,
  ].filter((v): v is number => typeof v === "number");
  const mean = signals.reduce((a, b) => a + b, 0) / (signals.length || 1);
  const spread = Math.sqrt(signals.reduce((a, b) => a + (b - mean) ** 2, 0) / (signals.length || 1));
  const agreement = 1 - Math.min(1, spread * 2); // low spread → high agreement
  const decisiveness = Math.abs(risk.overall_risk - 0.5) * 2; // far from 50% → more certain
  const ece = gnn.model?.test_ece ?? 0.1;
  const calib = 1 - Math.min(1, ece * 5);
  const confidence = Math.max(0.05, Math.min(0.99, 0.5 * agreement + 0.3 * decisiveness + 0.2 * calib));
  const band = Math.round((1 - confidence) * 18); // ± percentage points
  const confLabel = confidence >= 0.7 ? "High" : confidence >= 0.45 ? "Moderate" : "Low";
  const confColor = confidence >= 0.7 ? "text-ok" : confidence >= 0.45 ? "text-priority-high" : "text-danger";

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
        {/* Score bar with a model-uncertainty band */}
        <div className="relative mt-3 h-2 overflow-hidden rounded-full bg-surface-base">
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
          {/* uncertainty band around the point estimate */}
          <div
            className="absolute top-0 h-full bg-ink/10"
            style={{
              left: `${Math.max(0, overall - band)}%`,
              width: `${Math.min(100, overall + band) - Math.max(0, overall - band)}%`,
            }}
            title={`Model uncertainty ±${band}%`}
          />
        </div>
        {/* Honest confidence readout */}
        <div className="mt-2 flex items-center justify-between text-[11px]">
          <span className="text-ink-faint">
            Point estimate <span className="font-mono text-ink">{overall}%</span> · range{" "}
            <span className="font-mono text-ink">
              {Math.max(0, overall - band)}–{Math.min(100, overall + band)}%
            </span>
          </span>
          <span className={cx("font-semibold", confColor)}>
            {confLabel} confidence ({Math.round(confidence * 100)}%)
          </span>
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
        {gnn.model?.architecture} · trained on {gnn.model?.trained_on_accounts} accounts · ROC-AUC{" "}
        {gnn.model?.test_roc_auc?.toFixed(2)}
        {gnn.model?.calibrated && (
          <> · <span className="text-ok">calibrated</span> (Brier {gnn.model?.test_brier?.toFixed(3)}, ECE{" "}
          {gnn.model?.test_ece?.toFixed(3)})</>
        )}
        {gnn.model?.registry_version != null && <> · registry v{gnn.model.registry_version}</>}. An
        independent, graph-based signal that corroborates the typology match.
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
