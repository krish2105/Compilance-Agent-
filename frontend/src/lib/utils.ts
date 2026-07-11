// Small presentation helpers.
import type { Priority } from "./types";

export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

export function fmtMoney(n: number, currency = "AED"): string {
  return `${currency} ${n.toLocaleString(undefined, {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  })}`;
}

export function fmtNum(n: number): string {
  return n.toLocaleString();
}

export const priorityStyles: Record<Priority, { chip: string; dot: string; label: string }> = {
  Critical: {
    chip: "bg-priority-critical/15 text-priority-critical border border-priority-critical/30",
    dot: "bg-priority-critical",
    label: "Critical",
  },
  High: {
    chip: "bg-priority-high/15 text-priority-high border border-priority-high/30",
    dot: "bg-priority-high",
    label: "High",
  },
  Medium: {
    chip: "bg-priority-medium/15 text-priority-medium border border-priority-medium/30",
    dot: "bg-priority-medium",
    label: "Medium",
  },
  Low: {
    chip: "bg-priority-low/15 text-priority-low border border-priority-low/30",
    dot: "bg-priority-low",
    label: "Low",
  },
};

export function reviewStatusStyle(status: string): string {
  if (status.startsWith("APPROVED")) return "bg-ok/15 text-ok border border-ok/30";
  if (status.startsWith("REJECTED")) return "bg-danger/15 text-danger border border-danger/30";
  if (status.startsWith("EDITED")) return "bg-warn/15 text-warn border border-warn/30";
  if (status.startsWith("ESCALATED")) return "bg-accent/15 text-accent border border-accent/30";
  return "bg-ink-faint/15 text-ink-muted border border-line";
}

export function prettyStatus(status: string): string {
  return status
    .replace(/_/g, " ")
    .toLowerCase()
    .replace(/\b\w/g, (c) => c.toUpperCase());
}

/** Very small, safe-ish Markdown → HTML for the narrative (headings, bold, code, lists, hr, blockquote). */
export function renderMarkdown(md: string): string {
  const esc = (s: string) =>
    s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const lines = md.split("\n");
  let html = "";
  let inUl = false;
  let inOl = false;
  const closeLists = () => {
    if (inUl) {
      html += "</ul>";
      inUl = false;
    }
    if (inOl) {
      html += "</ol>";
      inOl = false;
    }
  };
  const inline = (s: string) =>
    esc(s)
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");

  for (const raw of lines) {
    const line = raw.replace(/\s+$/, "");
    if (/^---+$/.test(line)) {
      closeLists();
      html += "<hr/>";
    } else if (/^>\s?/.test(line)) {
      closeLists();
      html += `<blockquote>${inline(line.replace(/^>\s?/, ""))}</blockquote>`;
    } else if (/^#{1,6}\s/.test(line)) {
      closeLists();
      const level = line.match(/^#+/)![0].length;
      html += `<h${level}>${inline(line.replace(/^#+\s/, ""))}</h${level}>`;
    } else if (/^\s*[-*]\s/.test(line)) {
      if (!inUl) {
        closeLists();
        html += "<ul>";
        inUl = true;
      }
      html += `<li>${inline(line.replace(/^\s*[-*]\s/, ""))}</li>`;
    } else if (/^\s*\d+\.\s/.test(line)) {
      if (!inOl) {
        closeLists();
        html += "<ol>";
        inOl = true;
      }
      html += `<li>${inline(line.replace(/^\s*\d+\.\s/, ""))}</li>`;
    } else if (line.trim() === "") {
      closeLists();
    } else {
      closeLists();
      html += `<p>${inline(line)}</p>`;
    }
  }
  closeLists();
  return html;
}
