// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { cn } from "~/lib/utils";

import { Welcome } from "./welcome";

export function ConversationStarter({
  className,
  onSend,
}: {
  className?: string;
  onSend?: (message: string) => void;
}) {
  const t = useTranslations("chat");
  const questions = t.raw("conversationStarters") as string[];

  return (
    <div className={cn("flex flex-col items-center gap-6", className)}>
      <Welcome className="w-full max-w-3xl" />
      <ul className="grid w-full max-w-3xl grid-cols-1 gap-3 md:grid-cols-2">
        {questions.map((question, index) => (
          <motion.li
            key={question}
            className="w-full"
            style={{ transition: "all 0.25s ease-out" }}
            initial={{ opacity: 0, y: 24 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{
              duration: 0.3,
              delay: index * 0.08 + 0.4,
              ease: "easeOut",
            }}
          >
            <button
              type="button"
              className="group flex h-full w-full items-start justify-between gap-3 rounded-2xl border border-border/60 bg-gradient-to-br from-background via-background to-transparent px-5 py-4 text-left text-sm text-foreground/80 shadow-sm transition hover:border-primary/40 hover:text-foreground hover:shadow-lg"
              onClick={() => {
                onSend?.(question);
              }}
            >
              <span>{question}</span>
              <span className="mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-primary/15 text-primary transition group-hover:bg-primary group-hover:text-primary-foreground">
                ↗
              </span>
            </button>
          </motion.li>
        ))}
      </ul>
    </div>
  );
}
