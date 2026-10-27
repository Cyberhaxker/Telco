// API client: bearer token, RFC 9457 problem parsing, and an IndexedDB fallback
// (analytics_cache) so GET results stay viewable offline.
import { loadConfig } from "./config";
import { db } from "./db";

export class ApiError extends Error {
  constructor(
    public status: number,
    public title: string,
    public detail: string | undefined,
    public body: Record<string, unknown> = {},
  ) {
    super(detail ?? title);
  }
}

export interface CachedResult<T> {
  data: T;
  fromCache: boolean;
  fetchedAt: string;
}

type TokenFn = () => Promise<string | null>;

async function request(path: string, init: RequestInit, getToken: TokenFn): Promise<Response> {
  const cfg = await loadConfig();
  const token = await getToken();
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  if (init.body && typeof init.body === "string" && !headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), 30_000);
  try {
    return await fetch(`${cfg.apiBase}${path}`, { ...init, headers, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

export async function toApiError(res: Response): Promise<ApiError> {
  let body: Record<string, unknown> = {};
  try {
    body = (await res.json()) as Record<string, unknown>;
  } catch {
    // not JSON
  }
  const title = typeof body.title === "string" ? body.title : res.statusText || `HTTP ${res.status}`;
  const detail = typeof body.detail === "string" ? body.detail : undefined;
  return new ApiError(res.status, title, detail, body);
}

export async function apiJson<T>(path: string, init: RequestInit, getToken: TokenFn): Promise<T> {
  const res = await request(path, init, getToken);
  if (!res.ok) throw await toApiError(res);
  return (await res.json()) as T;
}

/** GET with offline fallback to the last successful response. */
export async function apiGetCached<T>(path: string, getToken: TokenFn, cacheKey = path): Promise<CachedResult<T>> {
  try {
    const data = await apiJson<T>(path, { method: "GET" }, getToken);
    const fetchedAt = new Date().toISOString();
    await db.analytics_cache.put({ key: cacheKey, value: data, fetched_at: fetchedAt });
    return { data, fromCache: false, fetchedAt };
  } catch (err) {
    const isNetwork = !(err instanceof ApiError) || err.status >= 500 || err.status === 401;
    const hit = isNetwork ? await db.analytics_cache.get(cacheKey) : undefined;
    if (hit) return { data: hit.value as T, fromCache: true, fetchedAt: hit.fetched_at };
    throw err;
  }
}

/** POST whose result is cached by request body (OLAP queries). */
export async function apiPostCached<T>(path: string, body: unknown, getToken: TokenFn): Promise<CachedResult<T>> {
  const key = `${path}:${JSON.stringify(body)}`;
  try {
    const data = await apiJson<T>(path, { method: "POST", body: JSON.stringify(body) }, getToken);
    const fetchedAt = new Date().toISOString();
    await db.analytics_cache.put({ key, value: data, fetched_at: fetchedAt });
    return { data, fromCache: false, fetchedAt };
  } catch (err) {
    const hit = !(err instanceof ApiError) || err.status >= 500 ? await db.analytics_cache.get(key) : undefined;
    if (hit) return { data: hit.value as T, fromCache: true, fetchedAt: hit.fetched_at };
    throw err;
  }
}

export { request as rawRequest };

/** Open an authenticated streaming GET (server-sent events). The caller owns the abort signal. */
export async function apiStream(path: string, getToken: TokenFn, signal: AbortSignal): Promise<Response> {
  const cfg = await loadConfig();
  const token = await getToken();
  const headers = new Headers({ Accept: "text/event-stream" });
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${cfg.apiBase}${path}`, { headers, signal, cache: "no-store" });
}
