import { motion } from "framer-motion";
import {
  ArrowRight,
  BadgeCheck,
  Banknote,
  Globe2,
  ShieldAlert,
  User,
} from "lucide-react";
import type { InvestigationResult, Transaction } from "../lib/types";
import { cx, fmtMoney, fmtNum } from "../lib/utils";

/** Displays the exact evidence (transactions, KYC, computed facts) behind the case. */
export default function EvidenceCitation({ result }: { result: InvestigationResult }) {
  const { evidence } = result;
  const kyc = evidence.subject_kyc;
  const facts = evidence.facts;
  const focalId = result.citations[0];

  const factTiles = [
    { label: "Transactions", value: fmtNum(facts.transaction_count), icon: <Banknote size={14} /> },
    { label: "Aggregate", value: fmtMoney(facts.total_amount, facts.currencies[0]), icon: <Banknote size={14} /> },
    { label: "Max single", value: fmtMoney(facts.max_amount, facts.currencies[0]), icon: <Banknote size={14} /> },
    { label: "Max fan-out", value: String(facts.max_fan_out), icon: <ArrowRight size={14} /> },
    { label: "Max fan-in", value: String(facts.max_fan_in), icon: <ArrowRight size={14} /> },
    { label: "Sub-threshold", value: String(facts.sub_threshold_count), icon: <ShieldAlert size={14} /> },
    { label: "Cross-border", value: String(facts.cross_border_tx), icon: <Globe2 size={14} /> },
    { label: "Layering depth", value: String(facts.layering_depth), icon: <ArrowRight size={14} /> },
  ];

  return (
    <div className="space-y-4">
      {/* KYC profile */}
      <div className="glass p-4">
        <div className="mb-3 flex items-center gap-2">
          <User size={16} className="text-brand" />
          <h3 className="text-sm font-bold text-ink">Subject KYC Profile</h3>
          <span className="ml-auto font-mono text-xs text-ink-faint">{evidence.subject_kyc.account_number}</span>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          <Field label="Name" value={kyc.full_name} />
          <Field
            label="Risk rating"
            value={kyc.risk_rating}
            tone={kyc.risk_rating === "High" ? "danger" : kyc.risk_rating === "Medium" ? "warn" : "ok"}
          />
          <Field label="PEP" value={kyc.pep_flag ? "Yes" : "No"} tone={kyc.pep_flag ? "danger" : undefined} />
          <Field label="Occupation" value={kyc.occupation} />
          <Field label="Residence" value={kyc.residence_country} />
          <Field label="Source of funds" value={kyc.source_of_funds} />
          <Field
            label="Expected monthly vol."
            value={kyc.expected_monthly_volume_aed ? fmtMoney(kyc.expected_monthly_volume_aed) : "—"}
          />
          <Field label="KYC last reviewed" value={kyc.kyc_last_review_date} />
        </div>
      </div>

      {/* Computed facts */}
      <div className="glass p-4">
        <div className="mb-3 flex items-center gap-2">
          <BadgeCheck size={16} className="text-brand" />
          <h3 className="text-sm font-bold text-ink">Computed Behavioural Facts</h3>
          <span className="ml-auto text-[11px] text-ink-faint">deterministic · verifier ground truth</span>
        </div>
        <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-4">
          {factTiles.map((f) => (
            <div key={f.label} className="rounded-xl border border-line bg-surface-raised/50 p-3">
              <div className="mb-1 flex items-center gap-1.5 text-ink-faint">
                {f.icon}
                <span className="label">{f.label}</span>
              </div>
              <p className="font-mono text-sm font-semibold text-ink">{f.value}</p>
            </div>
          ))}
        </div>
        {(facts.sanctioned_jurisdiction || facts.pep_involved || facts.has_cycle) && (
          <div className="mt-3 flex flex-wrap gap-2">
            {facts.sanctioned_jurisdiction && (
              <span className="chip bg-danger/15 text-danger">
                <ShieldAlert size={12} /> Sanctioned/high-risk jurisdiction
              </span>
            )}
            {facts.pep_involved && (
              <span className="chip bg-danger/15 text-danger">
                <ShieldAlert size={12} /> PEP involved
              </span>
            )}
            {facts.has_cycle && (
              <span className="chip bg-warn/15 text-warn">
                <ArrowRight size={12} /> Cyclic flow detected
              </span>
            )}
          </div>
        )}
      </div>

      {/* Transactions table (the citations) */}
      <div className="glass overflow-hidden p-0">
        <div className="flex items-center gap-2 border-b border-line px-4 py-3">
          <Banknote size={16} className="text-brand" />
          <h3 className="text-sm font-bold text-ink">Cited Transactions</h3>
          <span className="ml-auto text-[11px] text-ink-faint">
            {evidence.transactions.length} in case network
          </span>
        </div>
        <div className="max-h-[420px] overflow-auto">
          <table className="w-full text-left text-xs">
            <thead className="sticky top-0 bg-surface-raised/95 backdrop-blur">
              <tr className="text-ink-faint">
                <th className="px-4 py-2 font-semibold">Txn ID</th>
                <th className="px-2 py-2 font-semibold">Date</th>
                <th className="px-2 py-2 font-semibold">Sender → Receiver</th>
                <th className="px-2 py-2 text-right font-semibold">Amount</th>
                <th className="px-2 py-2 font-semibold">Type</th>
              </tr>
            </thead>
            <tbody>
              {evidence.transactions.map((t, i) => (
                <TxRow key={t.transaction_id} t={t} focal={t.transaction_id === focalId} index={i} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

function TxRow({ t, focal, index }: { t: Transaction; focal: boolean; index: number }) {
  const crossBorder = t.sender_bank_location !== t.receiver_bank_location;
  return (
    <motion.tr
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ delay: Math.min(index * 0.015, 0.25) }}
      className={cx(
        "border-t border-line/70",
        focal ? "bg-brand-soft/40" : "hover:bg-surface-overlay/60",
      )}
    >
      <td className="px-4 py-2 font-mono text-[11px] font-semibold text-brand">
        {t.transaction_id}
        {focal && <span className="ml-1.5 chip bg-brand/15 py-0 text-[9px] text-brand">FOCAL</span>}
      </td>
      <td className="px-2 py-2 text-ink-faint">{t.date}</td>
      <td className="px-2 py-2 font-mono text-[11px] text-ink-muted">
        {t.sender_account.slice(0, 8)}… <ArrowRight size={10} className="inline" />{" "}
        {t.receiver_account.slice(0, 8)}…
        {crossBorder && <Globe2 size={11} className="ml-1 inline text-accent" />}
      </td>
      <td className="px-2 py-2 text-right font-mono font-semibold text-ink">
        {fmtMoney(t.amount, t.payment_currency)}
      </td>
      <td className="px-2 py-2 text-ink-muted">{t.payment_type}</td>
    </motion.tr>
  );
}

function Field({
  label,
  value,
  tone,
}: {
  label: string;
  value?: unknown;
  tone?: "danger" | "warn" | "ok";
}) {
  const toneCls =
    tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : tone === "ok" ? "text-ok" : "text-ink";
  return (
    <div>
      <p className="label mb-0.5">{label}</p>
      <p className={cx("text-sm font-medium", toneCls)}>{value ? String(value) : "—"}</p>
    </div>
  );
}
