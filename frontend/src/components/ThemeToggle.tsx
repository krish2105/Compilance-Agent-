import { motion } from "framer-motion";
import { Moon, Sun } from "lucide-react";
import { useUi } from "../lib/store";

/** Animated light/dark toggle with a sliding thumb and clear iconography. */
export default function ThemeToggle() {
  const { theme, toggleTheme } = useUi();
  const dark = theme === "dark";
  return (
    <button
      onClick={toggleTheme}
      aria-label={`Switch to ${dark ? "light" : "dark"} mode`}
      title={`Switch to ${dark ? "light" : "dark"} mode`}
      className="relative flex h-9 w-16 items-center rounded-full border border-line bg-surface-raised/70 px-1 backdrop-blur transition-colors hover:border-brand/50"
    >
      <motion.span
        layout
        transition={{ type: "spring", stiffness: 500, damping: 32 }}
        className="absolute z-10 flex h-7 w-7 items-center justify-center rounded-full bg-brand text-white shadow-glow"
        style={{ left: dark ? 4 : "calc(100% - 1.75rem - 4px)" }}
      >
        {dark ? <Moon size={15} /> : <Sun size={15} />}
      </motion.span>
      <Sun size={14} className="ml-1 text-priority-high/80" />
      <Moon size={14} className="ml-auto mr-1 text-accent/80" />
    </button>
  );
}
