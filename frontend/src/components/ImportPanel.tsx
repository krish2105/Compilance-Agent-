import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { AlertTriangle, ArrowRight, Download, FileUp, Loader2, Sparkles, Upload } from "lucide-react";
import { useMemo, useState } from "react";
import { ingestRows } from "../lib/api";
import { useUi } from "../lib/store";
import { cx } from "../lib/utils";

const TEMPLATE =
  "transaction_id,timestamp,sender_account,receiver_account,amount,payment_currency,payment_type,sender_bank_location,receiver_bank_location\n" +
  "TX0001,2026-03-01T09:15:00,ACC-1001,ACC-2002,48500,AED,Wire,UAE,UAE\n" +
  "TX0002,2026-03-01T09:40:00,ACC-1001,ACC-3003,49200,AED,Wire,UAE,Iran\n" +
  "TX0003,2026-03-02T11:05:00,ACC-1001,ACC-4004,47800,AED,Cash Deposit,UAE,UAE\n";

// Canonical schema fields + which are required.
const FIELDS: { key: string; label: string; required: boolean }[] = [
  { key: "sender_account", label: "Sender account", required: true },
  { key: "receiver_account", label: "Receiver account", required: true },
  { key: "amount", label: "Amount", required: true },
  { key: "transaction_id", label: "Transaction ID", required: false },
  { key: "timestamp", label: "Timestamp", required: false },
  { key: "payment_currency", label: "Currency", required: false },
  { key: "payment_type", label: "Payment type", required: false },
  { key: "sender_bank_location", label: "Sender country", required: false },
  { key: "receiver_bank_location", label: "Receiver country", required: false },
];

type Row = Record<string, string>;

function parseCsv(text: string): { headers: string[]; rows: Row[] } {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return { headers: [], rows: [] };
  const headers = lines[0].split(",").map((h) => h.trim());
  const rows = lines.slice(1).map((line) => {
    const cells = line.split(",");
    const row: Row = {};
    headers.forEach((h, i) => (row[h] = (cells[i] ?? "").trim()));
    return row;
  });
  return { headers, rows };
}

/** Auto-guess a mapping: match schema keys to header names loosely. */
function autoMap(headers: string[]): Record<string, string> {
  const norm = (s: string) => s.toLowerCase().replace(/[^a-z0-9]/g, "");
  const map: Record<string, string> = {};
  for (const f of FIELDS) {
    const hit = headers.find((h) => {
      const n = norm(h);
      return n === norm(f.key) || n.includes(norm(f.label.replace(" ", ""))) ||
        (f.key === "sender_account" && (n.includes("from") || n.includes("sender"))) ||
        (f.key === "receiver_account" && (n.includes("to") || n.includes("receiver") || n.includes("beneficiary"))) ||
        (f.key === "amount" && (n.includes("amount") || n.includes("value")));
    });
    if (hit) map[f.key] = hit;
  }
  return map;
}

