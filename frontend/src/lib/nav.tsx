import { CreditCard, LayoutDashboard, ListChecks, Upload, Users } from "lucide-react";
import type { JSX } from "react";

export type View = "cases" | "dashboard" | "import" | "team" | "billing";

export interface NavItem {
  view: View;
  key: string; // i18n key
  icon: JSX.Element;
  adminOnly?: boolean;
}

export const NAV_ITEMS: NavItem[] = [
  { view: "cases", key: "nav.cases", icon: <ListChecks size={16} /> },
  { view: "dashboard", key: "nav.dashboard", icon: <LayoutDashboard size={16} /> },
  { view: "import", key: "nav.import", icon: <Upload size={16} /> },
  { view: "team", key: "nav.team", icon: <Users size={16} />, adminOnly: true },
  { view: "billing", key: "nav.billing", icon: <CreditCard size={16} />, adminOnly: true },
];

export function navFor(role?: string): NavItem[] {
  return NAV_ITEMS.filter((i) => !i.adminOnly || role === "admin");
}
