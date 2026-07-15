import { useQuery } from "@tanstack/react-query";
import { ArrowLeft, Command, ShieldHalf } from "lucide-react";
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
import { fetchHealth } from "./lib/api";
import { navFor } from "./lib/nav";
import { useUi } from "./lib/store";
import { cx } from "./lib/utils";

export default function App() {
  const t = useT();
  const { user, token, demoMode, view, setView, selectedCaseId, selectCase } = useUi();
  const authed = !!token || demoMode;

  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1, enabled: authed });
  const online = health.isSuccess;
  const rawProvider = (health.data?.llm as { provider?: string } | undefined)?.provider ?? "…";
  // "offline" is the deterministic-LLM mode name — misleading next to a live dot.
  const provider = rawProvider === "offline" ? "Local" : rawProvider;

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

      {/* Header — one clean row. */}
      <header className="z-20 border-b border-line bg-surface-base/80 backdrop-blur-sm">
        <div className="mx-auto flex h-14 max-w-[1440px] items-center gap-3 px-3 sm:px-5">
          {/* Brand */}
          <div className="flex items-center gap-2.5">
            <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-brand text-white">
              <ShieldHalf size={17} />
            </div>
            <span className="hidden text-[15px] font-bold tracking-tight text-ink sm:inline">
              Compliance<span className="text-ink-muted">Agent</span>
            </span>
          </div>

          {/* Desktop nav — quiet segmented control. */}
          <nav
            aria-label="Primary"
            className="ms-2 hidden items-center gap-0.5 rounded-lg border border-line bg-surface-raised/60 p-0.5 md:flex"
          >
            {navFor(user?.role).map((it) => (
              <button
                key={it.view}
                onClick={() => setView(it.view)}
                aria-current={view === it.view ? "page" : undefined}
                className={cx(
                  "flex items-center gap-1.5 rounded-md px-3 py-1.5 text-[13px] font-medium transition-colors",
                  view === it.view
                    ? "bg-brand text-white"
                    : "text-ink-muted hover:bg-surface-overlay hover:text-ink",
                )}
              >
                {it.icon} {t(it.key)}
              </button>
            ))}
          </nav>

          <div className="ms-auto flex shrink-0 items-center gap-1.5">
            {/* Live status — a single dot, details on hover. */}
            <span
              className="flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1"
              title={
                online
                  ? `${t("status.connected")} · LLM ${provider}`
                  : t("status.offline")
              }
              aria-label={online ? t("status.connected") : t("status.offline")}
            >
              <span className="relative flex h-2 w-2">
                {online && (
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-positive/60" />
                )}
                <span
                  className={cx(
                    "relative inline-flex h-2 w-2 rounded-full",
                    online ? "bg-positive" : "bg-danger",
                  )}
                />
              </span>
              <span className="hidden text-[11px] font-medium text-ink-muted lg:inline">
                {online ? provider : t("status.offline")}
              </span>
            </span>

            {/* Command palette */}
            <button
              onClick={openCmd}
              aria-label="Open command palette"
              className="hidden h-8 items-center gap-1.5 rounded-lg border border-line px-2.5 text-[11px] text-ink-faint transition-colors hover:text-ink lg:flex"
            >
              <Command size={12} /> <kbd className="font-sans">⌘K</kbd>
            </button>

            {user && <AccountMenu />}
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Slim disclaimer strip. */}
      <div className="flex items-center justify-center gap-1.5 border-b border-line bg-surface-raised/40 px-4 py-1 text-[10.5px] text-ink-faint">
        <span className="h-1 w-1 rounded-full bg-warn/70" />
        <span className="truncate">{t("disclaimer")}</span>
      </div>

      {/* Body */}
      {view === "dashboard" ? (
        <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 overflow-y-auto p-4 pb-24 sm:p-6 md:pb-6">
          <Dashboard />
        </main>
      ) : view === "team" ? (
        <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 overflow-y-auto p-4 pb-24 sm:p-6 md:pb-6">
          <TeamPanel />
        </main>
      ) : view === "import" ? (
        <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 overflow-y-auto p-4 pb-24 sm:p-6 md:pb-6">
          <ImportPanel />
        </main>
      ) : view === "billing" ? (
        <main id="main" className="mx-auto w-full max-w-[1440px] flex-1 overflow-y-auto p-4 pb-24 sm:p-6 md:pb-6">
          <BillingPanel />
        </main>
      ) : (
        <main
          id="main"
          className="mx-auto grid w-full max-w-[1440px] flex-1 grid-cols-1 gap-5 overflow-hidden p-4 pb-24 sm:p-6 md:pb-6 lg:grid-cols-[350px_1fr]"
        >
          {/* Case list — full-screen on mobile until a case is picked */}
          <aside
            className={cx(
              "min-h-0 flex-col lg:flex",
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
