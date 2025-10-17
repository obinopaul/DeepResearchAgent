// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { motion } from "framer-motion";
import { useTranslations } from "next-intl";

import { cn } from "~/lib/utils";

export function Welcome({ className }: { className?: string }) {
  const t = useTranslations("chat.welcome");

  return (
    <motion.div
      className={cn("flex w-full max-w-3xl flex-col items-center", className)}
      style={{ transition: "all 0.3s ease-out" }}
      initial={{ opacity: 0, y: 16, scale: 0.96 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
    >
      <div className="relative w-full overflow-hidden rounded-[24px] border border-border/50 bg-gradient-to-br from-background via-background to-transparent p-6 text-center shadow-[0_24px_64px_-48px_rgba(15,23,42,0.6)] backdrop-blur">
        <div
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 rounded-[24px] border border-white/10 opacity-60"
        />
        <div className="relative z-10 flex flex-col items-center gap-3">
          <span className="inline-flex items-center gap-2 rounded-full bg-primary/15 px-4 py-1 text-[11px] font-semibold uppercase tracking-[0.4em] text-primary md:text-xs">
            {t("tagline")}
          </span>
          <h3 className="text-balance text-2xl font-semibold md:text-3xl">
            {t("greeting")}
          </h3>
        </div>
      </div>
    </motion.div>
  );
}
