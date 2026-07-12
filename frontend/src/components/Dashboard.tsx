import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, AlertTriangle, FileCheck2, Loader2, PieChart, ShieldAlert } from "lucide-react";
import { getDashboard } from "../lib/api";
import { cx } from "../lib/utils";

const BAND_COLOR: Record<string, string> = {
  Critical: "var(--critical)",
  High: "var(--high)",
  Medium: "var(--medium)",
  Low: "var(--low)",
};

/** Portfolio analytics dashboard — alert volume, dispositions, SAR rate, risk & typology mix. */
export default function Dashboard() {
  const { data, isLoading, isError } = useQuery({ queryKey: ["dashboard"], queryFn: getDashboard });

  if (isLoading)
    return (
      <div className="glass flex items-center gap-2 p-6 text-sm text-ink-muted">
        <Loader2 size={16} className="animate-spin text-brand" /> Computing analytics across the case book…
      </div>
    );
  if (isError || !data) return <div className="glass p-6 text-sm text-danger">Failed to load dashboard.</div>;

  const d = data as Record<string, any>;
  const tiles = [
    { label: "Total cases", value: d.total_cases, icon: <Activity size={16} />, tone: "brand" },
    { label: "Critical + High", value: d.critical_high, icon: <AlertTriangle size={16} />, tone: "high" },
    { label: "Pending review", value: d.pending_review, icon: <FileCheck2 size={16} />, tone: "medium" },
    { label: "SAR rate", value: `${Math.round((d.sar_rate ?? 0) * 100)}%`, icon: <FileCheck2 size={16} />, tone: "ok" },
    { label: "Screening hit rate", value: `${Math.round((d.screening_hit_rate ?? 0) * 100)}%`, icon: <ShieldAlert size={16} />, tone: "critical" },
  ];

  return (
    <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-5">
        {tiles.map((t, i) => (
          <motion.div
            key={t.label}
            initial={{ opacity: 0, y: 10 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: i * 0.05 }}
            className="glass p-4"
          >
            <div className="mb-1.5 flex items-center gap-1.5 text-ink-faint">
              {t.icon}
              <span className="label">{t.label}</span>
            </div>
            <p className="font-mono text-2xl font-extrabold text-ink">{t.value}</p>
          </motion.div>
        ))}
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <BarCard title="Ensemble risk bands" data={d.risk_bands} colorByKey />
        <BarCard title="Alert volume by priority" data={d.by_priority} colorByKey />
        <BarCard
          title="Review dispositions"
          data={Object.fromEntries(
            Object.entries(d.dispositions ?? {}).map(([k, v]) => [prettify(k), v as number]),
          )}
        />
        <TypologyCard rows={d.top_typologies ?? []} />
      </div>
    </div>
  );
}

function prettify(s: string) {
  return s.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());
}

function BarCard({ title, data, colorByKey }: { title: string; data: Record<string, number>; colorByKey?: boolean }) {
  const entries = Object.entries(data ?? {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <PieChart size={15} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">{title}</h3>
      </div>
      <div className="space-y-2">
        {entries.map(([k, v]) => (
          <div key={k} className="flex items-center gap-2">
            <span className="w-28 truncate text-[12px] text-ink-muted">{k}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-surface-base">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${(v / max) * 100}%` }}
                transition={{ duration: 0.7 }}
                className="h-full rounded-full"
                style={{ background: colorByKey ? `rgb(${BAND_COLOR[k] ?? "var(--brand)"})` : "rgb(var(--brand))" }}
              />
            </div>
            <span className="w-8 text-right font-mono text-[11px] text-ink-faint">{v}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function TypologyCard({ rows }: { rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <PieChart size={15} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">Top typologies</h3>
      </div>
      <div className="space-y-2">
        {rows.map(([label, count]) => (
          <div key={label} className="flex items-center gap-2">
            <span className={cx("w-40 truncate text-[12px] text-ink-muted")}>{label}</span>
            <div className="h-3 flex-1 overflow-hidden rounded-full bg-surface-base">
              <div className="h-full rounded-full bg-accent" style={{ width: `${(count / max) * 100}%` }} />
            </div>
            <span className="w-8 text-right font-mono text-[11px] text-ink-faint">{count}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
