import { AnimatePresence, motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { useUi } from "../lib/store";

/** Single round light/dark toggle — shows the moon in dark mode, the sun in light,
 * with an animated swap. Matches the other header icon buttons. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useUi();
  const dark = theme === "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${dark ? "light" : "dark"} mode`}
      title={`Switch to ${dark ? "light" : "dark"} mode`}
      className="relative flex h-9 w-9 items-center justify-center overflow-hidden rounded-full border border-line bg-surface-raised/70 text-ink-muted transition-colors hover:border-brand/50 hover:text-brand"
    >
      <AnimatePresence mode="wait" initial={false}>
        <motion.span
          key={dark ? "moon" : "sun"}
          initial={{ y: 12, opacity: 0, rotate: -30 }}
          animate={{ y: 0, opacity: 1, rotate: 0 }}
          exit={{ y: -12, opacity: 0, rotate: 30 }}
          transition={{ duration: 0.18 }}
          className="flex items-center justify-center"
        >
          {dark ? <Moon size={16} /> : <Sun size={16} />}
        </motion.span>
      </AnimatePresence>
    </button>
  );
}
