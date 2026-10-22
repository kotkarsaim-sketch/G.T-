import { Suspense } from "react";
import ChatWindow from "@/components/chat";

export const metadata = {
  title: "Ask - CivicGraph",
};

export default function ChatPage({
  searchParams,
}: {
  searchParams?: { q?: string };
}) {
  return (
    <main className="mx-auto max-w-5xl px-6 py-10">
      <Suspense fallback={null}>
        <ChatWindow initialQuery={searchParams?.q ?? ""} />
      </Suspense>
    </main>
  );
}
