import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Check, CreditCard, Loader2, Pencil, ShieldCheck } from "lucide-react";
import { useState } from "react";
import { changePlan, getBilling, renameOrg, type BillingInfo } from "../lib/api";
import { useUi } from "../lib/store";
import { cx } from "../lib/utils";

const ORDER = ["free", "pro", "enterprise"];

/** Admin billing/plan view: current plan, usage vs limits, upgrade, org rename. */
export default function BillingPanel() {
  const { user } = useUi();
  const qc = useQueryClient();
  const isAdmin = user?.role === "admin";
  const { data, isLoading } = useQuery({ queryKey: ["billing"], queryFn: getBilling, enabled: isAdmin });

  const planMut = useMutation({
    mutationFn: (plan: string) => changePlan(plan),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["billing"] }),
  });

  if (!isAdmin)
    return (
      <div className="glass p-8 text-center">
        <ShieldCheck size={22} className="mx-auto mb-2 text-ink-faint" />
        <p className="text-sm text-ink-muted">Billing is available to <span className="font-semibold text-ink">admin</span> users.</p>
      </div>
    );
  if (isLoading || !data)
    return (
      <div className="glass flex items-center gap-2 p-6 text-sm text-ink-muted">
        <Loader2 size={16} className="animate-spin text-brand" /> Loading plan…
      </div>
    );

  const d = data as BillingInfo;

  return (
    <div className="mx-auto max-w-4xl space-y-5">
      <div>
        <h2 className="flex items-center gap-2 text-base font-extrabold text-ink">
          <CreditCard size={18} className="text-brand" /> Plan & Billing
        </h2>
        <p className="text-xs text-ink-faint">Manage your organization’s plan and usage.</p>
      </div>

      <OrgNameCard />

      {/* Usage */}
      <div className="glass p-5">
        <h3 className="mb-3 text-sm font-bold text-ink">
          Current usage · <span className="text-brand">{d.limits.label}</span> plan
        </h3>
        <div className="grid gap-4 sm:grid-cols-2">
          <UsageBar label="Team members" used={d.usage.members} cap={d.limits.max_members} />
          <UsageBar label="Uploaded cases" used={d.usage.uploaded_cases} cap={d.limits.max_uploaded_cases} />
        </div>
      </div>

      {/* Plans */}
      <div className="grid gap-4 md:grid-cols-3">
        {ORDER.map((key) => {
          const p = d.plans[key];
          const current = d.plan === key;
          return (
            <motion.div
              key={key}
              whileHover={{ y: -3 }}
              className={cx("glass flex flex-col p-5", current && "ring-2 ring-brand")}
            >
              <div className="mb-1 flex items-center justify-between">
                <h4 className="text-sm font-bold text-ink">{p.label}</h4>
                {current && <span className="chip bg-brand-soft text-brand">Current</span>}
              </div>
              <p className="mb-3 font-mono text-2xl font-extrabold text-ink">
                ${p.price_usd}
                <span className="text-xs font-normal text-ink-faint">/mo</span>
              </p>
              <ul className="mb-4 space-y-1.5 text-[13px] text-ink-muted">
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-ok" /> {p.max_members ?? "Unlimited"} team members
                </li>
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-ok" /> {p.max_uploaded_cases ?? "Unlimited"} uploaded cases
                </li>
                <li className="flex items-center gap-1.5">
                  <Check size={13} className="text-ok" /> Full multi-agent pipeline
                </li>
              </ul>
              <button
                disabled={current || planMut.isPending}
                onClick={() => planMut.mutate(key)}
                className={cx("mt-auto", current ? "btn-ghost cursor-default" : "btn-brand")}
              >
                {planMut.isPending && planMut.variables === key ? (
                  <Loader2 size={14} className="animate-spin" />
                ) : null}
                {current ? "Active" : ORDER.indexOf(key) > ORDER.indexOf(d.plan) ? "Upgrade" : "Switch"}
              </button>
            </motion.div>
          );
        })}
      </div>
      <p className="text-center text-[11px] text-ink-faint">
        Demo billing — switching plans is instant and free. Wiring real Stripe checkout only needs a
        payment webhook that sets the plan.
      </p>
    </div>
  );
}

function UsageBar({ label, used, cap }: { label: string; used: number; cap: number | null }) {
  const pct = cap ? Math.min(100, (used / cap) * 100) : 15;
  const near = cap ? used / cap >= 0.8 : false;
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-[12px]">
        <span className="text-ink-muted">{label}</span>
        <span className="font-mono text-ink">
          {used} / {cap ?? "∞"}
        </span>
      </div>
      <div className="h-2.5 overflow-hidden rounded-full bg-ink-faint/10">
        <motion.div
          initial={{ width: 0 }}
          animate={{ width: `${pct}%` }}
          transition={{ duration: 0.7 }}
          className={cx("h-full rounded-full", near ? "bg-danger" : "bg-brand")}
        />
      </div>
    </div>
  );
}

function OrgNameCard() {
  const { user, signIn, token } = useUi();
  const qc = useQueryClient();
  const [editing, setEditing] = useState(false);
  const [name, setName] = useState(user?.tenant?.name ?? "");
  const mut = useMutation({
    mutationFn: () => renameOrg(name),
    onSuccess: (r) => {
      if (user && token) signIn(token, { ...user, tenant: r.tenant });
      qc.invalidateQueries({ queryKey: ["billing"] });
      setEditing(false);
    },
  });

  return (
    <div className="glass flex items-center justify-between p-4">
      <div>
        <p className="label mb-0.5">Organization</p>
        {editing ? (
          <input
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-lg border border-line bg-surface-raised/60 px-2 py-1 text-sm text-ink focus:border-brand/60 focus:outline-none"
          />
        ) : (
          <p className="text-sm font-bold text-ink">{user?.tenant?.name}</p>
        )}
      </div>
      {editing ? (
        <div className="flex gap-2">
          <button onClick={() => mut.mutate()} disabled={mut.isPending} className="btn-brand text-xs">
            {mut.isPending ? <Loader2 size={13} className="animate-spin" /> : "Save"}
          </button>
          <button onClick={() => setEditing(false)} className="btn-ghost text-xs">
            Cancel
          </button>
        </div>
      ) : (
        <button onClick={() => setEditing(true)} className="btn-ghost text-xs">
          <Pencil size={13} /> Rename
        </button>
      )}
    </div>
  );
}
