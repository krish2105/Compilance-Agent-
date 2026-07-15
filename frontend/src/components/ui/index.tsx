// Shared primitives so every screen inherits one rhythm instead of
// re-styling inline. Graphite + emerald, flat surfaces, hairline borders.
import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";
import { riseItem, staggerParent } from "../../lib/motion";
import { cx } from "../../lib/utils";

/* ------------------------------------------------------------------ Card -- */
export function Card({
  children,
  className,
  hover,
  as,
}: {
  children: ReactNode;
  className?: string;
  hover?: boolean;
  as?: "div" | "section" | "article";
}) {
  const Tag = (as ?? "div") as "div";
  return (
    <Tag className={cx("card p-5", hover && "card-hover", className)}>{children}</Tag>
  );
}

/* --------------------------------------------------------- SectionHeader -- */
export function SectionHeader({
  title,
  subtitle,
  icon,
  actions,
  className,
}: {
  title: ReactNode;
  subtitle?: ReactNode;
  icon?: ReactNode;
  actions?: ReactNode;
  className?: string;
}) {
  return (
    <div className={cx("flex items-start justify-between gap-3", className)}>
      <div className="min-w-0">
        <h2 className="flex items-center gap-2 text-[15px] font-bold tracking-tight text-ink">
          {icon && <span className="text-ink-faint">{icon}</span>}
          {title}
        </h2>
        {subtitle && <p className="mt-0.5 text-xs text-ink-faint">{subtitle}</p>}
      </div>
      {actions && <div className="flex shrink-0 items-center gap-2">{actions}</div>}
    </div>
  );
}

/* ------------------------------------------------------------- StatTile -- */
export function StatTile({
  label,
  value,
  hint,
  accent,
  icon,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  hint?: ReactNode;
  accent?: "brand" | "positive" | "warn" | "danger" | "neutral";
  icon?: ReactNode;
  className?: string;
}) {
  const tone =
    accent === "brand"
      ? "text-brand"
      : accent === "positive"
        ? "text-positive"
        : accent === "warn"
          ? "text-warn"
          : accent === "danger"
            ? "text-danger"
            : "text-ink";
  return (
    <div className={cx("card p-4", className)}>
      <div className="flex items-center justify-between">
        <p className="label">{label}</p>
        {icon && <span className="text-ink-faint">{icon}</span>}
      </div>
      <p className={cx("mt-2 font-mono text-2xl font-bold tracking-tight tabular-nums", tone)}>
        {value}
      </p>
      {hint && <p className="mt-1 text-[11px] text-ink-faint">{hint}</p>}
    </div>
  );
}

/* ---------------------------------------------------------------- Badge -- */
type Tone = "neutral" | "brand" | "positive" | "warn" | "danger";
const toneChip: Record<Tone, string> = {
  neutral: "bg-ink-faint/10 text-ink-muted ring-1 ring-inset ring-line",
  brand: "bg-brand/10 text-brand ring-1 ring-inset ring-brand/25",
  positive: "bg-positive/10 text-positive ring-1 ring-inset ring-positive/25",
  warn: "bg-warn/10 text-warn ring-1 ring-inset ring-warn/25",
  danger: "bg-danger/10 text-danger ring-1 ring-inset ring-danger/25",
};
const toneDot: Record<Tone, string> = {
  neutral: "bg-ink-faint",
  brand: "bg-brand",
  positive: "bg-positive",
  warn: "bg-warn",
  danger: "bg-danger",
};

export function Badge({
  children,
  tone = "neutral",
  dot,
  className,
}: {
  children: ReactNode;
  tone?: Tone;
  dot?: boolean;
  className?: string;
}) {
  return (
    <span className={cx("chip", toneChip[tone], className)}>
      {dot && <span className={cx("h-1.5 w-1.5 rounded-full", toneDot[tone])} />}
      {children}
    </span>
  );
}

/* -------------------------------------------------------------- RiskDot -- */
export function RiskDot({ tone = "neutral", className }: { tone?: Tone; className?: string }) {
  return <span className={cx("inline-block h-2 w-2 rounded-full", toneDot[tone], className)} />;
}

/* --------------------------------------------------------------- Reveal -- */
/** Staggered entrance wrapper. Falls back to static when reduced-motion. */
export function Reveal({
  children,
  className,
  stagger = true,
}: {
  children: ReactNode;
  className?: string;
  stagger?: boolean;
}) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div
      className={className}
      variants={stagger ? staggerParent : undefined}
      initial="hidden"
      animate="show"
    >
      {children}
    </motion.div>
  );
}

export function RevealItem({ children, className }: { children: ReactNode; className?: string }) {
  const reduce = useReducedMotion();
  if (reduce) return <div className={className}>{children}</div>;
  return (
    <motion.div className={className} variants={riseItem}>
      {children}
    </motion.div>
  );
}
