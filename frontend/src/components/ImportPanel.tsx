import { useMutation } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { ArrowRight, Download, FileUp, Loader2, Sparkles, Upload } from "lucide-react";
import { useRef, useState } from "react";
import { ingestCsv, ingestRows } from "../lib/api";
import { useUi } from "../lib/store";
import { cx } from "../lib/utils";

const TEMPLATE =
  "transaction_id,timestamp,sender_account,receiver_account,amount,payment_currency,payment_type,sender_bank_location,receiver_bank_location\n" +
  "TX0001,2026-03-01T09:15:00,ACC-1001,ACC-2002,48500,AED,Wire,UAE,UAE\n" +
  "TX0002,2026-03-01T09:40:00,ACC-1001,ACC-3003,49200,AED,Wire,UAE,Iran\n" +
  "TX0003,2026-03-02T11:05:00,ACC-1001,ACC-4004,47800,AED,Cash Deposit,UAE,UAE\n";

/** Parse simple CSV text into row objects (header row → keys). */
function parseCsv(text: string): Record<string, string>[] {
  const lines = text.trim().split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) return [];
  const headers = lines[0].split(",").map((h) => h.trim());
  return lines.slice(1).map((line) => {
    const cells = line.split(",");
    const row: Record<string, string> = {};
    headers.forEach((h, i) => (row[h] = (cells[i] ?? "").trim()));
    return row;
  });
}

type Result = { case_id: string; priority: string; transaction_count: number };

/** Per-tenant ingestion: upload a CSV or paste rows → a case that runs the full pipeline. */
export default function ImportPanel() {
  const { selectCase, setView } = useUi();
  const [text, setText] = useState("");
  const [summary, setSummary] = useState("");
  const [result, setResult] = useState<Result | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const pasteMut = useMutation({
    mutationFn: () => ingestRows(parseCsv(text), summary || undefined),
    onSuccess: (r) => {
      setResult(r.case);
      setErr(null);
    },
    onError: (e) => setErr((e as Error).message),
  });
  const fileMut = useMutation({
    mutationFn: (f: File) => ingestCsv(f),
    onSuccess: (r) => {
      setResult(r.case);
      setErr(null);
    },
    onError: (e) => setErr((e as Error).message),
  });
  const busy = pasteMut.isPending || fileMut.isPending;

  const downloadTemplate = () => {
    const url = URL.createObjectURL(new Blob([TEMPLATE], { type: "text/csv" }));
    const a = document.createElement("a");
    a.href = url;
    a.download = "complianceagent_transactions_template.csv";
    a.click();
    URL.revokeObjectURL(url);
  };

  const rowCount = parseCsv(text).length;

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h2 className="flex items-center gap-2 text-base font-extrabold text-ink">
          <Upload size={18} className="text-brand" /> Import transactions
        </h2>
        <p className="text-xs text-ink-faint">
          Upload your own transactions — they become a private case that runs the full
          multi-agent investigation (evidence · GNN · typology · screening · narrative · verify).
        </p>
      </div>

      {result ? (
        <motion.div
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          className="glass border border-ok/40 p-5"
        >
          <div className="mb-2 flex items-center gap-2 text-ok">
            <Sparkles size={18} /> <span className="font-bold">Case created</span>
          </div>
          <p className="text-sm text-ink-muted">
            <span className="font-mono font-semibold text-ink">{result.case_id}</span> ·{" "}
            {result.transaction_count} transactions · priority{" "}
            <span className="font-semibold text-ink">{result.priority}</span>
          </p>
          <div className="mt-4 flex flex-wrap gap-2">
            <button
              onClick={() => {
                selectCase(result.case_id);
                setView("cases");
              }}
              className="btn-brand"
            >
              Investigate now <ArrowRight size={15} />
            </button>
            <button
              onClick={() => {
                setResult(null);
                setText("");
                setSummary("");
              }}
              className="btn-ghost"
            >
              Import another
            </button>
          </div>
        </motion.div>
      ) : (
        <>
          {/* CSV upload */}
          <div className="glass p-5">
            <div className="mb-3 flex items-center justify-between">
              <h3 className="flex items-center gap-2 text-sm font-bold text-ink">
                <FileUp size={15} className="text-brand" /> Upload a CSV
              </h3>
              <button onClick={downloadTemplate} className="btn-ghost text-xs">
                <Download size={13} /> Template
              </button>
            </div>
            <input
              ref={fileRef}
              type="file"
              accept=".csv,text/csv"
              onChange={(e) => {
                const f = e.target.files?.[0];
                if (f) fileMut.mutate(f);
              }}
              className="hidden"
            />
            <button
              onClick={() => fileRef.current?.click()}
              disabled={busy}
              className={cx(
                "flex w-full flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed border-line py-8 text-sm text-ink-muted transition-colors hover:border-brand/50 hover:bg-brand-soft/20",
              )}
            >
              {fileMut.isPending ? (
                <Loader2 size={22} className="animate-spin text-brand" />
              ) : (
                <FileUp size={22} className="text-brand" />
              )}
              Click to choose a CSV file
            </button>
          </div>

          {/* Paste */}
          <div className="glass p-5">
            <h3 className="mb-2 flex items-center gap-2 text-sm font-bold text-ink">
              Or paste rows (CSV)
            </h3>
            <textarea
              value={text}
              onChange={(e) => setText(e.target.value)}
              placeholder={TEMPLATE}
              rows={6}
              className="w-full rounded-lg border border-line bg-surface-raised/60 p-3 font-mono text-xs text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none"
            />
            <input
              value={summary}
              onChange={(e) => setSummary(e.target.value)}
              placeholder="Optional: alert summary for this case"
              className="mt-2 w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none"
            />
            <div className="mt-3 flex items-center gap-3">
              <button onClick={() => pasteMut.mutate()} disabled={busy || rowCount === 0} className="btn-brand">
                {pasteMut.isPending ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                Analyze {rowCount > 0 ? `${rowCount} rows` : ""}
              </button>
              <span className="text-[11px] text-ink-faint">
                Required columns: sender_account, receiver_account, amount
              </span>
            </div>
          </div>

          {err && <p className="text-sm text-danger">{err}</p>}
        </>
      )}
    </div>
  );
}