/** Per-tenant ingestion with a column-mapping wizard, preview, validation & dedupe. */
export default function ImportPanel() {
  const { selectCase, setView } = useUi();
  const [step, setStep] = useState<"upload" | "map">("upload");
  const [headers, setHeaders] = useState<string[]>([]);
  const [rows, setRows] = useState<Row[]>([]);
  const [map, setMap] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const [result, setResult] = useState<any | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const loadText = (text: string) => {
    const { headers, rows } = parseCsv(text);
    if (rows.length === 0) {
      setErr("Couldn't parse any rows — need a header row + at least one data row.");
      return;
    }
    setErr(null);
    setHeaders(headers);
    setRows(rows);
    setMap(autoMap(headers));
    setStep("map");
  };

  // Build mapped rows + validation.
  const { mapped, validation } = useMemo(() => {
    const out: Row[] = [];
    const seenTx = new Set<string>();
    let dupes = 0, selfLoops = 0, badAmount = 0, missing = 0;
    for (const r of rows) {
      const m: Row = {};
      for (const f of FIELDS) if (map[f.key]) m[f.key] = r[map[f.key]] ?? "";
      if (!m.sender_account || !m.receiver_account || m.amount === undefined || m.amount === "") {
        missing++;
        continue;
      }
      if (isNaN(Number(String(m.amount).replace(/,/g, "")))) { badAmount++; continue; }
      if (m.sender_account === m.receiver_account) { selfLoops++; continue; }
      const tid = m.transaction_id || `${m.sender_account}-${m.receiver_account}-${m.amount}`;
      if (seenTx.has(tid)) { dupes++; continue; }
      seenTx.add(tid);
      out.push(m);
    }
    return { mapped: out, validation: { dupes, selfLoops, badAmount, missing, kept: out.length } };
  }, [rows, map]);

  const requiredMapped = FIELDS.filter((f) => f.required).every((f) => map[f.key]);

  const mut = useMutation({
    mutationFn: () => ingestRows(mapped, summary || undefined),
    onSuccess: (r) => { setResult(r.case); setErr(null); },
    onError: (e) => setErr((e as Error).message),
  });

  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url; a.download = "complianceagent_transactions_template.csv"; a.click();
    URL.revokeObjectURL(url);
  };
  const reset = () => { setStep("upload"); setRows([]); setHeaders([]); setMap({}); setResult(null); setSummary(""); setErr(null); };

  const inputCls = "rounded-lg border border-line bg-surface-raised/60 px-2 py-1.5 text-xs text-ink focus:border-brand/60 focus:outline-none";

  if (result)
    return (
      <div className="mx-auto max-w-3xl">
        <motion.div initial={{ opacity: 0, y: 10 }} animate={{ opacity: 1, y: 0 }} className="glass border border-ok/40 p-5">
          <div className="mb-2 flex items-center gap-2 text-ok"><Sparkles size={18} /> <span className="font-bold">Case created</span></div>
          <p className="text-sm text-ink-muted">
            <span className="font-mono font-semibold text-ink">{result.case_id}</span> · {result.transaction_count} transactions
            {result.duplicates_dropped > 0 && ` · ${result.duplicates_dropped} dropped`} · priority{" "}
            <span className="font-semibold text-ink">{result.priority}</span>
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button onClick={() => { selectCase(result.case_id); setView("cases"); }} className="btn-brand">
              Investigate now <ArrowRight size={15} />
            </button>
            <button onClick={reset} className="btn-ghost">Import another</button>
          </div>
        </motion.div>
      </div>
    );

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h2 className="flex items-center gap-2 text-base font-extrabold text-ink"><Upload size={18} className="text-brand" /> Import transactions</h2>
        <p className="text-xs text-ink-faint">Upload your own transactions → map the columns → they become a private case that runs the full pipeline.</p>
      </div>

      {step === "upload" ? (
        <div className="glass p-5">
          <div className="mb-3 flex items-center justify-between">
            <h3 className="flex items-center gap-2 text-sm font-bold text-ink"><FileUp size={15} className="text-brand" /> Step 1 · Upload a CSV</h3>
            <button onClick={downloadTemplate} className="btn-ghost text-xs"><Download size={13} /> Template</button>
          </div>
          <label className="flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line py-8 text-sm text-ink-muted transition-colors hover:border-brand/50 hover:bg-brand-soft/20">
            <FileUp size={22} className="text-brand" /> Click to choose a CSV file
            <input type="file" accept=".csv,text/csv" className="hidden"
              onChange={(e) => { const f = e.target.files?.[0]; if (f) f.text().then(loadText); }} />
          </label>
          <p className="mt-3 text-center text-[11px] text-ink-faint">or paste rows below</p>
          <textarea placeholder={TEMPLATE} rows={4} onChange={(e) => e.target.value.trim() && loadText(e.target.value)}
            className="mt-2 w-full rounded-lg border border-line bg-surface-raised/60 p-3 font-mono text-xs text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none" />
          {err && <p className="mt-2 text-xs text-danger">{err}</p>}
        </div>
      ) : (
        <>
          {/* Step 2: mapping wizard */}
          <div className="glass p-5">
            <h3 className="mb-3 text-sm font-bold text-ink">Step 2 · Map your columns ({rows.length} rows detected)</h3>
            <div className="grid gap-2 sm:grid-cols-2">
              {FIELDS.map((f) => (
                <div key={f.key} className="flex items-center justify-between gap-2">
                  <span className="text-xs text-ink-muted">
                    {f.label}{f.required && <span className="text-danger"> *</span>}
                  </span>
                  <select className={inputCls} value={map[f.key] ?? ""} onChange={(e) => setMap({ ...map, [f.key]: e.target.value })}>
                    <option value="">—</option>
                    {headers.map((h) => <option key={h} value={h}>{h}</option>)}
                  </select>
                </div>
              ))}
            </div>
          </div>

          {/* Preview + validation */}
          <div className="glass p-5">
            <h3 className="mb-3 text-sm font-bold text-ink">Step 3 · Preview & validate</h3>
            <div className="mb-3 flex flex-wrap gap-2 text-[11px]">
              <span className="chip bg-ok/15 text-ok">{validation.kept} valid rows</span>
              {validation.dupes > 0 && <span className="chip bg-high/15 text-priority-high">{validation.dupes} duplicates dropped</span>}
              {validation.selfLoops > 0 && <span className="chip bg-high/15 text-priority-high">{validation.selfLoops} self-transfers</span>}
              {validation.badAmount > 0 && <span className="chip bg-danger/15 text-danger">{validation.badAmount} bad amounts</span>}
              {validation.missing > 0 && <span className="chip bg-danger/15 text-danger">{validation.missing} missing fields</span>}
            </div>
            <div className="overflow-x-auto rounded-lg border border-line">
              <table className="w-full text-[11px]">
                <thead className="bg-surface-base/60 text-ink-faint">
                  <tr>{FIELDS.filter((f) => map[f.key]).map((f) => <th key={f.key} className="px-2 py-1.5 text-left font-semibold">{f.label}</th>)}</tr>
                </thead>
                <tbody>
                  {mapped.slice(0, 5).map((r, i) => (
                    <tr key={i} className="border-t border-line">
                      {FIELDS.filter((f) => map[f.key]).map((f) => <td key={f.key} className="px-2 py-1.5 font-mono text-ink-muted">{r[f.key]}</td>)}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {!requiredMapped && (
              <p className="mt-2 flex items-center gap-1.5 text-xs text-danger">
                <AlertTriangle size={13} /> Map all required fields (sender, receiver, amount) to continue.
              </p>
            )}
            <input value={summary} onChange={(e) => setSummary(e.target.value)} placeholder="Optional: alert summary for this case"
              className="mt-3 w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none" />
            {err && <p className="mt-2 text-xs text-danger">{err}</p>}
            <div className="mt-3 flex gap-2">
              <button disabled={!requiredMapped || mapped.length === 0 || mut.isPending} onClick={() => mut.mutate()}
                className={cx("btn-brand", (!requiredMapped || mapped.length === 0) && "opacity-40")}>
                {mut.isPending ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                Analyze {validation.kept} transactions
              </button>
              <button onClick={reset} className="btn-ghost">Start over</button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
