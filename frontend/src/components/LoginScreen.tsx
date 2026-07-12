import { motion } from "framer-motion";
import { Loader2, LogIn, ShieldHalf, Sparkles } from "lucide-react";
import { useState } from "react";
import { login } from "../lib/api";
import { useUi, type Role } from "../lib/store";

const DEMO: { u: string; p: string; role: Role; label: string }[] = [
  { u: "analyst", p: "analyst123", role: "analyst", label: "analyst — view & edit drafts" },
  { u: "mlro", p: "mlro123", role: "mlro", label: "MLRO — approve / reject / file" },
  { u: "admin", p: "admin123", role: "admin", label: "admin — manage users" },
];

/** Login screen with role-based demo credentials + a skip-to-demo option. */
export default function LoginScreen() {
  const { signIn, enterDemo, enterDemoAs } = useUi();
  const [username, setUsername] = useState("mlro");
  const [password, setPassword] = useState("mlro123");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const { token, user } = await login(username, password);
      signIn(token, user);
    } catch (e) {
      // Graceful fallback: if the backend auth endpoint is unavailable (hosted
      // backend a step behind / waking), sign the known demo accounts in with
      // client-side roles so the RBAC UI still works. Real JWT is used when the
      // backend supports it.
      const demo = DEMO.find((d) => d.u === username && d.p === password);
      if (demo) {
        enterDemoAs(demo.u, demo.role);
        return;
      }
      setErr(
        "Sign-in failed. If this is the hosted demo, the backend may be waking or a " +
          "step behind — use a demo account below, or 'Continue as demo'.",
      );
    } finally {
      setLoading(false);
    }
  };

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
            <p className="text-[11px] text-ink-faint">AML/KYC investigation copilot · role-based access</p>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <div>
            <label className="label mb-1 block">Username</label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2.5 text-sm text-ink focus:border-brand/60 focus:outline-none"
            />
          </div>
          <div>
            <label className="label mb-1 block">Password</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2.5 text-sm text-ink focus:border-brand/60 focus:outline-none"
            />
          </div>
          {err && <p className="text-xs text-danger">{err}</p>}
          <button type="submit" disabled={loading} className="btn-brand w-full">
            {loading ? <Loader2 size={15} className="animate-spin" /> : <LogIn size={15} />}
            Sign in
          </button>
        </form>

        <button onClick={enterDemo} className="btn-ghost mt-2 w-full text-xs">
          <Sparkles size={14} /> Continue as demo (full access)
        </button>

        <div className="mt-4 rounded-xl border border-line bg-surface-base/50 p-3">
          <p className="label mb-1.5">Demo accounts (click to fill)</p>
          <div className="space-y-1.5">
            {DEMO.map((d) => (
              <button
                key={d.u}
                onClick={() => {
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
      </motion.div>
    </div>
  );
}
