export type Role = "admin" | "data_steward" | "data_entry" | "analyst" | "viewer";

export interface NavItem {
  href: string;
  label: string;
  roles: Role[];
}

// Admins can reach everything; composite roles in Keycloak already grant viewer etc.
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

export function rolesFromToken(accessToken: string | undefined): Role[] {
  if (!accessToken) return [];
  try {
    const part = accessToken.split(".")[1] ?? "";
    const json = JSON.parse(atob(part.replace(/-/g, "+").replace(/_/g, "/"))) as { realm_access?: { roles?: string[] } };
    const known: Role[] = ["admin", "data_steward", "data_entry", "analyst", "viewer"];
    return (json.realm_access?.roles ?? []).filter((r): r is Role => (known as string[]).includes(r));
  } catch {
    return [];
  }
}
