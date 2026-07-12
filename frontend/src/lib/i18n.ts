// Lightweight i18n (EN / AR) with RTL support — no external dependency.
import { create } from "zustand";

export type Lang = "en" | "ar";

type Dict = Record<string, { en: string; ar: string }>;

// Chrome / high-visibility strings. Extend freely — missing keys fall back to EN.
const T: Dict = {
  "app.tagline": { en: "AML / KYC Copilot", ar: "مساعد مكافحة غسل الأموال" },
  "app.subtitle": {
    en: "Multi-agent case investigation · evidence-cited drafts · human-in-the-loop",
    ar: "تحقيق متعدد الوكلاء · مسودات موثقة بالأدلة · بإشراف بشري",
  },
  "nav.cases": { en: "Cases", ar: "الحالات" },
  "nav.dashboard": { en: "Dashboard", ar: "لوحة التحكم" },
  "nav.import": { en: "Import", ar: "استيراد" },
  "nav.team": { en: "Team", ar: "الفريق" },
  "nav.billing": { en: "Billing", ar: "الفوترة" },
  "status.connected": { en: "API connected", ar: "الخدمة متصلة" },
  "status.offline": { en: "API offline", ar: "الخدمة غير متصلة" },
  "action.signout": { en: "Sign out", ar: "تسجيل الخروج" },
  "action.back": { en: "Back", ar: "رجوع" },
  "action.search": { en: "Search…", ar: "بحث…" },
  "cmd.title": { en: "Command palette", ar: "لوحة الأوامر" },
  "cmd.placeholder": { en: "Type a command or search…", ar: "اكتب أمرًا أو ابحث…" },
  "cmd.go": { en: "Go to", ar: "انتقل إلى" },
  "cmd.actions": { en: "Actions", ar: "إجراءات" },
  "cmd.toggleTheme": { en: "Toggle theme", ar: "تبديل المظهر" },
  "cmd.toggleLang": { en: "Switch language (EN/عربى)", ar: "تبديل اللغة (EN/عربى)" },
  "cmd.signout": { en: "Sign out", ar: "تسجيل الخروج" },
  "disclaimer": {
    en: "Portfolio/demo on synthetic data. Not certified compliance software. Every output is a draft requiring human sign-off.",
    ar: "عرض توضيحي على بيانات اصطناعية. ليس برنامج امتثال معتمد. كل مخرج هو مسودة تتطلب موافقة بشرية.",
  },
  "empty.selectCase": { en: "Select a case to investigate", ar: "اختر حالة للتحقيق" },
};

interface I18nState {
  lang: Lang;
  setLang: (l: Lang) => void;
  toggleLang: () => void;
}

function applyLang(lang: Lang) {
  const el = document.documentElement;
  el.lang = lang;
  el.dir = lang === "ar" ? "rtl" : "ltr";
  try {
    localStorage.setItem("ca-lang", lang);
  } catch {
    /* ignore */
  }
}

function initialLang(): Lang {
  try {
    const s = localStorage.getItem("ca-lang");
    if (s === "ar" || s === "en") return s;
  } catch {
    /* ignore */
  }
  return "en";
}

export const useI18n = create<I18nState>((set, get) => ({
  lang: (() => {
    const l = initialLang();
    applyLang(l);
    return l;
  })(),
  setLang: (l) => {
    applyLang(l);
    set({ lang: l });
  },
  toggleLang: () => {
    const next: Lang = get().lang === "en" ? "ar" : "en";
    applyLang(next);
    set({ lang: next });
  },
}));

/** Translate a key for the current language (falls back to EN, then the key). */
export function useT() {
  const lang = useI18n((s) => s.lang);
  return (key: string) => T[key]?.[lang] ?? T[key]?.en ?? key;
}
