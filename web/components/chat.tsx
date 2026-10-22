"use client";

import { useCallback, useRef, useState } from "react";
import { API_BASE, Citation, streamChat } from "@/lib/api";

type Status = "idle" | "retrieving" | "streaming" | "refused" | "degraded" | "done";

export function AnswerText({ text }: { text: string }) {
  // Render [n] markers as superscript links into the citation list.
  const parts = text.split(/(\[\d{1,2}\])/g);
  return (
    <span className="answer-text">
      {parts.map((part, i) => {
        const m = part.match(/^\[(\d{1,2})\]$/);
        if (!m) return <span key={i}>{part}</span>;
        const n = Number(m[1]);
        return (
          <sup key={i}>
            <a href={`#cite-${n}`}>[{n}]</a>
          </sup>
        );
      })}
    </span>
  );
}

export default function ChatWindow({ initialQuery }: { initialQuery: string }) {
  const [question, setQuestion] = useState(initialQuery);
  const [status, setStatus] = useState<Status>("idle");
  const [answer, setAnswer] = useState("");
  const [notice, setNotice] = useState<string | null>(null);
  const [sources, setSources] = useState<Citation[]>([]);
  const [error, setError] = useState<string | null>(null);
  const answerRef = useRef<HTMLDivElement>(null);

  const ask = useCallback(async () => {
    const q = question.trim();
    if (q.length < 3) {
      setError("Please enter a question of at least three characters.");
      return;
    }
    setError(null);
    setAnswer("");
    setNotice(null);
    setSources([]);
    setStatus("retrieving");

    try {
      await streamChat(q, {
        onMeta: (sources) => setSources(sources),
        onToken: (text) => {
          setStatus("streaming");
          setAnswer((prev) => prev + text);
        },
        onCitations: (_used, citedSources) => {
          setSources(citedSources);
        },
        onNotice: (n) => {
          setNotice(n.text);
          setStatus(n.kind === "generation_unavailable" ? "degraded" : "refused");
        },
        onDone: (finish) => {
          setStatus(
            finish === "refused"
              ? "refused"
              : finish === "degraded"
                ? "degraded"
                : "done",
          );
        },
      });
    } catch (e) {
      setError(
        e instanceof Error ? e.message : "The service is unavailable. Please retry shortly.",
      );
      setStatus("idle");
    }
  }, [question]);

  const busy = status === "retrieving" || status === "streaming";
  const examples = [
    "Are backyard hives allowed?",
    "What are quiet hours?",
    "Do I need a permit for a fence?",
  ];

  return (
    <div className="mx-auto w-full max-w-3xl">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          ask();
        }}
        className="flex gap-2"
      >
        <input
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          placeholder="Ask about a municipal by-law..."
          aria-label="Your question"
          maxLength={2000}
          className="w-full rounded-md border border-slate-300 bg-white px-4 py-3 text-base shadow-sm outline-none focus:border-civic-600 focus:ring-2 focus:ring-civic-100"
        />
        <button
          type="submit"
          disabled={busy}
          className="whitespace-nowrap rounded-md bg-civic-700 px-5 py-3 font-medium text-white shadow-sm transition hover:bg-civic-800 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {busy ? "Working..." : "Ask"}
        </button>
      </form>

      {error && (
        <p role="alert" className="mt-3 text-sm text-red-700">
          {error}
        </p>
      )}

      {!answer && status === "idle" && (
        <div className="mt-6 flex flex-wrap gap-2">
          {examples.map((ex) => (
            <button
              key={ex}
              onClick={() => {
                setQuestion(ex);
              }}
              className="rounded-full border border-slate-300 bg-white px-3 py-1.5 text-sm text-slate-600 hover:border-civic-600 hover:text-civic-700"
            >
              {ex}
            </button>
          ))}
        </div>
      )}

      {(sources.length > 0 || notice || answer) && (
        <div ref={answerRef} className="mt-8 space-y-6">
          {notice && (
            <div
              role="status"
              className="rounded-md border border-amber-300 bg-amber-50 p-4 text-sm leading-relaxed text-amber-900"
            >
              {notice}
            </div>
          )}

          {answer && (
            <article className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Answer
              </h2>
              <p className="text-[15px] leading-7 text-slate-800">
                <AnswerText text={answer} />
              </p>
            </article>
          )}

          {sources.length > 0 && (
            <section aria-label="Cited sections">
              <h2 className="mb-3 text-xs font-semibold uppercase tracking-wide text-slate-400">
                Sources in the municipal code
              </h2>
              <ol className="space-y-2">
                {sources.map((s) => (
                  <li
                    key={s.n}
                    id={`cite-${s.n}`}
                    className="rounded-md border border-slate-200 bg-white p-4 text-sm"
                  >
                    <div className="flex items-baseline justify-between gap-4">
                      <span className="font-medium text-civic-800">
                        [{s.n}] {s.instrument.title}, s. {s.article.number}
                        {s.article.heading ? ` - ${s.article.heading}` : ""}
                      </span>
                      {s.url && (
                        <a
                          href={s.url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="shrink-0 text-xs text-civic-600 underline underline-offset-2"
                        >
                          official source
                        </a>
                      )}
                    </div>
                  </li>
                ))}
              </ol>
            </section>
          )}
        </div>
      )}
    </div>
  );
}
