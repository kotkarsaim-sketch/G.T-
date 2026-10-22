"use client";

import { useCallback, useEffect, useState } from "react";
import {
  AdminAuthError,
  AuditRow,
  AuditStats,
  PendingItem,
  adminGet,
  adminPost,
} from "@/lib/api";

const TOKEN_KEY = "civic-admin-token";

const todayISO = () => new Date().toISOString().slice(0, 10);

export default function AdminPage() {
  const [tokenInput, setTokenInput] = useState("");
  const [token, setToken] = useState<string | null>(null);
  const [authed, setAuthed] = useState<boolean | null>(null); // null = checking
  const [tab, setTab] = useState<"queue" | "audit">("queue");
  const [pending, setPending] = useState<PendingItem[]>([]);
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [stats, setStats] = useState<AuditStats | null>(null);
  const [detail, setDetail] = useState<Record<string, unknown> | null>(null);
  const [detailId, setDetailId] = useState<string | null>(null);
  const [effective, setEffective] = useState(todayISO());
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAll = useCallback(async (t: string) => {
    const [p, r, s] = await Promise.all([
      adminGet<{ items: PendingItem[] }>("/v1/admin/pending", t),
      adminGet<{ items: AuditRow[] }>("/v1/admin/audit?limit=20", t),
      adminGet<AuditStats>("/v1/admin/audit/stats", t),
    ]);
    setPending(p.items);
    setRows(r.items);
    setStats(s);
  }, []);

  const unlock = useCallback(
    async (t: string) => {
      setBusy(true);
      setError(null);
      try {
        await loadAll(t);
        setToken(t);
        localStorage.setItem(TOKEN_KEY, t);
        setAuthed(true);
      } catch (e) {
        if (e instanceof AdminAuthError) {
          setError("Invalid or missing credentials.");
        } else {
          setError(e instanceof Error ? e.message : "Connection failed.");
        }
        setAuthed(false);
      } finally {
        setBusy(false);
      }
    },
    [loadAll],
  );

  useEffect(() => {
    const saved = localStorage.getItem(TOKEN_KEY);
    if (saved) {
      setTokenInput(saved);
      unlock(saved);
    } else {
      setAuthed(false);
    }
  }, [unlock]);

  const lock = () => {
    localStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setAuthed(false);
    setTokenInput("");
  };

  const refreshAudit = useCallback(
    async (t: string) => {
      const [r, s] = await Promise.all([
        adminGet<{ items: AuditRow[] }>("/v1/admin/audit?limit=20", t),
        adminGet<AuditStats>("/v1/admin/audit/stats", t),
      ]);
      setRows(r.items);
      setStats(s);
    },
    [],
  );

  const publish = async (number: string) => {
    if (!token) return;
    if (!window.confirm(`Publish by-law ${number}, in force ${effective}? This makes it current law.`)) {
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await adminPost(`/v1/admin/instruments/${number}/publish`, token, { effective_on: effective });
      setPending((prev) => prev.filter((p) => p.number !== number));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Publish failed.");
    } finally {
      setBusy(false);
    }
  };

  const openDetail = async (queryId: string) => {
    if (!token) return;
    setDetailId(queryId);
    try {
      const res = await adminGet<{ record: Record<string, unknown> }>(
        `/v1/admin/audit/${queryId}`,
        token,
      );
      setDetail(res.record);
    } catch {
      setDetail(null);
    }
  };

  if (authed === null) {
    return <main className="mx-auto max-w-5xl px-6 py-16 text-slate-500">Checking credentials...</main>;
  }

  if (!authed) {
    return (
      <main className="mx-auto max-w-md px-6 py-20">
        <div className="rounded-xl border border-slate-200 bg-white p-8 shadow-sm">
          <h1 className="font-serif text-2xl font-bold">Clerk review console</h1>
          <p className="mt-2 text-sm leading-relaxed text-slate-600">
            Restricted area. Sign in with the admin token, or municipal SSO once
            OIDC is configured for your deployment.
          </p>
          <form
            className="mt-6 space-y-3"
            onSubmit={(e) => {
              e.preventDefault();
              unlock(tokenInput.trim());
            }}
          >
            <input
              type="password"
              value={tokenInput}
              onChange={(e) => setTokenInput(e.target.value)}
              placeholder="Admin token"
              aria-label="Admin token"
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-civic-600 focus:ring-2 focus:ring-civic-100"
            />
            <button
              type="submit"
              disabled={busy}
              className="w-full rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white hover:bg-civic-800 disabled:opacity-50"
            >
              {busy ? "Checking..." : "Unlock"}
            </button>
          </form>
          {error && (
            <p role="alert" className="mt-4 rounded-md border border-amber-300 bg-amber-50 p-3 text-sm text-amber-900">
              {error}
            </p>
          )}
        </div>
      </main>
    );
  }

  const pct = (n: number) => (stats && stats.total ? Math.round((n / stats.total) * 100) : 0);

  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="font-serif text-2xl font-bold">Clerk review console</h1>
          <p className="text-sm text-slate-500">Amendment gate and assistant audit trail</p>
        </div>
        <button onClick={lock} className="rounded-md border border-slate-300 px-3 py-1.5 text-sm text-slate-600 hover:border-civic-600 hover:text-civic-700">
          Lock
        </button>
      </div>

      {error && (
        <p role="alert" className="mt-4 rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-800">
          {error}
        </p>
      )}

      <div className="mt-6 flex gap-2 border-b border-slate-200">
        {(["queue", "audit"] as const).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition ${
              tab === t
                ? "border-b-2 border-civic-700 text-civic-800"
                : "text-slate-500 hover:text-civic-700"
            }`}
          >
            {t === "queue" ? `Review queue (${pending.length})` : "Audit trail"}
          </button>
        ))}
      </div>

      {tab === "queue" && (
        <section className="mt-6">
          <div className="mb-4 flex items-center gap-3 text-sm text-slate-600">
            <label htmlFor="effective">Effective date for publishing:</label>
            <input
              id="effective"
              type="date"
              value={effective}
              onChange={(e) => setEffective(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1"
            />
          </div>
          {pending.length === 0 ? (
            <p className="rounded-lg border border-slate-200 bg-white p-6 text-sm text-slate-500">
              Nothing is awaiting review. Amended instruments appear here when
              ingested with status <code className="text-xs">pending_review</code>.
            </p>
          ) : (
            <ul className="space-y-3">
              {pending.map((p) => (
                <li key={p.id} className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-200 bg-white p-4">
                  <div>
                    <p className="font-medium">
                      By-law {p.number} - {p.title}
                    </p>
                    <p className="text-xs text-slate-500">enacted {p.enacted_on ?? "unknown"}</p>
                  </div>
                  <button
                    onClick={() => publish(p.number)}
                    disabled={busy}
                    className="rounded-md bg-civic-700 px-4 py-2 text-sm font-medium text-white hover:bg-civic-800 disabled:opacity-50"
                  >
                    Publish
                  </button>
                </li>
              ))}
            </ul>
          )}
        </section>
      )}

      {tab === "audit" && (
        <section className="mt-6 space-y-6">
          {stats && (
            <div className="grid grid-cols-2 gap-4 sm:grid-cols-5">
              <Stat label="Sessions" value={String(stats.total)} />
              <Stat label="Complete" value={`${pct(stats.by_finish["complete"] ?? 0)}%`} />
              <Stat label="Refused" value={`${pct(stats.by_finish["refused"] ?? 0)}%`} />
              <Stat label="p50 latency" value={ms(stats.latency_ms.p50)} />
              <Stat label="p95 latency" value={ms(stats.latency_ms.p95)} />
            </div>
          )}
          <div className="overflow-hidden rounded-lg border border-slate-200 bg-white">
            <table className="w-full text-left text-sm">
              <thead className="bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-4 py-2">When</th>
                  <th className="px-4 py-2">Finish</th>
                  <th className="px-4 py-2">Latency</th>
                  <th className="px-4 py-2">Question</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((r) => (
                  <tr
                    key={r.query_id}
                    onClick={() => openDetail(r.query_id)}
                    className={`cursor-pointer border-t border-slate-100 hover:bg-civic-50 ${
                      detailId === r.query_id ? "bg-civic-50" : ""
                    }`}
                  >
                    <td className="px-4 py-2 text-slate-500">{String(r.at).slice(0, 10)}</td>
                    <td className="px-4 py-2">
                      <span
                        className={`rounded-full px-2 py-0.5 text-xs ${
                          r.finish === "complete"
                            ? "bg-emerald-100 text-emerald-800"
                            : r.finish === "refused"
                              ? "bg-amber-100 text-amber-900"
                              : "bg-slate-100 text-slate-700"
                        }`}
                      >
                        {r.finish}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-slate-500">{ms(r.latency_ms)}</td>
                    <td className="max-w-[22rem] truncate px-4 py-2" title={r.question}>
                      {r.question}
                    </td>
                  </tr>
                ))}
                {rows.length === 0 && (
                  <tr>
                    <td colSpan={4} className="px-4 py-6 text-center text-slate-500">
                      No sessions recorded yet.
                    </td>
                  </tr>
                )}
              </tbody>
            </table>
          </div>
          {detail && (
            <div className="rounded-lg border border-slate-200 bg-white p-4">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Record {detailId}
              </h3>
              <pre className="overflow-x-auto whitespace-pre-wrap text-xs leading-relaxed text-slate-700">
                {JSON.stringify(detail, null, 2)}
              </pre>
            </div>
          )}
        </section>
      )}
    </main>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white p-4">
      <p className="text-xs uppercase tracking-wide text-slate-400">{label}</p>
      <p className="mt-1 text-lg font-semibold text-ink">{value}</p>
    </div>
  );
}

function ms(v: number | null | undefined): string {
  return typeof v === "number" ? `${Math.round(v)}ms` : "-";
}
