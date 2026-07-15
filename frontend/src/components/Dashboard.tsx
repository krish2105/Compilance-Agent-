import { useQuery } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  Activity,
  AlertTriangle,
  ArrowUpRight,
  CheckCircle2,
  Coins,
  FileCheck2,
  Layers,
  Loader2,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingUp,
} from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { getDashboard } from "../lib/api";
import { cx } from "../lib/utils";

/* --------------------------------------------------------------------------
 * Portfolio analytics dashboard
 * Premium, fully responsive, animated. Consumes either the rich server payload
 * or the client-side fallback (see api.getDashboard) — it renders whatever
 * fields are present, so it degrades gracefully without ever dead-ending.
 * ------------------------------------------------------------------------ */

const BAND_TOKEN: Record<string, string> = {
  Critical: "--critical",
  High: "--high",
  Medium: "--medium",
  Low: "--low",
};
const rgb = (token: string, alpha?: number) =>
  alpha == null ? `rgb(var(${token}))` : `rgb(var(${token}) / ${alpha})`;

const prettify = (s: string) =>
  s.replace(/_/g, " ").toLowerCase().replace(/\b\w/g, (c) => c.toUpperCase());

/* ---- animated count-up ---------------------------------------------------- */
function useCountUp(target: number, duration = 900) {
  const [val, setVal] = useState(0);
  const ref = useRef<number>(0);
  useEffect(() => {
    let raf = 0;
    const start = performance.now();
    const from = ref.current;
    const tick = (now: number) => {
      const t = Math.min(1, (now - start) / duration);
      const eased = 1 - Math.pow(1 - t, 3); // easeOutCubic
      const next = from + (target - from) * eased;
      setVal(next);
      if (t < 1) raf = requestAnimationFrame(tick);
      else ref.current = target;
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [target, duration]);
  return val;
}

function Stat({ value, suffix }: { value: number; suffix?: string }) {
  const v = useCountUp(value);
  const display = suffix === "%" ? Math.round(v) : Math.round(v).toLocaleString();
  return (
    <span className="tabular-nums">
      {display}
      {suffix ? <span className="text-lg font-bold text-ink-faint">{suffix}</span> : null}
    </span>
  );
}

/* ---- main ----------------------------------------------------------------- */
export default function Dashboard() {
  const { data, isLoading, isError, refetch, isFetching } = useQuery({
    queryKey: ["dashboard"],
    queryFn: getDashboard,
    staleTime: 60_000,
  });

  if (isLoading) return <DashboardSkeleton />;

  if (isError || !data)
    return (
      <div className="glass flex flex-col items-center gap-3 p-10 text-center">
        <AlertTriangle size={22} className="text-high" />
        <p className="text-sm text-ink-muted">
          Couldn’t reach the case book. Check that the backend is running, then retry.
        </p>
        <button onClick={() => refetch()} className="btn-ghost">
          <RefreshCw size={14} /> Retry
        </button>
      </div>
    );

  const d = data as Record<string, any>;
  const degraded = d.source === "client";

  const tiles = [
    {
      label: "Total cases",
      value: d.total_cases ?? 0,
      icon: <Activity size={17} />,
      token: "--brand",
      sub: `${d.reviewed ?? (d.total_cases ?? 0) - (d.pending_review ?? 0)} reviewed`,
    },
    {
      label: "Critical + High",
      value: d.critical_high ?? 0,
      icon: <AlertTriangle size={17} />,
      token: "--critical",
      sub: "elevated priority",
    },
    {
      label: "Pending review",
      value: d.pending_review ?? 0,
      icon: <FileCheck2 size={17} />,
      token: "--high",
      sub: "awaiting sign-off",
    },
    {
      label: "SAR rate",
      value: Math.round((d.sar_rate ?? 0) * 100),
      suffix: "%",
      icon: <TrendingUp size={17} />,
      token: "--low",
      sub: "filed / escalated",
    },
    d.screening_hit_rate != null
      ? {
          label: "Screening hits",
          value: Math.round((d.screening_hit_rate ?? 0) * 100),
          suffix: "%",
          icon: <ShieldAlert size={17} />,
          token: "--medium",
          sub: "sanctions / PEP",
        }
      : {
          label: "Transactions",
          value: d.total_transactions ?? 0,
          icon: <Coins size={17} />,
          token: "--medium",
          sub: `~${d.avg_transactions ?? 0} / case`,
        },
  ];

  const container = {
    animate: { transition: { staggerChildren: 0.06 } },
  };
  const item = {
    initial: { opacity: 0, y: 14 },
    animate: { opacity: 1, y: 0, transition: { type: "spring", stiffness: 260, damping: 24 } },
  };

  const hasTypologies = Array.isArray(d.top_typologies) && d.top_typologies.length > 0;

  return (
    <div className="min-h-0 space-y-5 overflow-y-auto overflow-x-hidden pb-4 pr-1">
      {/* Header */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 className="flex items-center gap-2 text-base font-extrabold text-ink">
            <Sparkles size={17} className="text-brand" /> Portfolio Analytics
          </h2>
          <p className="text-xs text-ink-faint">Live view across the entire case book</p>
        </div>
        <div className="flex items-center gap-2">
          <AnimatePresence>
            {degraded && (
              <motion.span
                initial={{ opacity: 0, scale: 0.9 }}
                animate={{ opacity: 1, scale: 1 }}
                exit={{ opacity: 0 }}
                className="chip bg-high/10 text-high"
                title="Server analytics endpoint not yet reachable — computed live from the case queue."
              >
                <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-high" /> Queue analytics
              </motion.span>
            )}
          </AnimatePresence>
          <button
            onClick={() => refetch()}
            disabled={isFetching}
            className="btn-ghost"
            title="Refresh"
          >
            <RefreshCw size={14} className={cx(isFetching && "animate-spin")} /> Refresh
          </button>
        </div>
      </div>

      {/* KPI tiles */}
      <motion.div
        variants={container}
        initial="initial"
        animate="animate"
        className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5"
      >
        {tiles.map((t) => (
          <motion.div
            key={t.label}
            variants={item}
            className="group card p-4 transition-colors"
          >
            <div className="mb-3 flex items-center justify-between">
              <span
                className="flex h-8 w-8 items-center justify-center rounded-lg"
                style={{ background: rgb(t.token, 0.12), color: rgb(t.token) }}
              >
                {t.icon}
              </span>
              <ArrowUpRight
                size={13}
                className="text-ink-faint opacity-0 transition-opacity group-hover:opacity-100"
              />
            </div>
            <p className="font-mono text-[26px] font-bold leading-none tracking-tight text-ink">
              <Stat value={t.value} suffix={(t as any).suffix} />
            </p>
            <p className="mt-2 label">{t.label}</p>
            <p className="mt-0.5 text-[11px] text-ink-faint">{t.sub}</p>
          </motion.div>
        ))}
      </motion.div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-3">
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.15 }}
          className="lg:col-span-1"
        >
          <DonutCard title="Priority mix" data={d.by_priority ?? {}} total={d.total_cases ?? 0} />
        </motion.div>
        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.22 }}
          className="lg:col-span-2"
        >
          <BarCard
            title={degraded ? "Risk posture (by priority)" : "Ensemble risk bands"}
            icon={<ShieldAlert size={15} />}
            data={d.risk_bands ?? d.by_priority ?? {}}
            colorByKey
          />
        </motion.div>

        <motion.div
          initial={{ opacity: 0, y: 16 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ delay: 0.29 }}
          className={hasTypologies ? "lg:col-span-1" : "lg:col-span-3"}
        >
          <BarCard
            title="Review dispositions"
            icon={<CheckCircle2 size={15} />}
            data={Object.fromEntries(
              Object.entries(d.dispositions ?? {}).map(([k, v]) => [prettify(k), v as number]),
            )}
          />
        </motion.div>

        {hasTypologies && (
          <motion.div
            initial={{ opacity: 0, y: 16 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ delay: 0.36 }}
            className="lg:col-span-2"
          >
            <TypologyCard rows={d.top_typologies} />
          </motion.div>
        )}
      </div>
    </div>
  );
}

