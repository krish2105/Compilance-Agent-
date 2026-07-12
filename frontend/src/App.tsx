import { useQuery } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { Activity, LayoutDashboard, ListChecks, LogOut, ShieldHalf, TriangleAlert, UserCircle2 } from "lucide-react";
import CaseDetail from "./components/CaseDetail";
import CaseList from "./components/CaseList";
import Dashboard from "./components/Dashboard";
import LoginScreen from "./components/LoginScreen";
import ThemeToggle from "./components/ThemeToggle";
import { fetchHealth } from "./lib/api";
import { useUi } from "./lib/store";

export default function App() {
  const { user, token, demoMode, signOut, view, setView } = useUi();
  const authed = !!token || demoMode;

  const health = useQuery({ queryKey: ["health"], queryFn: fetchHealth, retry: 1, enabled: authed });
  const online = health.isSuccess;
  const provider =
    (health.data?.llm as { provider?: string } | undefined)?.provider ?? "…";

  if (!authed) return <LoginScreen />;

  const roleColor: Record<string, string> = {
    admin: "bg-brand-soft text-brand",
    mlro: "bg-priority-high/15 text-priority-high",
    analyst: "bg-priority-medium/15 text-priority-medium",
  };

  return (
    <div className="flex h-screen flex-col overflow-hidden">
      {/* Header */}
      <header className="z-20 border-b border-line/70 bg-surface-raised/70 backdrop-blur-xl">
        <div className="mx-auto flex max-w-[1500px] items-center gap-3 px-4 py-3">
          <motion.div
            initial={{ rotate: -12, opacity: 0 }}
            animate={{ rotate: 0, opacity: 1 }}
            className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand text-white shadow-glow"
          >
            <ShieldHalf size={22} />
          </motion.div>
          <div className="min-w-0">
            <h1 className="flex items-center gap-2 text-base font-extrabold tracking-tight text-ink">
              ComplianceAgent
              <span className="chip bg-brand-soft text-brand">AML / KYC Copilot</span>
            </h1>
            <p className="hidden text-[11px] text-ink-faint sm:block">
              Multi-agent case investigation · evidence-cited drafts · human-in-the-loop
            </p>
          </div>

          <div className="ml-4 hidden items-center gap-1 rounded-xl border border-line bg-surface-raised/60 p-1 md:flex">
            {([["cases", "Cases", <ListChecks size={14} />], ["dashboard", "Dashboard", <LayoutDashboard size={14} />]] as const).map(
              ([v, label, icon]) => (
                <button
                  key={v}
                  onClick={() => setView(v)}
                  className={`flex items-center gap-1.5 rounded-lg px-3 py-1.5 text-xs font-semibold transition-all ${
                    view === v ? "bg-brand text-white shadow-glow" : "text-ink-muted hover:bg-surface-overlay"
                  }`}
                >
                  {icon} {label}
                </button>
              ),
            )}
          </div>

          <div className="ml-auto flex items-center gap-2.5">
            <span
              className={`chip ${
                online ? "bg-ok/15 text-ok" : "bg-danger/15 text-danger"
              }`}
              title={online ? "Backend connected" : "Backend unreachable"}
            >
              <Activity size={13} />
              {online ? "API connected" : "API offline"}
            </span>
            {online && (
              <span className="chip hidden bg-brand-soft text-brand sm:inline-flex" title="Active LLM provider">
                LLM · {provider}
              </span>
            )}
            {user && (
              <span
                className={`chip ${roleColor[user.role] ?? "bg-ink-faint/15 text-ink-muted"}`}
                title={`Signed in as ${user.username} (${user.role})`}
              >
                <UserCircle2 size={13} /> {user.username} · {user.role}
                {demoMode ? " (demo)" : ""}
              </span>
            )}
            <button
              onClick={signOut}
              title="Sign out"
              className="flex h-9 w-9 items-center justify-center rounded-full border border-line bg-surface-raised/70 text-ink-muted hover:border-danger/50 hover:text-danger"
            >
              <LogOut size={15} />
            </button>
            <ThemeToggle />
          </div>
        </div>

        {/* Disclaimer banner */}
        <div className="flex items-center gap-2 border-t border-warn/20 bg-warn/10 px-4 py-1.5 text-[11px] text-warn">
          <TriangleAlert size={13} className="shrink-0" />
          <span className="truncate">
            Portfolio/demo on synthetic data. Not certified compliance software. Every output is a
            <strong className="mx-1">draft requiring human sign-off</strong>— nothing is auto-cleared or
            auto-reported.
          </span>
        </div>
      </header>

      {/* Body */}
      {view === "dashboard" ? (
        <main className="mx-auto w-full max-w-[1500px] flex-1 overflow-y-auto p-4">
          <Dashboard />
        </main>
      ) : (
        <main className="mx-auto grid w-full max-w-[1500px] flex-1 grid-cols-1 gap-4 overflow-hidden p-4 lg:grid-cols-[360px_1fr]">
          <aside className="glass hidden min-h-0 flex-col p-3 lg:flex">
            <CaseList />
          </aside>
          {/* Mobile: case list collapses above detail */}
          <aside className="glass min-h-0 p-3 lg:hidden">
            <CaseList />
          </aside>
          <section className="min-h-0">
            <CaseDetail />
          </section>
        </main>
      )}
    </div>
  );
}
