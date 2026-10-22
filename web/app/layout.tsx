import type { Metadata } from "next";
import Link from "next/link";
import ChatWidget from "@/components/chat-widget";
import "./globals.css";

export const metadata: Metadata = {
  title: "CivicGraph - Municipal By-law Assistant",
  description:
    "Ask questions about municipal by-laws and get answers cited to the exact section in force.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 font-sans text-ink antialiased">
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-baseline gap-2">
              <span className="font-serif text-xl font-bold tracking-tight">CivicGraph</span>
              <span className="hidden text-sm text-slate-500 sm:inline">
                Municipal by-law assistant
              </span>
            </Link>
            <nav className="flex items-center gap-6 text-sm">
              <Link href="/" className="text-slate-600 hover:text-civic-700">
                Home
              </Link>
              <Link href="/chat" className="text-slate-600 hover:text-civic-700">
                Ask a question
              </Link>
              <Link href="/admin" className="text-slate-600 hover:text-civic-700">
                Admin
              </Link>
            </nav>
          </div>
        </header>
        {children}
        <footer className="mt-16 border-t border-slate-200 bg-white">
          <div className="mx-auto max-w-5xl px-6 py-8 text-xs leading-relaxed text-slate-500">
            <p>
              Informational service only. Answers are generated from the municipal code and
              cite their sources; they do not constitute legal advice. For binding
              determinations, contact the City Clerk&apos;s office.
            </p>
            <p className="mt-2">CivicGraph v0.3 - pilot deployment</p>
          </div>
        </footer>
        <ChatWidget />
      </body>
    </html>
  );
}
