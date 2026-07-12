/**
 * useAgentStream — consumes the backend SSE investigation stream.
 *
 * EventSource cannot attach the X-API-Key header, so we read the SSE response
 * with fetch + a stream reader and parse the `event:`/`data:` frames manually.
 * Emits agent-step events live and captures the terminal `result` payload.
 */
import { useCallback, useRef, useState } from "react";
import { authHeader, streamUrl } from "../lib/api";
import type { AgentStepEvent, InvestigationResult } from "../lib/types";

export type StreamPhase = "idle" | "running" | "done" | "error";

export interface StreamState {
  phase: StreamPhase;
  steps: AgentStepEvent[];
  result: InvestigationResult | null;
  error: string | null;
}

const INITIAL: StreamState = { phase: "idle", steps: [], result: null, error: null };

export function useAgentStream() {
  const [state, setState] = useState<StreamState>(INITIAL);
  const abortRef = useRef<AbortController | null>(null);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    setState(INITIAL);
  }, []);

  const start = useCallback(async (caseId: string) => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setState({ phase: "running", steps: [], result: null, error: null });

    try {
      const res = await fetch(streamUrl(caseId), {
        headers: { ...authHeader(), Accept: "text/event-stream" },
        signal: ctrl.signal,
      });
      if (!res.ok || !res.body) {
        throw new Error(`Stream failed: ${res.status} ${res.statusText}`);
      }

      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = "";

      // Parse SSE frames separated by a blank line.
      const processFrame = (frame: string) => {
        let event = "message";
        const dataLines: string[] = [];
        for (const line of frame.split("\n")) {
          if (line.startsWith("event:")) event = line.slice(6).trim();
          else if (line.startsWith("data:")) dataLines.push(line.slice(5).trim());
        }
        if (dataLines.length === 0) return;
        let data: unknown = null;
        try {
          data = JSON.parse(dataLines.join("\n"));
        } catch {
          return;
        }

        if (event === "agent_step") {
          const step = data as AgentStepEvent;
          setState((s) => ({ ...s, steps: mergeStep(s.steps, step) }));
        } else if (event === "result") {
          setState((s) => ({ ...s, result: data as InvestigationResult }));
        } else if (event === "error") {
          const d = data as { message?: string; detail?: string };
          setState((s) => ({ ...s, phase: "error", error: d.detail || d.message || "error" }));
        } else if (event === "end") {
          setState((s) => (s.phase === "error" ? s : { ...s, phase: "done" }));
        }
      };

      // eslint-disable-next-line no-constant-condition
      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        // Normalize CRLF → LF: sse_starlette separates fields with "\r\n" and
        // frames with "\r\n\r\n", so we split on "\n\n" after normalizing.
        buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, "\n");
        let idx: number;
        while ((idx = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, idx);
          buffer = buffer.slice(idx + 2);
          if (frame.trim()) processFrame(frame);
        }
      }
      if (buffer.trim()) processFrame(buffer);
      setState((s) => (s.phase === "error" ? s : { ...s, phase: "done" }));
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setState((s) => ({ ...s, phase: "error", error: (e as Error).message }));
    }
  }, []);

  return { ...state, start, reset };
}

function mergeStep(steps: AgentStepEvent[], incoming: AgentStepEvent): AgentStepEvent[] {
  // Steps arrive as they complete; append but keep chronological order.
  return [...steps, incoming];
}
