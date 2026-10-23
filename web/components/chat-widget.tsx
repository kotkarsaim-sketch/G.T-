"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { AnswerText } from "@/components/chat";
import { Citation, streamChat } from "@/lib/api";

interface Msg {
  role: "user" | "assistant";
  text: string;
  notice?: string;
  sources?: Citation[];
}

const GREETING =
  "Hello. Ask me about municipal by-laws - noise, animals, fencing, licensing. Every answer cites the exact section in force.";

export default function ChatWidget() {
  const [open, setOpen] = useState(false);
  const [input, setInput] = useState("");
  const [msgs, setMsgs] = useState<Msg[]>([]);
  const [busy, setBusy] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const msgsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (open) {
      inputRef.current?.focus();
      if (msgs.length === 0) {
        setMsgs([{ role: "assistant", text: GREETING }]);
      }
    }
  }, [open, msgs.length]);

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    msgsRef.current?.scrollTo({ top: msgsRef.current.scrollHeight });
  }, [msgs, open]);

  const send = useCallback(async () => {
    const q = input.trim();
    if (q.length < 3 || busy) return;
    setInput("");
    setBusy(true);

    const history = msgs
      .filter((m) => !m.notice)
      .slice(-6)
      .map((m) => ({ role: m.role, content: m.text }));

    setMsgs((prev) => [...prev, { role: "user", text: q }, { role: "assistant", text: "" }]);

    const patchLast = (patch: Partial<Msg>) =>
      setMsgs((prev) => {
        const next = [...prev];
        next[next.length - 1] = { ...next[next.length - 1], ...patch };
        return next;
      });

    try {
      await streamChat(q, {
        onMeta: () => undefined,
        onToken: (text) =>
          setMsgs((prev) => {
            const next = [...prev];
            const last = next[next.length - 1];
            next[next.length - 1] = { ...last, text: last.text + text };
            return next;
          }),
        onNotice: (n) => patchLast({ notice: n.text }),
        onCitations: (_used, sources) => patchLast({ sources }),
        onDone: () => undefined,
      });
    } catch {
      patchLast({ notice: "The assistant is temporarily unavailable. Please retry shortly." });
    } finally {
      setBusy(false);
      inputRef.current?.focus();
    }
  }, [input, busy, msgs]);

  return (
    <>
      <button
        aria-label={open ? "Close assistant" : "Open assistant"}
        onClick={() => setOpen((v) => !v)}
        className="fixed bottom-6 right-6 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-civic-700 text-white shadow-xl transition hover:bg-civic-800 focus:outline-none focus:ring-4 focus:ring-civic-200"
      >
        {open ? (
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round">
            <path d="M6 6l12 12M18 6L6 18" />
          </svg>
        ) : (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <path d="M21 12a8 8 0 0 1-8 8H5l-2 2V12a8 8 0 0 1 8-8h2a8 8 0 0 1 8 8z" />
          </svg>
        )}
      </button>

      {open && (
        <section
          aria-label="Assistant chat"
          className="fixed bottom-24 right-6 z-50 flex h-[540px] max-h-[calc(100vh-8rem)] w-[380px] max-w-[calc(100vw-3rem)] flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl"
        >
          <header className="bg-civic-800 px-4 py-3 text-white">
            <h2 className="text-sm font-semibold">City Assistant</h2>
            <p className="text-xs text-civic-100">Cited answers from the municipal code</p>
          </header>

          <div ref={msgsRef} className="flex-1 space-y-3 overflow-y-auto bg-slate-50 p-4">
            {msgs.map((m, i) =>
              m.role === "user" ? (
                <p key={i} className="ml-auto max-w-[85%] rounded-2xl rounded-br-sm bg-civic-700 px-3 py-2 text-sm text-white">
                  {m.text}
                </p>
              ) : (
                <div key={i} className="mr-auto max-w-[92%] space-y-2">
                  <div className="relative rounded-2xl rounded-bl-sm border border-slate-200 bg-white px-3 py-2 pb-5 text-sm leading-relaxed text-slate-800">
                    <AnswerText text={m.text} />
                    {m.notice && (
                      <p className="mt-2 rounded-md border border-amber-300 bg-amber-50 p-2 text-xs text-amber-900">{m.notice}</p>
                    )}
                    <div className="absolute bottom-1 right-2.5 text-[9px] font-semibold tracking-wider text-slate-300 uppercase select-none pointer-events-none">
                      CivicGraph
                    </div>
                  </div>
                  {m.sources && m.sources.length > 0 && (
                    <ul className="space-y-1 pl-1 text-xs text-slate-500">
                      {m.sources.map((s) => (
                        <li key={s.n}>
                          {s.instrument.title}, s. {s.article.number}
                          {s.url && (
                            <>
                              {" "}
                              <a href={s.url} target="_blank" rel="noopener noreferrer" className="text-civic-600 underline underline-offset-2">
                                source
                              </a>
                            </>
                          )}
                        </li>
                      ))}
                    </ul>
                  )}
                </div>
              ),
            )}
          </div>

          <form
            onSubmit={(e) => {
              e.preventDefault();
              send();
            }}
            className="flex gap-2 border-t border-slate-200 p-3"
          >
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              placeholder="Ask about a by-law..."
              aria-label="Your question"
              maxLength={2000}
              className="w-full rounded-md border border-slate-300 px-3 py-2 text-sm outline-none focus:border-civic-600 focus:ring-2 focus:ring-civic-100"
            />
            <button
              type="submit"
              disabled={busy}
              className="rounded-md bg-civic-700 px-3 py-2 text-sm font-medium text-white hover:bg-civic-800 disabled:opacity-50"
            >
              Send
            </button>
          </form>
          <p className="pb-2 text-center text-[10px] text-slate-400">Informational only - not legal advice.</p>
        </section>
      )}
    </>
  );
}