/* ---- donut ---------------------------------------------------------------- */
function DonutCard({
  title,
  data,
  total,
}: {
  title: string;
  data: Record<string, number>;
  total: number;
}) {
  const order = ["Critical", "High", "Medium", "Low"];
  const entries = order
    .filter((k) => data[k])
    .map((k) => [k, data[k]] as [string, number])
    .concat(Object.entries(data).filter(([k]) => !order.includes(k)));
  const sum = entries.reduce((a, [, v]) => a + v, 0) || 1;
  const R = 54;
  const C = 2 * Math.PI * R;
  let offset = 0;

  return (
    <div className="glass h-full p-4">
      <div className="mb-2 flex items-center gap-2">
        <Layers size={15} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">{title}</h3>
      </div>
      <div className="flex items-center gap-5">
        <div className="relative h-[140px] w-[140px] shrink-0">
          <svg viewBox="0 0 140 140" className="h-full w-full -rotate-90">
            <circle cx="70" cy="70" r={R} fill="none" stroke={rgb("--ink-faint", 0.12)} strokeWidth="14" />
            {entries.map(([k, v]) => {
              const frac = v / sum;
              const dash = frac * C;
              const seg = (
                <motion.circle
                  key={k}
                  cx="70"
                  cy="70"
                  r={R}
                  fill="none"
                  stroke={rgb(BAND_TOKEN[k] ?? "--brand")}
                  strokeWidth="14"
                  strokeLinecap="round"
                  strokeDasharray={`${dash} ${C - dash}`}
                  initial={{ strokeDashoffset: C }}
                  animate={{ strokeDashoffset: -offset }}
                  transition={{ duration: 0.9, ease: "easeOut" }}
                />
              );
              offset += dash;
              return seg;
            })}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="font-mono text-2xl font-extrabold text-ink">
              <Stat value={total} />
            </span>
            <span className="label">cases</span>
          </div>
        </div>
        <div className="min-w-0 flex-1 space-y-1.5">
          {entries.map(([k, v]) => (
            <div key={k} className="flex items-center gap-2 text-[12px]">
              <span
                className="h-2.5 w-2.5 shrink-0 rounded-full"
                style={{ background: rgb(BAND_TOKEN[k] ?? "--brand") }}
              />
              <span className="flex-1 truncate text-ink-muted">{k}</span>
              <span className="font-mono font-semibold text-ink">{v}</span>
              <span className="w-9 text-right font-mono text-ink-faint">
                {Math.round((v / sum) * 100)}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ---- animated bars -------------------------------------------------------- */
function BarCard({
  title,
  data,
  colorByKey,
  icon,
}: {
  title: string;
  data: Record<string, number>;
  colorByKey?: boolean;
  icon?: JSX.Element;
}) {
  const entries = Object.entries(data ?? {}).sort((a, b) => b[1] - a[1]);
  const max = Math.max(1, ...entries.map(([, v]) => v));
  return (
    <div className="glass h-full p-4">
      <div className="mb-3 flex items-center gap-2">
        <span className="text-brand">{icon ?? <TrendingUp size={15} />}</span>
        <h3 className="text-sm font-bold text-ink">{title}</h3>
      </div>
      <div className="space-y-2.5">
        {entries.length === 0 && <p className="text-xs text-ink-faint">No data yet.</p>}
        {entries.map(([k, v], i) => {
          const token = colorByKey ? BAND_TOKEN[k] ?? "--brand" : "--brand";
          return (
            <div key={k} className="flex items-center gap-3">
              <span className="w-32 shrink-0 truncate text-[12px] text-ink-muted">{k}</span>
              <div className="relative h-2.5 flex-1 overflow-hidden rounded-full bg-ink-faint/10">
                <motion.div
                  initial={{ width: 0 }}
                  animate={{ width: `${(v / max) * 100}%` }}
                  transition={{ duration: 0.7, delay: i * 0.04, ease: "easeOut" }}
                  className="h-full rounded-full"
                  style={{ background: rgb(token) }}
                />
              </div>
              <span className="w-8 text-right font-mono text-[12px] font-semibold text-ink">{v}</span>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ---- typology leaderboard ------------------------------------------------- */
function TypologyCard({ rows }: { rows: [string, number][] }) {
  const max = Math.max(1, ...rows.map((r) => r[1]));
  return (
    <div className="glass h-full p-4">
      <div className="mb-3 flex items-center gap-2">
        <Layers size={15} className="text-accent" />
        <h3 className="text-sm font-bold text-ink">Top typologies detected</h3>
      </div>
      <div className="space-y-2.5">
        {rows.map(([label, count], i) => (
          <motion.div
            key={label}
            initial={{ opacity: 0, x: -8 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.04 }}
            className="flex items-center gap-3"
          >
            <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-accent/12 font-mono text-[11px] font-bold text-accent">
              {i + 1}
            </span>
            <span className="w-44 shrink-0 truncate text-[12px] text-ink-muted">{label}</span>
            <div className="h-2.5 flex-1 overflow-hidden rounded-full bg-ink-faint/10">
              <motion.div
                initial={{ width: 0 }}
                animate={{ width: `${(count / max) * 100}%` }}
                transition={{ duration: 0.7, delay: i * 0.04, ease: "easeOut" }}
                className="h-full rounded-full"
                style={{ background: rgb("--brand") }}
              />
            </div>
            <span className="w-8 text-right font-mono text-[12px] font-semibold text-ink">{count}</span>
          </motion.div>
        ))}
      </div>
    </div>
  );
}

/* ---- skeleton ------------------------------------------------------------- */
function DashboardSkeleton() {
  return (
    <div className="space-y-5">
      <div className="flex items-center gap-2 text-sm text-ink-muted">
        <Loader2 size={16} className="animate-spin text-brand" /> Computing analytics across the case
        book…
      </div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
        {Array.from({ length: 5 }).map((_, i) => (
          <div key={i} className="h-28 animate-pulse rounded-2xl bg-surface-raised/50" />
        ))}
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        <div className="h-52 animate-pulse rounded-2xl bg-surface-raised/50" />
        <div className="h-52 animate-pulse rounded-2xl bg-surface-raised/50 lg:col-span-2" />
      </div>
    </div>
  );
}
