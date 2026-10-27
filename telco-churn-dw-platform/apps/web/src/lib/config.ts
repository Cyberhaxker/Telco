// Runtime configuration served as /config.json (rendered by the NGINX
// container from environment variables), so one image runs in any environment.
export interface AppConfig {
  apiBase: string;
  environment: string;
}

const FALLBACK: AppConfig = {
  apiBase: "/api/v1",
  environment: "dev",
};

// Build-time overrides for local development without Docker (see scripts/local/README.md).
const ENV_OVERRIDES: Partial<AppConfig> = {
  ...(process.env.NEXT_PUBLIC_API_BASE ? { apiBase: process.env.NEXT_PUBLIC_API_BASE } : {}),
};

let cached: AppConfig | null = null;

export async function loadConfig(): Promise<AppConfig> {
  if (cached) return cached;
  try {
    const res = await fetch("/config.json", { cache: "no-cache" });
    if (res.ok) {
      cached = { ...FALLBACK, ...((await res.json()) as Partial<AppConfig>), ...ENV_OVERRIDES };
      localStorage.setItem("telco.config", JSON.stringify(cached));
      return cached;
    }
  } catch {
    // offline: fall through to the last known config
  }
  try {
    const saved = localStorage.getItem("telco.config");
    if (saved) cached = { ...FALLBACK, ...(JSON.parse(saved) as Partial<AppConfig>), ...ENV_OVERRIDES };
  } catch {
    // storage blocked
  }
  cached ??= { ...FALLBACK, ...ENV_OVERRIDES };
  return cached;
}
