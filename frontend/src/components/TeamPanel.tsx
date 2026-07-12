import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { CheckCircle2, Loader2, ShieldCheck, UserPlus, Users, XCircle } from "lucide-react";
import { useState } from "react";
import { addUser, listUsers, updateUser, type TeamMember } from "../lib/api";
import { useUi } from "../lib/store";
import { cx } from "../lib/utils";

const ROLES = ["analyst", "mlro", "admin"] as const;
const roleChip: Record<string, string> = {
  admin: "bg-brand-soft text-brand",
  mlro: "bg-priority-high/15 text-priority-high",
  analyst: "bg-priority-medium/15 text-priority-medium",
};

/** Admin-only team management: list org members, add members, change role / active. */
export default function TeamPanel() {
  const { user } = useUi();
  const qc = useQueryClient();
  const isAdmin = user?.role === "admin";

  const { data, isLoading, isError, error } = useQuery({
    queryKey: ["team"],
    queryFn: listUsers,
    enabled: isAdmin,
  });

  const invalidate = () => qc.invalidateQueries({ queryKey: ["team"] });
  const patchMut = useMutation({
    mutationFn: ({ username, patch }: { username: string; patch: { role?: string; active?: boolean } }) =>
      updateUser(username, patch),
    onSuccess: invalidate,
  });

  if (!isAdmin)
    return (
      <div className="glass p-8 text-center">
        <ShieldCheck size={22} className="mx-auto mb-2 text-ink-faint" />
        <p className="text-sm text-ink-muted">
          Team management is available to <span className="font-semibold text-ink">admin</span> users.
        </p>
      </div>
    );

  return (
    <div className="mx-auto max-w-3xl space-y-5">
      <div>
        <h2 className="flex items-center gap-2 text-base font-extrabold text-ink">
          <Users size={18} className="text-brand" /> Team
          {user?.tenant && <span className="chip bg-brand-soft text-brand">{user.tenant.name}</span>}
        </h2>
        <p className="text-xs text-ink-faint">Invite teammates to your organization and manage their roles.</p>
      </div>

      <AddMemberForm onAdded={invalidate} />

      <div className="glass overflow-hidden">
        <div className="flex items-center justify-between border-b border-line px-4 py-3">
          <h3 className="text-sm font-bold text-ink">Members</h3>
          <span className="text-xs text-ink-faint">{data ? `${data.length} total` : "…"}</span>
        </div>
        {isLoading && (
          <div className="flex items-center gap-2 p-4 text-sm text-ink-muted">
            <Loader2 size={15} className="animate-spin text-brand" /> Loading members…
          </div>
        )}
        {isError && <div className="p-4 text-sm text-danger">Failed to load: {(error as Error).message}</div>}
        <div className="divide-y divide-line">
          <AnimatePresence>
            {(data ?? []).map((m) => (
              <MemberRow
                key={m.username}
                m={m}
                isSelf={m.username === user?.username}
                busy={patchMut.isPending}
                onRole={(role) => patchMut.mutate({ username: m.username, patch: { role } })}
                onActive={(active) => patchMut.mutate({ username: m.username, patch: { active } })}
              />
            ))}
          </AnimatePresence>
        </div>
      </div>
    </div>
  );
}

function MemberRow({
  m,
  isSelf,
  busy,
  onRole,
  onActive,
}: {
  m: TeamMember;
  isSelf: boolean;
  busy: boolean;
  onRole: (role: string) => void;
  onActive: (active: boolean) => void;
}) {
  return (
    <motion.div
      layout
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      className="flex flex-wrap items-center gap-3 px-4 py-3"
    >
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-2 text-sm font-semibold text-ink">
          {m.username}
          {isSelf && <span className="chip bg-ink-faint/15 text-ink-faint">you</span>}
          {!m.active && <span className="chip bg-danger/15 text-danger">disabled</span>}
        </p>
        {m.email && <p className="text-[11px] text-ink-faint">{m.email}</p>}
      </div>

      <select
        value={m.role}
        disabled={busy || (isSelf && m.role === "admin")}
        onChange={(e) => onRole(e.target.value)}
        className={cx(
          "rounded-lg border border-line bg-surface-raised/60 px-2 py-1.5 text-xs font-semibold focus:border-brand/60 focus:outline-none",
          roleChip[m.role],
        )}
        title={isSelf ? "You can't remove your own admin role" : "Change role"}
      >
        {ROLES.map((r) => (
          <option key={r} value={r}>
            {r}
          </option>
        ))}
      </select>

      <button
        onClick={() => onActive(!m.active)}
        disabled={busy || (isSelf && m.active)}
        title={isSelf ? "You can't deactivate yourself" : m.active ? "Deactivate" : "Reactivate"}
        className={cx(
          "flex items-center gap-1 rounded-lg px-2.5 py-1.5 text-xs font-semibold transition-colors disabled:opacity-40",
          m.active ? "text-danger hover:bg-danger/10" : "text-ok hover:bg-ok/10",
        )}
      >
        {m.active ? <XCircle size={14} /> : <CheckCircle2 size={14} />}
        {m.active ? "Disable" : "Enable"}
      </button>
    </motion.div>
  );
}

function AddMemberForm({ onAdded }: { onAdded: () => void }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState("analyst");
  const [email, setEmail] = useState("");
  const [msg, setMsg] = useState<{ ok: boolean; text: string } | null>(null);

  const mut = useMutation({
    mutationFn: () => addUser({ username, password, role, email }),
    onSuccess: (r) => {
      setMsg({ ok: true, text: `Added ${r.user.username} (${r.user.role}).` });
      setUsername("");
      setPassword("");
      setEmail("");
      setRole("analyst");
      onAdded();
    },
    onError: (e) => setMsg({ ok: false, text: (e as Error).message }),
  });

  const inputCls =
    "rounded-lg border border-line bg-surface-raised/60 px-3 py-2 text-sm text-ink placeholder:text-ink-faint focus:border-brand/60 focus:outline-none";

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        setMsg(null);
        mut.mutate();
      }}
      className="glass p-4"
    >
      <h3 className="mb-3 flex items-center gap-2 text-sm font-bold text-ink">
        <UserPlus size={15} className="text-brand" /> Add a member
      </h3>
      <div className="grid gap-2 sm:grid-cols-2">
        <input className={inputCls} placeholder="Username" value={username} onChange={(e) => setUsername(e.target.value)} required minLength={3} />
        <input className={inputCls} type="password" placeholder="Temp password (min 6)" value={password} onChange={(e) => setPassword(e.target.value)} required minLength={6} />
        <input className={inputCls} placeholder="Email (optional)" value={email} onChange={(e) => setEmail(e.target.value)} />
        <select className={inputCls} value={role} onChange={(e) => setRole(e.target.value)}>
          {ROLES.map((r) => (
            <option key={r} value={r}>
              {r}
            </option>
          ))}
        </select>
      </div>
      {msg && <p className={cx("mt-2 text-xs", msg.ok ? "text-ok" : "text-danger")}>{msg.text}</p>}
      <button type="submit" disabled={mut.isPending} className="btn-brand mt-3">
        {mut.isPending ? <Loader2 size={15} className="animate-spin" /> : <UserPlus size={15} />}
        Add member
      </button>
    </form>
  );
}
