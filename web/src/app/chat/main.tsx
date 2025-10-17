// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

"use client";

import { useMemo } from "react";

import { useStore } from "~/core/store";
import { cn } from "~/lib/utils";

import { MessagesBlock } from "./components/messages-block";
import { ResearchBlock } from "./components/research-block";

export default function Main() {
  const openResearchId = useStore((state) => state.openResearchId);
  const doubleColumnMode = useMemo(
    () => openResearchId !== null,
    [openResearchId],
  );
  return (
    <div
      className={cn(
        "relative z-10 flex h-full w-full justify-center-safe px-6 pb-4 pt-4",
        doubleColumnMode && "gap-8",
      )}
    >
      <MessagesBlock
        className={cn(
          "shrink-0 transition-all duration-300 ease-out",
          !doubleColumnMode && "mx-auto w-full max-w-[880px]",
          doubleColumnMode && "w-[560px]",
        )}
      />
      {doubleColumnMode && (
        <ResearchBlock
          className="w-[min(max(calc((100vw-560px)*0.75),600px),980px)] pb-4 transition-all duration-300 ease-out"
          researchId={openResearchId}
        />
      )}
    </div>
  );
}
