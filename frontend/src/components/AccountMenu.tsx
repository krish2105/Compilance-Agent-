import { AnimatePresence, motion } from "framer-motion";
import { KeyRound, Languages, Loader2, LogOut, ShieldCheck, Smartphone, UserCircle2, X } from "lucide-react";
import { useState } from "react";
import { changePassword, mfaDisable, mfaEnable, mfaSetup } from "../lib/api";
import { useI18n, useT } from "../lib/i18n";
import { useUi } from "../lib/store";

/** Header account chip → account modal: password change + language + sign out. */
export default function AccountMenu() {
  const t = useT();
  const toggleLang = useI18n((s) => s.toggleLang);
  const { user, demoMode, setToken, signOut } = useUi();
  const [open, setOpen] = useState(false);
  if (!user) return null;

  const roleColor: Record<string, string> = {
    admin: "bg-brand-soft text-brand",
    mlro: "bg-priority-high/15 text-priority-high",
    analyst: "bg-priority-medium/15 text-priority-medium",
  };

  return (
    <>
      <button
        onClick={() => setOpen(true)}
        aria-label="Account"
        className={`chip ${roleColor[user.role] ?? "bg-ink-faint/15 text-ink-muted"} hover:brightness-110`}
        title={`${user.tenant?.name ? user.tenant.name + " · " : ""}${user.username} · ${user.role}${demoMode ? " (demo)" : ""}`}
      >
        <UserCircle2 size={14} />
        {/* Full label on larger screens; icon-only on mobile to save header space. */}
        <span className="hidden lg:inline">
          {user.tenant && !demoMode ? `${user.tenant.name} · ` : ""}
          {user.username} · {user.role}
          {demoMode ? " (demo)" : ""}
        </span>
        <span className="hidden sm:inline lg:hidden">{user.role}</span>
      </button>

      <AnimatePresence>
        {open && (
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4 backdrop-blur-sm"
            onClick={() => setOpen(false)}
          >
            <motion.div
              initial={{ opacity: 0, y: 12, scale: 0.97 }}
              animate={{ opacity: 1, y: 0, scale: 1 }}
              exit={{ opacity: 0, y: 8, scale: 0.98 }}
              onClick={(e) => e.stopPropagation()}
              className="glass w-full max-w-sm p-5"
            >
              <div className="mb-4 flex items-center justify-between">
                <h3 className="flex items-center gap-2 text-sm font-bold text-ink">
                  <ShieldCheck size={16} className="text-brand" /> Account
                </h3>
                <button onClick={() => setOpen(false)} className="text-ink-faint hover:text-ink">
                  <X size={16} />
                </button>
              </div>
              <p className="mb-4 text-xs text-ink-faint">
                {user.tenant?.name ? `${user.tenant.name} · ` : ""}
                {user.username} ({user.role})
              </p>
              {demoMode ? (
                <p className="rounded-lg bg-surface-base/60 p-3 text-xs text-ink-muted">
                  You’re in the demo session. Sign in with a real organization account to manage
                  your password.
                </p>
              ) : (
                <>
                  <ChangePasswordForm onDone={(tok) => { setToken(tok); setOpen(false); }} />
                  <MfaSection enabled={!!user.mfa_enabled} />
                </>
              )}

              {/* Quick actions (also reachable from the header on desktop). */}
              <div className="mt-4 flex gap-2 border-t border-line pt-4">
                <button
                  onClick={() => { toggleLang(); }}
                  className="btn-ghost flex-1 justify-center text-xs"
                >
                  <Languages size={14} /> EN / عربى
                </button>
                <button
                  onClick={() => { signOut(); setOpen(false); }}
                  className="flex flex-1 items-center justify-center gap-1.5 rounded-lg border border-line px-3 py-2 text-xs font-semibold text-danger hover:bg-danger/10"
                >
                  <LogOut size={14} /> {t("action.signout")}
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </>
  );
}

function ChangePasswordForm({ onDone }: { onDone: (token: string) => void }) {
  const [oldPw, setOldPw] = useState("");
  const [newPw, setNewPw] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [ok, setOk] = useState(false);

  const inputCls =
    "w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none";

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLoading(true);
    setErr(null);
    try {
      const r = await changePassword(oldPw, newPw);
      setOk(true);
      setTimeout(() => onDone(r.token), 700);
    } catch (e) {
      setErr((e as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-2.5">
      <div className="flex items-center gap-1.5 text-xs font-semibold text-ink">
        <KeyRound size={13} className="text-brand" /> Change password
      </div>
      <input className={inputCls} type="password" placeholder="Current password" value={oldPw} onChange={(e) => setOldPw(e.target.value)} required />
      <input className={inputCls} type="password" placeholder="New password (min 8, mixed)" value={newPw} onChange={(e) => setNewPw(e.target.value)} required minLength={8} />
      {err && <p className="text-xs text-danger">{err}</p>}
      {ok && <p className="text-xs text-ok">Password updated — other sessions signed out.</p>}
      <button type="submit" disabled={loading} className="btn-brand w-full">
        {loading ? <Loader2 size={14} className="animate-spin" /> : <KeyRound size={14} />}
        Update password
      </button>
      <p className="text-[11px] text-ink-faint">Changing your password signs out all other sessions.</p>
    </form>
  );
}

function MfaSection({ enabled }: { enabled: boolean }) {
  const [on, setOn] = useState(enabled);
  const [phase, setPhase] = useState<"idle" | "setup">("idle");
  const [secret, setSecret] = useState("");
  const [uri, setUri] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  const inputCls =
    "w-full rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-center font-mono tracking-[0.3em] text-sm text-ink focus:border-brand/60 focus:outline-none";

  const beginSetup = async () => {
    setBusy(true); setMsg(null);
    try {
      const r = await mfaSetup();
      setSecret(r.secret); setUri(r.otpauth_uri); setPhase("setup");
    } catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  const confirm = async () => {
    setBusy(true); setMsg(null);
    try { await mfaEnable(code); setOn(true); setPhase("idle"); setCode(""); }
    catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };
  const disable = async () => {
    const c = window.prompt("Enter a current 6-digit code to turn off 2FA:");
    if (!c) return;
    setBusy(true); setMsg(null);
    try { await mfaDisable(c.trim()); setOn(false); }
    catch (e) { setMsg((e as Error).message); } finally { setBusy(false); }
  };

  return (
    <div className="mt-4 border-t border-line pt-4">
      <div className="mb-2 flex items-center justify-between">
        <span className="flex items-center gap-1.5 text-xs font-semibold text-ink">
          <Smartphone size={13} className="text-brand" /> Two-factor authentication
        </span>
        <span className={`chip ${on ? "bg-ok/15 text-ok" : "bg-ink-faint/15 text-ink-faint"}`}>
          {on ? "Enabled" : "Off"}
        </span>
      </div>

      {phase === "setup" ? (
        <div className="space-y-2">
          <p className="text-[11px] text-ink-faint">
            Add this key to your authenticator app (Google Authenticator, Authy, 1Password), then enter the code:
          </p>
          <code className="block break-all rounded-lg bg-surface-base/60 p-2 text-center font-mono text-xs text-ink">
            {secret}
          </code>
          <a href={uri} className="block text-center text-[11px] text-brand underline">Open in authenticator app</a>
          <input className={inputCls} inputMode="numeric" placeholder="123456"
            value={code} onChange={(e) => setCode(e.target.value.replace(/\D/g, "").slice(0, 6))} />
          <button onClick={confirm} disabled={busy || code.length < 6} className="btn-brand w-full">
            {busy ? <Loader2 size={14} className="animate-spin" /> : null} Verify & enable
          </button>
        </div>
      ) : on ? (
        <button onClick={disable} disabled={busy} className="btn-ghost w-full text-xs">
          Turn off 2FA
        </button>
      ) : (
        <button onClick={beginSetup} disabled={busy} className="btn-brand w-full">
          {busy ? <Loader2 size={14} className="animate-spin" /> : <Smartphone size={14} />} Enable 2FA
        </button>
      )}
      {msg && <p className="mt-1.5 text-xs text-danger">{msg}</p>}
    </div>
  );
}
