import { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { cx } from "../lib/utils";

const MIN = 300;
const MAX = 620;
const KEY = "ca-queue-w";
const DEFAULT = 360;

function loadWidth(): number {
  try {
    const v = Number(localStorage.getItem(KEY));
    if (v >= MIN && v <= MAX) return v;
  } catch {
    /* ignore */
  }
  return DEFAULT;
}
const clamp = (n: number) => Math.max(MIN, Math.min(MAX, n));

/**
 * Two-pane layout with a draggable divider between `left` and `right`.
 * The left width is user-adjustable (pointer drag or keyboard) and persisted.
 * Pointer/keyboard driven, `role="separator"` — accessible and reduced-motion safe.
 */
export default function ResizableSplit({
  left,
  right,
  className,
}: {
  left: ReactNode;
  right: ReactNode;
  className?: string;
}) {
  const [width, setWidth] = useState(loadWidth);
  const [dragging, setDragging] = useState(false);
  const widthRef = useRef(width);
  widthRef.current = width;

  const persist = useCallback((w: number) => {
    try {
      localStorage.setItem(KEY, String(Math.round(w)));
    } catch {
      /* ignore */
    }
  }, []);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      const startX = e.clientX;
      const startW = widthRef.current;
      setDragging(true);
      document.body.style.cursor = "col-resize";
      document.body.style.userSelect = "none";

      const onMove = (ev: PointerEvent) => setWidth(clamp(startW + (ev.clientX - startX)));
      const onUp = () => {
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
        document.body.style.cursor = "";
        document.body.style.userSelect = "";
        setDragging(false);
        persist(widthRef.current);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [persist],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      let next: number | null = null;
      if (e.key === "ArrowLeft") next = widthRef.current - 24;
      else if (e.key === "ArrowRight") next = widthRef.current + 24;
      else if (e.key === "Home") next = MIN;
      else if (e.key === "End") next = MAX;
      if (next != null) {
        e.preventDefault();
        const w = clamp(next);
        setWidth(w);
        persist(w);
      }
    },
    [persist],
  );

  // Double-click resets to the default width.
  const reset = useCallback(() => {
    setWidth(DEFAULT);
    persist(DEFAULT);
  }, [persist]);

  // Keep width in range if the token bounds ever change on mount.
  useEffect(() => setWidth((w) => clamp(w)), []);

  return (
    <div
      className={cx("grid min-h-0", className)}
      style={{ gridTemplateColumns: `${width}px 14px minmax(0,1fr)` }}
    >
      <div className="min-h-0 overflow-hidden">{left}</div>

      {/* Divider */}
      <div
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize case queue"
        aria-valuenow={Math.round(width)}
        aria-valuemin={MIN}
        aria-valuemax={MAX}
        tabIndex={0}
        onPointerDown={onPointerDown}
        onKeyDown={onKeyDown}
        onDoubleClick={reset}
        title="Drag to resize · double-click to reset"
        className="group relative flex cursor-col-resize items-center justify-center focus:outline-none"
      >
        {/* hairline */}
        <span
          className={cx(
            "absolute inset-y-0 left-1/2 w-px -translate-x-1/2 transition-colors",
            dragging ? "bg-brand" : "bg-line group-hover:bg-brand/50 group-focus-visible:bg-brand",
          )}
        />
        {/* grab handle */}
        <span
          className={cx(
            "relative h-9 w-1 rounded-full transition-all",
            dragging
              ? "bg-brand"
              : "bg-ink-faint/30 group-hover:h-12 group-hover:bg-brand/70 group-focus-visible:bg-brand",
          )}
        />
      </div>

      <div className="min-h-0 overflow-hidden">{right}</div>
    </div>
  );
}
