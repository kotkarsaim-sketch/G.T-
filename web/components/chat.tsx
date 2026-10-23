"use client";

import { useCallback, useMemo, useRef, useState } from "react";
import jsPDF from "jspdf";
import { marked } from "marked";
import { API_BASE, Citation, streamChat } from "@/lib/api";

type Status = "idle" | "retrieving" | "streaming" | "refused" | "degraded" | "done";

// Configure marked renderer to never output hyperlinks or unstyled elements
const customRenderer = new marked.Renderer();
customRenderer.link = ({ text }) => text;

marked.setOptions({
  renderer: customRenderer,
  gfm: true,
  breaks: true,
});

/**
 * Strips bracket citation numbers (e.g. [1], 【1】), hyperlinks, and stray brackets
 * so the resident sees clean prose in normal font without distracting links and numbers.
 */
export function cleanAnswerText(raw: string): string {
  if (!raw) return "";

  return raw
    // 1. Remove bracket citation numbers: [1], [2], 【1】, 【2】, [12], etc.
    .replace(/(?:\[|【)\s*\d{1,3}\s*(?:\]|】)/g, "")
    // 2. Remove any HTML <sup> tags or links
    .replace(/<sup\b[^>]*>.*?<\/sup>/gi, "")
    .replace(/<a\b[^>]*>(.*?)<\/a>/gi, "$1")
    // 3. Remove markdown links: [text](url) -> text
    .replace(/\[([^\]]+)\]\([^)]+\)/g, "$1")
    // 4. Remove empty parentheses or brackets left behind like ( ) or 【 】
    .replace(/\(\s*\)/g, "")
    .replace(/【\s*】/g, "")
    // 5. Clean extra whitespace before punctuation
    .replace(/\s+([.,;:!?])/g, "$1")
    // 6. Clean duplicate spaces
    .replace(/[ \t]{2,}/g, " ")
    .trim();
}

/**
 * Formats text for clean multi-line PDF output without raw markdown syntax.
 */
