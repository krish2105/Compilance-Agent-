import { motion } from "framer-motion";
import { Network } from "lucide-react";
import { useMemo } from "react";
import type { CaseGraph as CaseGraphType } from "../lib/types";
import { cx } from "../lib/utils";

/**
 * Case transaction-network visualization (SVG node-link diagram).
 * Positions come from the backend's NetworkX spring layout; the subject node is
 * highlighted, laundering-flagged edges are drawn in the danger colour, and node
 * radius scales with degree.
 */
const W = 640;
const H = 420;
const PAD = 40;

export default function CaseGraph({ graph }: { graph: CaseGraphType }) {
  const { nodePos, radius } = useMemo(() => {
    const xs = graph.nodes.map((n) => n.x);
    const ys = graph.nodes.map((n) => n.y);
    const minX = Math.min(...xs, -1);
    const maxX = Math.max(...xs, 1);
    const minY = Math.min(...ys, -1);
    const maxY = Math.max(...ys, 1);
    const sx = (x: number) => PAD + ((x - minX) / (maxX - minX || 1)) * (W - 2 * PAD);
    const sy = (y: number) => PAD + ((y - minY) / (maxY - minY || 1)) * (H - 2 * PAD);
    const nodePos = new Map(graph.nodes.map((n) => [n.id, { x: sx(n.x), y: sy(n.y) }]));
    const maxDeg = Math.max(1, ...graph.nodes.map((n) => n.in_degree + n.out_degree));
    const radius = (n: { in_degree: number; out_degree: number }) =>
      6 + (10 * (n.in_degree + n.out_degree)) / maxDeg;
    return { nodePos, radius };
  }, [graph]);

  const roleColor: Record<string, string> = {
    subject: "rgb(var(--brand))",
    collector: "rgb(var(--critical))",
    distributor: "rgb(var(--accent))",
  };

  const f = graph.features as Record<string, number | string | boolean>;
  const featChips: [string, unknown][] = [
    ["nodes", f.num_nodes],
    ["edges", f.num_edges],
    ["max fan-out", f.max_out_degree],
    ["max fan-in", f.max_in_degree],
    ["cycles", f.num_simple_cycles],
    ["communities", f.num_communities],
    ["reciprocity", f.reciprocity],
  ];

  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <Network size={16} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">Transaction Network (graph analytics)</h3>
        <span className="ml-auto text-[11px] text-ink-faint">NetworkX · spring layout</span>
      </div>

      <div className="mb-3 flex flex-wrap gap-1.5">
        {featChips.map(([k, v]) =>
          v === undefined ? null : (
            <span key={k} className="chip bg-surface-base/70 text-ink-muted">
              {k}: <span className="font-semibold text-ink">{String(v)}</span>
            </span>
          ),
        )}
      </div>

      <div className="overflow-x-auto rounded-xl border border-line bg-surface-base/40">
        <svg viewBox={`0 0 ${W} ${H}`} className="h-auto w-full" style={{ minWidth: 480 }}>
          <defs>
            <marker id="arrow-g" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
              <path d="M0,0 L7,3 L0,6 Z" fill="rgb(var(--ink-faint))" />
            </marker>
            <marker id="arrow-r" markerWidth="8" markerHeight="8" refX="7" refY="3" orient="auto">
              <path d="M0,0 L7,3 L0,6 Z" fill="rgb(var(--critical))" />
            </marker>
          </defs>

          {graph.edges.map((e, i) => {
            const a = nodePos.get(e.source);
            const b = nodePos.get(e.target);
            if (!a || !b) return null;
            const laundering = e.laundering === 1;
            return (
              <motion.line
                key={i}
                initial={{ pathLength: 0, opacity: 0 }}
                animate={{ pathLength: 1, opacity: 0.55 }}
                transition={{ duration: 0.5, delay: Math.min(i * 0.02, 0.4) }}
                x1={a.x}
                y1={a.y}
                x2={b.x}
                y2={b.y}
                stroke={laundering ? "rgb(var(--critical))" : "rgb(var(--line))"}
                strokeWidth={laundering ? 1.6 : 1}
                markerEnd={laundering ? "url(#arrow-r)" : "url(#arrow-g)"}
              />
            );
          })}

          {graph.nodes.map((n, i) => {
            const p = nodePos.get(n.id)!;
            return (
              <motion.g
                key={n.id}
                initial={{ scale: 0, opacity: 0 }}
                animate={{ scale: 1, opacity: 1 }}
                transition={{ delay: Math.min(i * 0.02, 0.4), type: "spring", stiffness: 300 }}
              >
                <circle
                  cx={p.x}
                  cy={p.y}
                  r={radius(n)}
                  fill={roleColor[n.role] ?? "rgb(var(--ink-faint))"}
                  fillOpacity={n.role === "subject" ? 1 : 0.85}
                  stroke={n.role === "subject" ? "rgb(var(--brand))" : "transparent"}
                  strokeWidth={n.role === "subject" ? 3 : 0}
                />
                <text
                  x={p.x}
                  y={p.y + radius(n) + 11}
                  textAnchor="middle"
                  className={cx("font-mono", n.role === "subject" ? "fill-brand" : "fill-ink-faint")}
                  style={{ fontSize: 9 }}
                >
                  {n.label}
                </text>
              </motion.g>
            );
          })}
        </svg>
      </div>

      <div className="mt-2 flex flex-wrap gap-3 text-[11px] text-ink-faint">
        <span className="flex items-center gap-1"><Dot c="brand" /> subject</span>
        <span className="flex items-center gap-1"><Dot c="accent" /> distributor</span>
        <span className="flex items-center gap-1"><Dot c="critical" /> collector</span>
        <span className="flex items-center gap-1">
          <span className="inline-block h-0.5 w-4" style={{ background: "rgb(var(--critical))" }} /> flagged transfer
        </span>
      </div>
    </div>
  );
}

function Dot({ c }: { c: string }) {
  return <span className="inline-block h-2.5 w-2.5 rounded-full" style={{ background: `rgb(var(--${c}))` }} />;
}
