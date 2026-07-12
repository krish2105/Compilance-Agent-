// Small global UI store (Zustand): theme + auth + currently-selected case.
import { create } from "zustand";

type Theme = "light" | "dark";
export type Role = "analyst" | "mlro" | "admin";
export interface AuthUser {
  username: string;
  role: Role;
  tenant?: { slug: string; name: string };
}

interface UiState {
  theme: Theme;
  toggleTheme: () => void;
  selectedCaseId: string | null;
  selectCase: (id: string | null) => void;
  view: "cases" | "dashboard" | "team";
  setView: (v: "cases" | "dashboard" | "team") => void;
  reviewer: string;
  setReviewer: (name: string) => void;

  // Auth
  token: string | null;
  user: AuthUser | null;
  demoMode: boolean;
  signIn: (token: string, user: AuthUser) => void;
  signOut: () => void;
  enterDemo: () => void;
  enterDemoAs: (username: string, role: Role) => void;
}

function loadUser(): AuthUser | null {
  try {
    const raw = localStorage.getItem("ca-user");
    return raw ? (JSON.parse(raw) as AuthUser) : null;
  } catch {
    return null;
  }
}

function initialTheme(): Theme {
  try {
    const saved = localStorage.getItem("ca-theme");
    if (saved === "light" || saved === "dark") return saved;
  } catch {
    /* ignore */
  }
  return "dark";
}

function applyTheme(theme: Theme) {
  document.documentElement.classList.toggle("dark", theme === "dark");
  try {
    localStorage.setItem("ca-theme", theme);
  } catch {
    /* ignore */
  }
}

export const useUi = create<UiState>((set, get) => ({
  theme: initialTheme(),
  toggleTheme: () => {
    const next: Theme = get().theme === "dark" ? "light" : "dark";
    applyTheme(next);
    set({ theme: next });
  },
  selectedCaseId: null,
  selectCase: (id) => set({ selectedCaseId: id }),
  view: "cases",
  setView: (v) => set({ view: v }),
  reviewer: (() => {
    try {
      return localStorage.getItem("ca-reviewer") || "analyst_kalpana";
    } catch {
      return "analyst_kalpana";
    }
  })(),
  setReviewer: (name) => {
    try {
      localStorage.setItem("ca-reviewer", name);
    } catch {
      /* ignore */
    }
    set({ reviewer: name });
  },

  // ---- Auth ----
  token: (() => {
    try {
      return localStorage.getItem("ca-token");
    } catch {
      return null;
    }
  })(),
  user: loadUser(),
  demoMode: (() => {
    try {
      return localStorage.getItem("ca-demo") === "1";
    } catch {
      return false;
    }
  })(),
  signIn: (token, user) => {
    try {
      localStorage.setItem("ca-token", token);
      localStorage.setItem("ca-user", JSON.stringify(user));
      localStorage.removeItem("ca-demo");
    } catch {
      /* ignore */
    }
    set({ token, user, demoMode: false });
  },
  signOut: () => {
    try {
      localStorage.removeItem("ca-token");
      localStorage.removeItem("ca-user");
      localStorage.removeItem("ca-demo");
    } catch {
      /* ignore */
    }
    set({ token: null, user: null, demoMode: false });
  },
  enterDemo: () => {
    try {
      localStorage.setItem("ca-demo", "1");
      localStorage.removeItem("ca-token");
      localStorage.setItem("ca-user", JSON.stringify({ username: "demo", role: "admin" }));
    } catch {
      /* ignore */
    }
    set({ demoMode: true, token: null, user: { username: "demo", role: "admin" } });
  },
  // Client-side role demo — used when the backend auth endpoint is unavailable
  // (e.g. the hosted backend is a step behind). Uses the X-API-Key lane.
  enterDemoAs: (username, role) => {
    try {
      localStorage.setItem("ca-demo", "1");
      localStorage.removeItem("ca-token");
      localStorage.setItem("ca-user", JSON.stringify({ username, role }));
    } catch {
      /* ignore */
    }
    set({ demoMode: true, token: null, user: { username, role } });
  },
}));
