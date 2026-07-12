import { AnimatePresence, motion } from "framer-motion";
import { Building2, Loader2, LogIn, ShieldHalf, Sparkles, UserPlus } from "lucide-react";
import { useState } from "react";
import { login, registerOrg } from "../lib/api";
import { useUi, type Role } from "../lib/store";

const DEMO: { u: string; p: string; role: Role; label: string }[] = [
  { u: "analyst", p: "analyst123", role: "analyst", label: "analyst — view & edit drafts" },
  { u: "mlro", p: "mlro123", role: "mlro", label: "MLRO — approve / reject / file" },
  { u: "admin", p: "admin123", role: "admin", label: "admin — manage users" },
];

type Mode = "signin" | "signup";

/** Login screen: sign in to an organization, create a new one, or skip to the demo. */
export default function LoginScreen() {
  const { signIn, enterDemo, enterDemoAs } = useUi();
  const [mode, setMode] = useState<Mode>("signin");

  // sign-in state
  const [org, setOrg] = useState("demo");
  const [username, setUsername] = useState("mlro");
  const [password, setPassword] = useState("mlro123");

  // sign-up state
  const [orgName, setOrgName] = useState("");
  const [newUser, setNewUser] = useState("");
  const [newPass, setNewPass] = useState("");
  const [email, setEmail] = useState("");

  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submitSignIn = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const { token, user, tenant } = await login(username, password, org || "demo");
      signIn(token, { ...user, tenant });
    } catch {
      // Graceful fallback for the demo org if the backend is waking / a step behind.
      const demo = DEMO.find((d) => d.u === username && d.p === password);
      if ((org === "demo" || !org) && demo) {
        enterDemoAs(demo.u, demo.role);
        return;
      }
      setErr(
        "Sign-in failed. Check the organization, username and password — or use a demo " +
          "account below / 'Continue as demo'.",
      );
    } finally {
      setLoading(false);
    }
  };

  const submitSignUp = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const { token, user, tenant } = await registerOrg({
        org_name: orgName,
        username: newUser,
        password: newPass,
        email,
      });
      signIn(token, { ...user, tenant });
    } catch (e) {
      setErr((e as Error).message || "Could not create the organization.");
    } finally {
      setLoading(false);
    }
  };

  const inputCls =
    "w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2.5 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none focus:ring-2 focus:ring-brand/25";

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <motion.div
        initial={{ opacity: 0, y: 12, scale: 0.98 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        className="glass w-full max-w-md p-6"
      >
        <div className="mb-5 flex items-center gap-3">
          <div className="flex h-11 w-11 items-center justify-center rounded-xl bg-brand text-white shadow-glow">
            <ShieldHalf size={24} />
          </div>
          <div>
            <h1 className="text-lg font-extrabold text-ink">ComplianceAgent</h1>
            <p className="text-[11px] text-ink-faint">
              AML/KYC investigation copilot · multi-tenant SaaS
            </p>
          </div>
        </div>

        {/* Mode toggle */}
        <div className="mb-4 flex gap-1 rounded-xl border border-line bg-surface-base/50 p-1">
          {(["signin", "signup"] as Mode[]).map((m) => (
            <button
              key={m}
              onClick={() => {
                setMode(m);
                setErr(null);
              }}
              className={
                "flex flex-1 items-center justify-center gap-1.5 rounded-lg px-3 py-2 text-xs font-semibold transition-all " +
                (mode === m ? "bg-brand text-white shadow-glow" : "text-ink-muted hover:bg-surface-overlay")
              }
            >
              {m === "signin" ? <LogIn size={13} /> : <Building2 size={13} />}
              {m === "signin" ? "Sign in" : "Create organization"}
            </button>
          ))}
        </div>

        <AnimatePresence mode="wait">
          {mode === "signin" ? (
            <motion.form
              key="signin"
              initial={{ opacity: 0, x: -8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: 8 }}
              onSubmit={submitSignIn}
              className="space-y-3"
            >
              <div>
                <label className="label mb-1 block">Organization</label>
                <input value={org} onChange={(e) => setOrg(e.target.value)} placeholder="demo" className={inputCls} />
              </div>
              <div>
                <label className="label mb-1 block">Username</label>
                <input value={username} onChange={(e) => setUsername(e.target.value)} className={inputCls} />
              </div>
              <div>
                <label className="label mb-1 block">Password</label>
                <input type="password" value={password} onChange={(e) => setPassword(e.target.value)} className={inputCls} />
              </div>
              {err && <p className="text-xs text-danger">{err}</p>}
              <button type="submit" disabled={loading} className="btn-brand w-full">
                {loading ? <Loader2 size={15} className="animate-spin" /> : <LogIn size={15} />}
                Sign in
              </button>
            </motion.form>
          ) : (
            <motion.form
              key="signup"
              initial={{ opacity: 0, x: 8 }}
              animate={{ opacity: 1, x: 0 }}
              exit={{ opacity: 0, x: -8 }}
              onSubmit={submitSignUp}
              className="space-y-3"
            >
              <div>
                <label className="label mb-1 block">Organization name</label>
                <input value={orgName} onChange={(e) => setOrgName(e.target.value)} placeholder="Acme Bank PLC" className={inputCls} required />
              </div>
              <div>
                <label className="label mb-1 block">Admin username</label>
                <input value={newUser} onChange={(e) => setNewUser(e.target.value)} placeholder="jane.doe" className={inputCls} required />
              </div>
              <div>
                <label className="label mb-1 block">Password</label>
                <input type="password" value={newPass} onChange={(e) => setNewPass(e.target.value)} placeholder="min. 6 characters" className={inputCls} required />
              </div>
              <div>
                <label className="label mb-1 block">Email (optional)</label>
                <input value={email} onChange={(e) => setEmail(e.target.value)} placeholder="jane@acme.com" className={inputCls} />
              </div>
              {err && <p className="text-xs text-danger">{err}</p>}
              <button type="submit" disabled={loading} className="btn-brand w-full">
                {loading ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} />}
                Create organization & admin
              </button>
              <p className="text-[11px] text-ink-faint">
                Creates an isolated workspace — your cases & decisions are private to your org.
              </p>
            </motion.form>
          )}
        </AnimatePresence>

        <button onClick={enterDemo} className="btn-ghost mt-2 w-full text-xs">
          <Sparkles size={14} /> Continue as demo (full access)
        </button>

        {mode === "signin" && (
          <div className="mt-4 rounded-xl border border-line bg-surface-base/50 p-3">
            <p className="label mb-1.5">Demo accounts (org “demo” · click to fill)</p>
            <div className="space-y-1.5">
              {DEMO.map((d) => (
                <button
                  key={d.u}
                  onClick={() => {
                    setOrg("demo");
                    setUsername(d.u);
                    setPassword(d.p);
                  }}
                  className="flex w-full items-center justify-between rounded-lg px-2 py-1.5 text-left text-[12px] hover:bg-surface-overlay"
                >
                  <span className="font-mono text-ink">{d.u} / {d.p}</span>
                  <span className="text-ink-faint">{d.label}</span>
                </button>
              ))}
            </div>
          </div>
        )}
      </motion.div>
    </div>
  );
}
