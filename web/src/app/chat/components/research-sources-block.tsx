// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { useTranslations } from "next-intl";
import { useStore } from "~/core/store";
import { cn } from "~/lib/utils";
import { Markdown } from "~/components/deer-flow/markdown";
import { useShallow } from "zustand/react/shallow";

export function ResearchSourcesBlock({
  className,
  researchId,
}: {
  className?: string;
  researchId: string;
}) {
  const t = useTranslations("chat.research");
  const sources = useStore(
    useShallow((state) => state.researchSources.get(researchId) ?? []),
  );

  const sourcesMarkdown = sources
    .map((source) => `- [${source.title.replace(/[[\]]/g, "")}](${source.url})`)
    .join("\n");

  return (
    <div className={cn("py-4", className)}>
      {sources.length > 0 ? (
        <Markdown>{sourcesMarkdown}</Markdown>
      ) : (
        <p className="text-muted-foreground text-sm">{t("noSourcesFound")}</p>
      )}
    </div>
  );
}
