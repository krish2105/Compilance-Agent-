import { AnimatePresence, motion } from "framer-motion";
import { Command, Languages, LogOut, Moon, Search } from "lucide-react";
import { useEffect, useMemo, useRef, useState } from "react";
import { useT } from "../lib/i18n";
import { useI18n } from "../lib/i18n";
import { navFor } from "../lib/nav";
import { useUi } from "../lib/store";
import { cx } from "../lib/utils";

/** Global ⌘K / Ctrl+K command palette. Keyboard-first, accessible. */
export default function CommandPalette() {
  const t = useT();
  const { user, setView, toggleTheme, signOut } = useUi();
  const toggleLang = useI18n((s) => s.toggleLang);
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  // Build the command list.
  const commands = useMemo(() => {
    const nav = navFor(user?.role).map((n) => ({
      id: `go:${n.view}`,
      group: t("cmd.go"),
      label: t(n.key),
      icon: n.icon,
      run: () => setView(n.view),
    }));
    const actions = [
      { id: "theme", group: t("cmd.actions"), label: t("cmd.toggleTheme"), icon: <Moon size={16} />, run: toggleTheme },
      { id: "lang", group: t("cmd.actions"), label: t("cmd.toggleLang"), icon: <Languages size={16} />, run: toggleLang },
      { id: "signout", group: t("cmd.actions"), label: t("cmd.signout"), icon: <LogOut size={16} />, run: signOut },
    ];
    return [...nav, ...actions];
  }, [user?.role, t, setView, toggleTheme, toggleLang, signOut]);

  const filtered = useMemo(() => {
    const needle = q.trim().toLowerCase();
    return needle ? commands.filter((c) => c.label.toLowerCase().includes(needle)) : commands;
  }, [q, commands]);

  // Global open shortcut (⌘K / Ctrl+K) + a custom event so a button can open it too.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setOpen((o) => !o);
      }
      if (e.key === "Escape") setOpen(false);
    };
    const onOpen = () => setOpen(true);
    window.addEventListener("keydown", onKey);
    window.addEventListener("ca:cmdk", onOpen as EventListener);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("ca:cmdk", onOpen as EventListener);
    };
  }, []);

  useEffect(() => {
    if (open) {
      setQ("");
      setActive(0);
      setTimeout(() => inputRef.current?.focus(), 30);
    }
  }, [open]);

  useEffect(() => setActive(0), [q]);

  const runAt = (i: number) => {
    const cmd = filtered[i];
    if (cmd) {
      cmd.run();
      setOpen(false);
    }
  };

  return (
    <AnimatePresence>
      {open && (
        <motion.div
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          exit={{ opacity: 0 }}
          className="fixed inset-0 z-[60] flex items-start justify-center bg-black/40 p-4 pt-[12vh] backdrop-blur-sm"
          onClick={() => setOpen(false)}
        >
          <motion.div
            role="dialog"
            aria-modal="true"
            aria-label={t("cmd.title")}
            initial={{ opacity: 0, y: -12, scale: 0.98 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -8, scale: 0.98 }}
            onClick={(e) => e.stopPropagation()}
            onKeyDown={(e) => {
              if (e.key === "ArrowDown") { e.preventDefault(); setActive((a) => Math.min(a + 1, filtered.length - 1)); }
              if (e.key === "ArrowUp") { e.preventDefault(); setActive((a) => Math.max(a - 1, 0)); }
              if (e.key === "Enter") { e.preventDefault(); runAt(active); }
            }}
            className="glass w-full max-w-lg overflow-hidden p-0 shadow-float"
          >
            <div className="flex items-center gap-2 border-b border-line px-4 py-3">
              <Search size={16} className="text-ink-faint" />
              <input
                ref={inputRef}
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder={t("cmd.placeholder")}
                className="w-full bg-transparent text-sm text-ink placeholder:text-ink-faint focus:outline-none"
                aria-label={t("cmd.placeholder")}
              />
              <kbd className="hidden rounded border border-line px-1.5 py-0.5 text-[10px] text-ink-faint sm:block">
                ESC
              </kbd>
            </div>
            <ul role="listbox" className="max-h-[50vh] overflow-y-auto p-2">
              {filtered.length === 0 && (
                <li className="px-3 py-6 text-center text-sm text-ink-faint">No matches.</li>
              )}
              {filtered.map((c, i) => (
                <li key={c.id} role="option" aria-selected={i === active}>
                  <button
                    onMouseEnter={() => setActive(i)}
                    onClick={() => runAt(i)}
                    className={cx(
                      "flex w-full items-center gap-3 rounded-lg px-3 py-2.5 text-left text-sm transition-colors",
                      i === active ? "bg-brand text-white" : "text-ink-muted hover:bg-surface-overlay",
                    )}
                  >
                    <span className={i === active ? "text-white" : "text-brand"}>{c.icon}</span>
                    <span className="flex-1">{c.label}</span>
                    <span className={cx("text-[10px]", i === active ? "text-white/70" : "text-ink-faint")}>
                      {c.group}
                    </span>
                  </button>
                </li>
              ))}
            </ul>
            <div className="flex items-center gap-3 border-t border-line px-4 py-2 text-[10px] text-ink-faint">
              <Command size={11} /> <span>K to open</span>
              <span className="ml-auto">↑↓ navigate · ↵ select · esc close</span>
            </div>
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>
  );
}
