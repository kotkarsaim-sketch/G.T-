export const API_BASE = process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8000";

export class AdminAuthError extends Error {
  constructor() {
    super("Unauthorized");
  }
}

function adminHeaders(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}`, "Content-Type": "application/json" };
}

export async function adminGet<T>(path: string, token: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, { headers: adminHeaders(token) });
  if (res.status === 401) throw new AdminAuthError();
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export async function adminPost<T>(path: string, token: string, body?: unknown): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: adminHeaders(token),
    body: body ? JSON.stringify(body) : undefined,
  });
  if (res.status === 401) throw new AdminAuthError();
  if (!res.ok) throw new Error(`Request failed (${res.status})`);
  return res.json();
}

export interface PendingItem {
  id: string;
  number: string;
  title: string;
  enacted_on: string | null;
  kind: string;
}

export interface AuditRow {
  at: string;
  query_id: string;
  question: string;
  finish: string;
  latency_ms: number | null;
  n_sources: number | null;
}

export interface AuditStats {
  total: number;
  by_finish: Record<string, number>;
  latency_ms: { p50: number | null; p95: number | null };
}

export interface Citation {
  n: number;
  instrument: { id: string; number: string; title: string };
  article: { id: string; number: string; heading: string };
  url: string | null;
  score: number;
  origin: string;
}

interface StreamHandlers {
  onMeta?: (sources: Citation[]) => void;
  onToken?: (text: string) => void;
  onNotice?: (notice: { text: string; kind: string }) => void;
  onCitations?: (used: number[], sources: Citation[]) => void;
  onDone?: (finish: string, latencyMs: number) => void;
}

/**
 * POST /v1/chat and consume the SSE stream.
 * Event names arrive on the line preceding each data payload.
 */
export async function streamChat(question: string, handlers: StreamHandlers): Promise<void> {
  const res = await fetch(`${API_BASE}/v1/chat`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ question, locale: navigator.language?.slice(0, 2) ?? "en" }),
  });

  if (res.status === 429) {
    throw new Error("Too many requests. Please wait a moment and try again.");
  }
  if (!res.ok || !res.body) {
    throw new Error("The assistant is temporarily unavailable.");
  }

  const reader = res.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  const dispatch = (eventName: string, dataLine: string) => {
    if (!dataLine) return;
    try {
      const data = JSON.parse(dataLine.replace(/^data:\s*/, ""));
      switch (eventName) {
        case "meta":
          handlers.onMeta?.(data.sources ?? []);
          break;
        case "token":
          handlers.onToken?.(data.text ?? "");
          break;
        case "notice":
          handlers.onNotice?.(data);
          break;
        case "citations":
          handlers.onCitations?.(data.used ?? [], data.sources ?? []);
          break;
        case "done":
          handlers.onDone?.(data.finish ?? "complete", data.latency_ms ?? 0);
          break;
        default:
          break; // forward compatibility: ignore unknown events
      }
    } catch {
      // malformed frame: skip rather than abort the stream
    }
  };

  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });

    let sep: number;
    while ((sep = buffer.indexOf("\n\n")) !== -1) {
      const block = buffer.slice(0, sep);
      buffer = buffer.slice(sep + 2);
      let eventName = "";
      let dataLine = "";
      for (const line of block.split("\n")) {
        if (line.startsWith("event: ")) eventName = line.slice(7).trim();
        else if (line.startsWith("data: ")) dataLine = line;
      }
      dispatch(eventName, dataLine);
    }
  }
}
