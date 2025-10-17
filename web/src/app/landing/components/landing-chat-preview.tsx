'use client';

import { ArrowRight, MessageCircle } from "lucide-react";
import { useRouter } from "next/navigation";
import { useCallback } from "react";

import { cn } from "~/lib/utils";

type PreviewMessage = {
  role: "user" | "assistant";
  content: string;
};

export function LandingChatPreview({
  title,
  messages,
  hint,
}: {
  title: string;
  messages: PreviewMessage[];
  hint: string;
}) {
  const router = useRouter();
  const handleOpenChat = useCallback(() => {
    router.push("/chat");
  }, [router]);

  return (
    <button
      type="button"
      onClick={handleOpenChat}
      className="border-border/40 bg-background/70 group relative mx-auto flex w-full max-w-3xl flex-col gap-5 overflow-hidden rounded-3xl border p-6 text-left shadow-2xl transition duration-300 hover:border-primary hover:shadow-primary/30 focus-visible:border-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/40"
    >
      <ChatGlow />
      <div className="flex items-center justify-between">
        <span className="text-sm font-medium uppercase tracking-[0.2em] text-foreground/70">
          {title}
        </span>
        <span className="text-muted-foreground flex items-center gap-1 text-xs">
          {hint}
          <ArrowRight
            size={14}
            className="translate-x-0 transition duration-300 group-hover:translate-x-1"
            aria-hidden="true"
          />
        </span>
      </div>
      <div className="flex flex-col gap-4">
        {messages.map((message, index) => (
          <div
            key={`${message.role}-${index}`}
            className={cn(
              "flex w-full",
              message.role === "assistant" ? "justify-start" : "justify-end",
            )}
          >
            <div
              className={cn(
                "border-border/40 max-w-[85%] rounded-2xl border px-4 py-3 text-sm md:text-base",
                message.role === "assistant"
                  ? "bg-primary/15 text-primary-foreground"
                  : "bg-background text-foreground/90",
              )}
            >
              <span>{message.content}</span>
            </div>
          </div>
        ))}
      </div>
      <div className="text-muted-foreground/80 flex items-center justify-between pt-2 text-xs">
        <span>Tap to launch Morgana</span>
        <span className="flex items-center gap-2 rounded-full bg-primary/15 px-3 py-1 text-primary">
          <MessageCircle size={14} aria-hidden="true" />
          /chat
        </span>
      </div>
    </button>
  );
}

function ChatGlow() {
  return (
    <span
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 -z-10 opacity-80 transition duration-300 group-hover:opacity-100"
      style={{
        background:
          "radial-gradient(circle at top, rgba(96, 165, 250, 0.3), transparent 55%), radial-gradient(circle at bottom right, rgba(236, 72, 153, 0.2), transparent 60%)",
      }}
    />
  );
}
