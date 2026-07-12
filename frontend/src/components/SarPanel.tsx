import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Clock, Download, FileWarning, Loader2 } from "lucide-react";
import { useState } from "react";
import { downloadSarXml, getSar } from "../lib/api";
import { cx } from "../lib/utils";

/** SAR/STR filing panel: coded activity + filing SLA + goAML XML export. */
export default function SarPanel({ caseId }: { caseId: string }) {
  const { data, isLoading, isError } = useQuery({
    queryKey: ["sar", caseId],
    queryFn: () => getSar(caseId),
  });
  const [downloading, setDownloading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const doDownload = async () => {
    setDownloading(true);
    setErr(null);
    try {
      await downloadSarXml(caseId);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setDownloading(false);
    }
  };

  const sar = data?.sar as Record<string, any> | undefined;
  const sla = data?.sla as Record<string, any> | undefined;
  const activity = sar?.suspicious_activity as Record<string, any> | undefined;

  const slaStyle: Record<string, string> = {
    ON_TIME: "bg-ok/15 text-ok",
    DUE_SOON: "bg-warn/15 text-warn",
    OVERDUE: "bg-danger/15 text-danger",
    PENDING_DETERMINATION: "bg-ink-faint/15 text-ink-muted",
  };

  return (
    <div className="glass p-4">
      <div className="mb-3 flex items-center gap-2">
        <FileWarning size={16} className="text-brand" />
        <h3 className="text-sm font-bold text-ink">SAR / STR Filing (draft)</h3>
        {sla && (
          <span className={cx("chip ml-auto", slaStyle[sla.status as string] ?? "bg-ink-faint/15 text-ink-muted")}>
            <Clock size={12} /> {(sla.status as string).replace(/_/g, " ")}
          </span>
        )}
      </div>

      {isLoading && (
        <div className="flex items-center gap-2 py-4 text-sm text-ink-muted">
          <Loader2 size={15} className="animate-spin" /> Preparing STR…
        </div>
      )}
      {isError && (
        <div className="rounded-lg border border-warn/40 bg-warn/10 px-3 py-2 text-xs text-ink-muted">
          STR generation isn't available from this backend yet. If you're on the hosted demo, the
          backend may be waking (free-tier cold start ~30–60s) or a step behind the frontend — retry
          shortly, or redeploy the latest backend commit.
        </div>
      )}

      {sar && activity && (
        <>
          <div className="grid grid-cols-2 gap-2.5 sm:grid-cols-3">
            <Field label="Report type" value={String(sar.report_type)} />
            <Field label="Activity code" value={String(activity.category_code)} />
            <Field label="Risk band" value={String(activity.risk_band)} tone="danger" />
            <Field label="Subject" value={String((sar.subject as any).name)} />
            <Field label="Amount" value={`${activity.currency} ${Number(activity.total_amount).toLocaleString()}`} />
            <Field label="Transactions" value={String(activity.transaction_count)} />
          </div>

          <div className="mt-3 rounded-lg border-l-4 border-warn/60 bg-warn/10 px-3 py-2 text-xs text-ink-muted">
            <AlertTriangle size={12} className="mr-1 inline text-warn" />
            {String(sar.status)}. {sla?.policy}
            {sla?.deadline ? ` Deadline: ${String(sla.deadline).slice(0, 10)}.` : ""}
          </div>

          {Array.isArray(sar.indicators) && sar.indicators.length > 0 && (
            <div className="mt-3">
              <p className="label mb-1">Coded indicators</p>
              <div className="flex flex-wrap gap-1.5">
                {(sar.indicators as string[]).slice(0, 6).map((ind, i) => (
                  <span key={i} className="chip bg-surface-base/70 text-ink-muted">{ind}</span>
                ))}
              </div>
            </div>
          )}

          <div className="mt-4 flex items-center gap-3">
            <button onClick={doDownload} disabled={downloading} className="btn-brand">
              {downloading ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
              Export goAML XML
            </button>
            <span className="flex items-center gap-1 text-[11px] text-ink-faint">
              <CheckCircle2 size={12} className="text-ok" /> goAML STR schema · UAE FIU / UNODC format
            </span>
          </div>
          {err && <p className="mt-2 text-xs text-danger">{err}</p>}
        </>
      )}
    </div>
  );
}

function Field({ label, value, tone }: { label: string; value: string; tone?: "danger" }) {
  return (
    <div className="rounded-xl border border-line bg-surface-raised/50 p-2.5">
      <p className="label mb-0.5">{label}</p>
      <p className={cx("text-[13px] font-semibold", tone === "danger" ? "text-danger" : "text-ink")}>{value}</p>
    </div>
  );
}
