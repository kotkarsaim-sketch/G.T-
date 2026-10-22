import Link from "next/link";

const features = [
  {
    title: "Plain-language questions",
    body: "Ask the way you would ask a person at the counter. No section numbers or legal vocabulary required.",
  },
  {
    title: "Every answer is cited",
    body: "Responses link to the exact by-law and section they come from, so you can read the law yourself.",
  },
  {
    title: "Current law, not stale PDFs",
    body: "The assistant answers from the code as in force today, including amendments, and tells you when it cannot find an answer.",
  },
];

export default function Home() {
  return (
    <main className="mx-auto max-w-5xl px-6">
      <section className="py-16 sm:py-24">
        <p className="text-sm font-medium uppercase tracking-wider text-civic-600">
          City of Rivermont - pilot
        </p>
        <h1 className="mt-3 max-w-2xl font-serif text-4xl font-bold leading-tight tracking-tight sm:text-5xl">
          Understand your city&apos;s by-laws without reading them like a lawyer.
        </h1>
        <p className="mt-5 max-w-2xl text-lg leading-relaxed text-slate-600">
          CivicGraph answers questions about municipal rules in plain language,
          with a citation to the exact section of the by-law behind every answer.
        </p>

        <div className="mt-8 flex flex-wrap gap-3">
          <Link
            href="/chat"
            className="rounded-md bg-civic-700 px-6 py-3 font-medium text-white shadow-sm transition hover:bg-civic-800"
          >
            Ask a question
          </Link>
          <a
            href="http://localhost:7474"
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md border border-slate-300 bg-white px-6 py-3 font-medium text-slate-700 transition hover:border-civic-600 hover:text-civic-700"
          >
            Browse the knowledge graph
          </a>
        </div>
      </section>

      <section className="grid gap-6 pb-8 sm:grid-cols-3">
        {features.map((f) => (
          <div key={f.title} className="rounded-lg border border-slate-200 bg-white p-6 shadow-sm">
            <h2 className="font-semibold">{f.title}</h2>
            <p className="mt-2 text-sm leading-relaxed text-slate-600">{f.body}</p>
          </div>
        ))}
      </section>
    </main>
  );
}
