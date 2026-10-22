// Runtime configuration served as /config.json (rendered by the NGINX
// container from environment variables), so one image runs in any environment.
export interface AppConfig {
  keycloakUrl: string;
  realm: string;
  clientId: string;
  apiBase: string;
  environment: string;
}

const FALLBACK: AppConfig = {
  keycloakUrl: "http://localhost:8081",
  realm: "telco",
  clientId: "telco-pwa",
  apiBase: "/api/v1",
  environment: "dev",
};

let cached: AppConfig | null = null;

export async function loadConfig(): Promise<AppConfig> {
  if (cached) return cached;
  try {
    const res = await fetch("/config.json", { cache: "no-cache" });
    if (res.ok) {
      cached = { ...FALLBACK, ...((await res.json()) as Partial<AppConfig>) };
      localStorage.setItem("telco.config", JSON.stringify(cached));
      return cached;
    }
  } catch {
    // offline: fall through to the last known config
  }
  try {
    const saved = localStorage.getItem("telco.config");
    if (saved) cached = { ...FALLBACK, ...(JSON.parse(saved) as Partial<AppConfig>) };
  } catch {
    // storage blocked
  }
  cached ??= FALLBACK;
  return cached;
}
