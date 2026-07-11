// Small global UI store (Zustand): theme + currently-selected case.
import { create } from "zustand";

type Theme = "light" | "dark";

interface UiState {
  theme: Theme;
  toggleTheme: () => void;
  selectedCaseId: string | null;
  selectCase: (id: string | null) => void;
  reviewer: string;
  setReviewer: (name: string) => void;
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
}));
