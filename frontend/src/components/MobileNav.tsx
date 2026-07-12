import { motion } from "framer-motion";
import { useT } from "../lib/i18n";
import { navFor } from "../lib/nav";
import { useUi } from "../lib/store";
import { cx } from "../lib/utils";

/** Floating bottom navigation for mobile (the top tab bar is desktop-only). */
export default function MobileNav() {
  const t = useT();
  const { user, view, setView } = useUi();
  const items = navFor(user?.role);

  return (
    <nav
      aria-label="Primary"
      className="fixed inset-x-0 bottom-0 z-40 flex justify-center px-3 pb-[max(0.6rem,env(safe-area-inset-bottom))] pt-1 md:hidden"
    >
      <div className="glass flex w-full max-w-md items-center justify-around gap-0.5 rounded-2xl p-1.5 shadow-float">
        {items.map((it) => {
          const activeItem = view === it.view;
          return (
            <button
              key={it.view}
              onClick={() => setView(it.view)}
              aria-current={activeItem ? "page" : undefined}
              aria-label={t(it.key)}
              className={cx(
                "relative flex flex-1 flex-col items-center gap-0.5 rounded-xl px-1 py-1.5 text-[10px] font-semibold transition-colors",
                activeItem ? "text-brand" : "text-ink-faint hover:text-ink-muted",
              )}
            >
              {activeItem && (
                <motion.span
                  layoutId="mobilenav-active"
                  className="absolute inset-0 rounded-xl bg-brand-soft"
                  transition={{ type: "spring", stiffness: 400, damping: 30 }}
                />
              )}
              <span className="relative z-10">{it.icon}</span>
              <span className="relative z-10 leading-none">{t(it.key)}</span>
            </button>
          );
        })}
      </div>
    </nav>
  );
}
