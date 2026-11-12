import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}

export const ROLE_ORDER = ["lead", "developer", "tester", "qa", "security", "optimizer"] as const;

/** Fixed categorical order: a role always gets the same hue, whatever else is on screen. */
export function roleColor(role: string): string {
  const i = ROLE_ORDER.indexOf(role as (typeof ROLE_ORDER)[number]);
  return i === -1 ? "var(--role-other)" : `var(--role-${i + 1})`;
}

export function roleLabel(role: string): string {
  if (role === "qa") return "QA";
  return role.charAt(0).toUpperCase() + role.slice(1);
}