export function getPlainTextForPdf(raw: string): string {
  const cleaned = cleanAnswerText(raw);
  return cleaned
    // Remove markdown headers
    .replace(/^#{1,6}\s+/gm, "")
    // Remove bold and italic markers
    .replace(/(\*\*|__)(.*?)\1/g, "$2")
    .replace(/(\*|_)(.*?)\1/g, "$2")
    // Remove horizontal rules
    .replace(/^[ \t]*[-*_]{3,}[ \t]*$/gm, "")
    // Convert table rows into clean readable lines
    .replace(/^\|(.+)\|$/gm, (_, content) => {
      if (/^[ \t\-:|]+$/.test(content)) return "";
      const cells = content
        .split("|")
        .map((c: string) => c.trim())
        .filter(Boolean);
      return cells.join("  -  ");
    })
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

export function AnswerText({ text }: { text: string }) {
  const html = useMemo(() => {
    const cleaned = cleanAnswerText(text);
    return marked.parse(cleaned) as string;
  }, [text]);

  return (
    <div
      className="answer-prose text-[15px] font-normal leading-relaxed text-slate-800"
      dangerouslySetInnerHTML={{ __html: html }}
    />
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

  const downloadPdf = useCallback(() => {
    if (!answer) return;

    const doc = new jsPDF({
      orientation: "portrait",
      unit: "mm",
      format: "a4",
    });

    const pageWidth = doc.internal.pageSize.getWidth();
    const pageHeight = doc.internal.pageSize.getHeight();
    const margin = 18;
    const contentWidth = pageWidth - margin * 2;
    let y = 18;

    const addWatermark = () => {
      doc.setFont("helvetica", "bold");
      doc.setFontSize(8);
      doc.setTextColor(203, 213, 225); // subtle slate-300 watermark
      doc.text("CIVICGRAPH", pageWidth - margin, pageHeight - 10, { align: "right" });
    };

    // Header top brand bar
    doc.setFillColor(26, 66, 116);
    doc.rect(margin, y, contentWidth, 2, "F");
    y += 8;

    // Header branding
    doc.setFont("helvetica", "bold");
    doc.setFontSize(15);
    doc.setTextColor(26, 66, 116);
    doc.text("CivicGraph", margin, y);

    // Current Date
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    const dateStr = new Date().toLocaleDateString("en-US", {
      year: "numeric",
      month: "short",
      day: "numeric",
    });
    doc.text(dateStr, pageWidth - margin, y, { align: "right" });
    y += 6;

    // Subtitle
    doc.setFontSize(9);
    doc.setTextColor(100, 116, 139);
    doc.text("Municipal Legal & Regulatory Information Report", margin, y);
    y += 8;

    // Divider
    doc.setDrawColor(226, 232, 240);
    doc.setLineWidth(0.4);
    doc.line(margin, y, pageWidth - margin, y);
    y += 7;

    // Question Section
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(15, 23, 42);
    doc.text("Question:", margin, y);
    y += 5.5;

    doc.setFont("helvetica", "normal");
    doc.setFontSize(10);
    doc.setTextColor(51, 65, 85);
    const qLines = doc.splitTextToSize(question.trim() || initialQuery, contentWidth);
    doc.text(qLines, margin, y);
    y += qLines.length * 4.8 + 6;

    // Answer Section Header
    doc.setFont("helvetica", "bold");
    doc.setFontSize(11);
    doc.setTextColor(15, 23, 42);
    doc.text("Answer:", margin, y);
    y += 6;

    // Answer Body in normal clean font
    const plainText = getPlainTextForPdf(answer);
    doc.setFont("helvetica", "normal");
    doc.setFontSize(9.5);
    doc.setTextColor(30, 41, 59);

    const paragraphs = plainText.split(/\n\n+/);
    for (const para of paragraphs) {
      const trimmed = para.trim();
      if (!trimmed) continue;

      const lines = doc.splitTextToSize(trimmed, contentWidth);
      const blockHeight = lines.length * 4.6;

      if (y + blockHeight > pageHeight - 24) {
        addWatermark();
        doc.addPage();
        y = 18;
      }

      doc.text(lines, margin, y);
      y += blockHeight + 3.5;
    }

    // Disclaimer footer
    if (y + 16 > pageHeight - 16) {
      addWatermark();
      doc.addPage();
      y = 18;
    }

    y = Math.max(y + 4, pageHeight - 20);
    doc.setDrawColor(241, 245, 249);
    doc.line(margin, y - 2, pageWidth - margin, y - 2);

    doc.setFont("helvetica", "italic");
    doc.setFontSize(8);
    doc.setTextColor(148, 163, 184);
    doc.text(
      "Informational only. Grounded in municipal by-laws. Not formal legal advice.",
      margin,
      y + 3,
    );

    addWatermark();

    const fileDate = new Date().toISOString().slice(0, 10);
    doc.save(`civicgraph-answer-${fileDate}.pdf`);
  }, [answer, question, initialQuery]);

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
            <article className="relative rounded-lg border border-slate-200 bg-white p-6 pb-9 shadow-sm">
              <div className="mb-4 flex items-center justify-between border-b border-slate-100 pb-3">
                <h2 className="text-xs font-semibold uppercase tracking-wider text-slate-400">
                  Answer
                </h2>
                <button
                  type="button"
                  onClick={downloadPdf}
                  className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-slate-50 px-2.5 py-1 text-xs font-medium text-slate-700 shadow-sm transition hover:bg-white hover:text-civic-700 hover:border-civic-300 focus:outline-none focus:ring-2 focus:ring-civic-500"
                  title="Download answer as PDF"
                >
                  <svg className="h-3.5 w-3.5 text-slate-500" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
                  </svg>
                  <span>Download PDF</span>
                </button>
              </div>

              <AnswerText text={answer} />

              {/* Watermark in corner */}
              <div className="absolute bottom-2.5 right-3.5 flex items-center gap-1.5 text-xs font-semibold tracking-wider text-slate-300 uppercase select-none pointer-events-none">
                <svg className="w-3.5 h-3.5 opacity-60" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2L2 7l10 5 10-5-10-5zM2 17l10 5 10-5M2 12l10 5 10-5" />
                </svg>
                <span>CivicGraph</span>
              </div>
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
                        {s.instrument.title}, s. {s.article.number}
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
