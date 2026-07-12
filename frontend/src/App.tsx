import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, ArrowLeft, Command, Languages, LogOut, ShieldHalf, TriangleAlert } from "lucide-react";
import AccountMenu from "./components/AccountMenu";
import BillingPanel from "./components/BillingPanel";
import CaseDetail from "./components/CaseDetail";
import CaseList from "./components/CaseList";
import CommandPalette from "./components/CommandPalette";
import Dashboard from "./components/Dashboard";
import ImportPanel from "./components/ImportPanel";
import LoginScreen from "./components/LoginScreen";
import MobileNav from "./components/MobileNav";
import TeamPanel from "./components/TeamPanel";
import ThemeToggle from "./components/ThemeToggle";
import { useT } from "./lib/i18n";
import { useI18n } from "./lib/i18n";
import { fetchHealth } from "./lib/api";
import { navFor } from "./lib/nav";
import { useUi } from "./lib/store";
import { cx } from "./lib/utils";

export default function App() {
  const t = useT();
  const toggleLang = useI18n((s) => s.toggleLang);
  const lang = useI18n((s) => s.lang);
  const { user, token, demoMode, signOut, view, setView, selectedCaseId, selectCase } = useUi();
  const authed = !!token || demoMode;

  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1, enabled: authed });
  const online = health.isSuccess;
  const provider = (health.data?.llm as { provider?: string } | undefined)?.provider ?? "…";

  if (!authed) return <LoginScreen />;

  const openCmd = () => window.dispatchEvent(new Event("ca:cmdk"));

  return (
    <div className="flex h-[100dvh] flex-col overflow-hidden">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-3 focus:top-3 focus:z-[70] focus:rounded-lg focus:bg-brand focus:px-3 focus:py-2 focus:text-sm focus:text-white"
      >
        Skip to content
      </a>

      {/* Header */}
      <header className="z-20 border-b border-line/70 bg-surface-raised/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1500px] items-center gap-2 px-3 py-2.5 sm:gap-3 sm:px-4 sm:py-3">
          <motion.div
            initial={{ rotate: -12, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl bg-brand text-white shadow-glow sm:h-10 sm:w-10"
          >
            <ShieldHalf size={20} />
          </motion.div>
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-sm font-extrabold tracking-tight text-ink sm:text-base">
              ComplianceAgent
              <span className="chip hidden bg-brand-soft text-brand xs:inline-flex sm:inline-flex">
                {t("app.tagline")}
              </span>
            </h1>
            <p className="hidden text-[11px] text-ink-faint md:block">{t("app.subtitle")}</p>
          </div>

          {/* Desktop nav */}
          <nav
            aria-label="Primary"
            className="ms-4 hidden items-center gap-1 rounded-xl border border-line bg-surface-raised/60 p-1 md:flex"
          >
            {navFor(user?.role).map((it) => (
              <button
                key={it.view}
                onClick={() => setView(it.view)}
                aria-current={view === it.view ? "page" : undefined}
                className={cx(
                  "flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all",
                  view === it.view ? "bg-brand text-white shadow-glow" : "text-ink-muted hover:bg-surface-overlay",
                )}
              >
                {it.icon} {t(it.key)}
              </button>
            ))}
          </nav>

          <div className="ms-auto flex items-center gap-1.5 sm:gap-2.5">
            {/* Command palette trigger */}
            <button
              onClick={openCmd}
              aria-label="Open command palette"
              className="hidden h-9 items-center gap-1.5 rounded-full border border-line bg-surface-raised/70 px-3 text-xs text-ink-faint hover:text-ink sm:flex"
            >
              <Command size={13} /> <kbd className="font-sans">⌘K</kbd>
            </button>
            <span
              className={cx("chip", online ? "bg-ok/15 text-ok" : "bg-danger/15 text-danger")}
              title={online ? "Backend connected" : "Backend unreachable"}
            >
              <Activity size={13} />
              <span className="hidden xs:inline">{online ? t("status.connected") : t("status.offline")}</span>
            </span>
            {online && (
              <span className="chip hidden bg-brand-soft text-brand lg:inline-flex" title="Active LLM provider">
                LLM · {provider}
              </span>
            )}
            <button
              onClick={toggleLang}
              aria-label="Switch language"
              title="English / عربى"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface-raised/70 text-ink-muted hover:text-ink"
            >
              <Languages size={15} />
              <span className="sr-only">{lang}</span>
            </button>
            {user && <AccountMenu />}
            <button
              onClick={signOut}
              aria-label={t("action.signout")}
              title={t("action.signout")}
              className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface-raised/70 text-ink-muted hover:border-danger/50 hover:text-danger"
            >
              <LogOut size={15} />
            </button>
            <ThemeToggle />
          </div>
        </div>

        {/* Disclaimer banner */}
        <div className="flex items-center gap-2 border-t border-warn/20 bg-warn/10 px-3 py-1.5 text-[10px] text-warn sm:px-4 sm:text-[11px]">
          <TriangleAlert size={13} className="shrink-0" />
          <span className="truncate">{t("disclaimer")}</span>
        </div>
      </header>

      {/* Body */}
      {view === "dashboard" ? (
        <main id="main" className="mx-auto w-full max-w-[1500px] flex-1 overflow-y-auto p-3 pb-24 sm:p-4 md:pb-4">
          <Dashboard />
        </main>
      ) : view === "team" ? (
        <main id="main" className="mx-auto w-full max-w-[1500px] flex-1 overflow-y-auto p-3 pb-24 sm:p-4 md:pb-4">
          <TeamPanel />
        </main>
      ) : view === "import" ? (
        <main id="main" className="mx-auto w-full max-w-[1500px] flex-1 overflow-y-auto p-3 pb-24 sm:p-4 md:pb-4">
          <ImportPanel />
        </main>
      ) : view === "billing" ? (
        <main id="main" className="mx-auto w-full max-w-[1500px] flex-1 overflow-y-auto p-3 pb-24 sm:p-4 md:pb-4">
          <BillingPanel />
        </main>
      ) : (
        <main
          id="main"
          className="mx-auto grid w-full max-w-[1500px] flex-1 grid-cols-1 gap-4 overflow-hidden p-3 pb-24 sm:p-4 md:pb-4 lg:grid-cols-[360px_1fr]"
        >
          {/* Case list — full-screen on mobile until a case is picked */}
          <aside
            className={cx(
              "glass min-h-0 flex-col p-3 lg:flex",
              selectedCaseId ? "hidden lg:flex" : "flex",
            )}
          >
            <CaseList />
          </aside>
          {/* Case detail — full-screen on mobile once a case is picked */}
          <section className={cx("min-h-0", selectedCaseId ? "block" : "hidden lg:block")}>
            {selectedCaseId && (
              <button
                onClick={() => selectCase(null)}
                className="mb-3 flex items-center gap-1.5 text-sm font-semibold text-brand lg:hidden"
              >
                <ArrowLeft size={16} /> {t("action.back")}
              </button>
            )}
            <CaseDetail />
          </section>
        </main>
      )}

      <MobileNav />
      <CommandPalette />
    </div>
  );
}
