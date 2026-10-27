export type Role = "admin" | "data_steward" | "data_entry" | "analyst" | "viewer";

export interface NavItem {
  href: string;
  label: string;
  roles: Role[];
}

// Admins can reach everything; the other roles are assigned per user in the app_users table.
export const NAV: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", roles: ["viewer"] },
  { href: "/olap", label: "OLAP explorer", roles: ["analyst"] },
  { href: "/predictions", label: "Predictions", roles: ["analyst"] },
  { href: "/data-entry", label: "Data entry", roles: ["data_entry"] },
  { href: "/uploads", label: "CSV uploads", roles: ["data_entry"] },
  { href: "/sync", label: "Sync", roles: ["data_entry", "data_steward"] },
  { href: "/metadata", label: "Metadata", roles: ["viewer"] },
  { href: "/models", label: "Models", roles: ["analyst"] },
  { href: "/admin", label: "Admin", roles: ["admin", "data_steward"] },
];

export function hasRole(roles: readonly string[], allowed: readonly Role[]): boolean {
  return roles.includes("admin") || allowed.some((r) => roles.includes(r));
}
