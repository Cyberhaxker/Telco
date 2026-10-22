import { ApiError } from "@/lib/api";
import { ago } from "@/lib/format";

export function Problem({ error }: { error: Error | null }) {
  if (!error) return null;
  let text = error.message;
  if (error instanceof ApiError) {
    if (error.status === 401) text = "Your session expired. Sign in again to load fresh data.";
    else if (error.status === 403) text = "Your account does not have permission for this data.";
    else if (error.status === 429) text = "Too many requests. Wait a minute and try again.";
    else text = `${error.title}${error.detail ? `: ${error.detail}` : ""}`;
  } else if (error.name === "AbortError" || error.message === "Failed to fetch") {
    text = "The server could not be reached and nothing is saved on this device for this view yet.";
  }
  return (
    <div className="notice bad" role="alert">
      {text}
    </div>
  );
}

export function CacheNote({ fromCache, fetchedAt }: { fromCache: boolean; fetchedAt: string | null }) {
  if (!fetchedAt) return null;
  return fromCache ? (
    <span className="pill warn">Saved copy from {ago(fetchedAt)}</span>
  ) : (
    <span className="pill">Updated {ago(fetchedAt)}</span>
  );
}
