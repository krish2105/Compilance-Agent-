import { useMutation, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import {
  CheckCircle2,
  Gavel,
  Loader2,
  Lock,
  PencilLine,
  ShieldAlert,
  ThumbsDown,
  TriangleAlert,
} from "lucide-react";
import { useState } from "react";
import { submitReview, type ReviewPayload } from "../lib/api";
import { useUi } from "../lib/store";
import type { InvestigationResult, ReviewRecord } from "../lib/types";
import { cx, prettyStatus, reviewStatusStyle } from "../lib/utils";

/**
 * The mandatory, backend-enforced human approval gate.
 * Nothing is finalized until a human submits Approve / Edit / Reject / Escalate.
 */
export default function ApprovalGate({
  caseId,
  result,
  existingReview,
  onEdited,
}: {
  caseId: string;
  result: InvestigationResult;
  existingReview: ReviewRecord | null;
  onEdited: (text: string) => void;
}) {
  const { reviewer, setReviewer } = useUi();
  const qc = useQueryClient();
  const [notes, setNotes] = useState("");
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(result.narrative);

  const mutation = useMutation({
    mutationFn: (payload: ReviewPayload) => submitReview(caseId, payload),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["cases"] });
      qc.invalidateQueries({ queryKey: ["case", caseId] });
      qc.invalidateQueries({ queryKey: ["audit", caseId] });
    },
  });

  const decided = !!existingReview && existingReview.status !== "PENDING_REVIEW";

  const act = (decision: ReviewPayload["decision"], edited?: string) => {
    mutation.mutate({
      decision,
      reviewer: reviewer || "analyst",
      notes: notes || undefined,
      edited_narrative: edited,
    });
  };

  return (
    <div className="glass border-2 border-brand/30 p-4">
      <div className="mb-3 flex items-center gap-2">
        <div className="flex h-9 w-9 items-center justify-center rounded-xl bg-brand text-white shadow-glow">
          <Gavel size={17} />
        </div>
        <div>
          <h3 className="text-sm font-bold text-ink">Human Approval Gate</h3>
          <p className="text-[11px] text-ink-faint">
            Mandatory sign-off — the system never auto-clears or auto-files a case.
          </p>
        </div>
        <span className="ml-auto chip bg-warn/15 text-warn">
          <Lock size={12} /> Enforced
        </span>
      </div>

      {decided ? (
        <motion.div
          initial={{ opacity: 0, scale: 0.98 }}
          animate={{ opacity: 1, scale: 1 }}
          className="rounded-xl border border-line bg-surface-raised/60 p-4"
        >
          <div className="flex items-center gap-2">
            <CheckCircle2 size={18} className="text-ok" />
            <span className={cx("chip", reviewStatusStyle(existingReview!.status))}>
              {prettyStatus(existingReview!.status)}
            </span>
            <span className="text-xs text-ink-faint">
              by {existingReview!.reviewer} · {new Date(existingReview!.ts).toLocaleString()}
            </span>
          </div>
          {existingReview!.notes && (
            <p className="mt-2 text-[13px] text-ink-muted">“{existingReview!.notes}”</p>
          )}
          <button
            className="btn-ghost mt-3 text-xs"
            onClick={() => qc.invalidateQueries({ queryKey: ["case", caseId] })}
          >
            Refresh
          </button>
        </motion.div>
      ) : (
        <>
          <div className="mb-3 grid gap-2 sm:grid-cols-2">
            <div>
              <label className="label mb-1 block">Reviewer</label>
              <input
                value={reviewer}
                onChange={(e) => setReviewer(e.target.value)}
                className="w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-sm text-ink focus:border-brand/60 focus:outline-none"
              />
            </div>
            <div>
              <label className="label mb-1 block">Notes (optional)</label>
              <input
                value={notes}
                onChange={(e) => setNotes(e.target.value)}
                placeholder="Rationale for the decision…"
                className="w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none"
              />
            </div>
          </div>

          <AnimatePresence>
            {editing && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <label className="label mb-1 block">Edit the draft narrative</label>
                <textarea
                  value={draft}
                  onChange={(e) => {
                    setDraft(e.target.value);
                    onEdited(e.target.value);
                  }}
                  rows={10}
                  className="mb-3 w-full rounded-lg border border-line bg-surface-base/70 p-3 font-mono text-[12px] text-ink focus:border-brand/60 focus:outline-none"
                />
              </motion.div>
            )}
          </AnimatePresence>

          <div className="flex flex-wrap gap-2">
            <button
              disabled={mutation.isPending}
              onClick={() => act("APPROVED")}
              className="btn-ok flex-1"
            >
              {mutation.isPending ? <Loader2 size={15} className="animate-spin" /> : <CheckCircle2 size={15} />}
              Approve
            </button>
            {!editing ? (
              <button onClick={() => setEditing(true)} className="btn-ghost flex-1">
                <PencilLine size={15} /> Edit
              </button>
            ) : (
              <button
                disabled={mutation.isPending}
                onClick={() => act("EDITED", draft)}
                className="btn-brand flex-1"
              >
                <PencilLine size={15} /> Save edited draft
              </button>
            )}
            <button
              disabled={mutation.isPending}
              onClick={() => act("ESCALATED")}
              className="btn-ghost flex-1"
            >
              <TriangleAlert size={15} /> Escalate
            </button>
            <button
              disabled={mutation.isPending}
              onClick={() => act("REJECTED")}
              className="btn-danger flex-1"
            >
              <ThumbsDown size={15} /> Reject
            </button>
          </div>

          {mutation.isError && (
            <p className="mt-2 flex items-center gap-1.5 text-xs text-danger">
              <ShieldAlert size={13} /> {(mutation.error as Error).message}
            </p>
          )}
        </>
      )}
    </div>
  );
}
