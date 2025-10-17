// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { GithubFilled } from "@ant-design/icons";
import { ChevronRight, MessageCircle } from "lucide-react";
import Link from "next/link";
import { useTranslations } from "next-intl";

import { AuroraText } from "~/components/magicui/aurora-text";
import { FlickeringGrid } from "~/components/magicui/flickering-grid";
import { Button } from "~/components/ui/button";
import { env } from "~/env";

import { LandingChatPreview } from "./landing-chat-preview";

export function Jumbotron() {
  const t = useTranslations("hero");
  const tCommon = useTranslations("common");
  const highlights = [
    t("highlight1"),
    t("highlight2"),
    t("highlight3"),
  ].filter(Boolean);
  const previewMessages = [
    { role: "user" as const, content: t("chatPreview.userMessage") },
    { role: "assistant" as const, content: t("chatPreview.assistantMessage") },
  ].filter((message) => message.content && message.content.length > 0);

  return (
    <section className="relative flex min-h-[90vh] w-full flex-col items-center justify-center overflow-hidden px-4 pb-24 pt-12 sm:px-8 lg:pb-32">
      <FlickeringGrid
        id="deer-hero-bg"
        className="absolute inset-0 z-0 [mask-image:radial-gradient(800px_circle_at_center,white,transparent)]"
        squareSize={4}
        gridGap={4}
        color="#60A5FA"
        maxOpacity={0.133}
        flickerChance={0.1}
      />
      <FlickeringGrid
        id="deer-hero"
        className="absolute inset-0 z-0 translate-y-[2vh] mask-[url(/images/deer-hero.svg)] mask-size-[100vw] mask-center mask-no-repeat md:mask-size-[72vh]"
        squareSize={3}
        gridGap={6}
        color="#60A5FA"
        maxOpacity={0.64}
        flickerChance={0.12}
      />
      <div className="relative z-10 flex w-full max-w-5xl flex-col items-center gap-10 text-center">
        <span className="border-border/40 bg-background/40 text-muted-foreground inline-flex items-center gap-2 rounded-full border px-4 py-1 text-xs font-medium uppercase tracking-[0.3em] backdrop-blur sm:text-sm">
          <MessageCircle size={14} />
          {t("eyebrow")}
        </span>
        <h1 className="font-medium leading-tight text-balance text-4xl md:text-6xl">
          <span className="bg-gradient-to-r from-white via-gray-100 to-gray-400 bg-clip-text text-transparent">
            {t("title")}
          </span>
          <span className="mt-2 block text-4xl md:text-6xl">
            <AuroraText>{t("highlighted")}</AuroraText>
          </span>
        </h1>
        <p className="text-muted-foreground max-w-3xl text-base leading-relaxed md:text-xl">
          {t("description")}
        </p>
        <ul className="flex flex-wrap items-center justify-center gap-3">
          {highlights.map((highlight) => (
            <li
              key={highlight}
              className="border-border/40 bg-background/60 text-foreground/80 inline-flex items-center gap-2 rounded-full border px-4 py-2 text-xs font-medium backdrop-blur md:text-sm"
            >
              <span className="h-1.5 w-1.5 rounded-full bg-primary" />
              {highlight}
            </li>
          ))}
        </ul>
        <div className="flex flex-col items-center justify-center gap-4 sm:flex-row">
          <Button className="w-48 text-base" size="lg" asChild>
            <Link
              target={
                env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY ? "_blank" : undefined
              }
              href={
                env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY
                  ? "https://github.com/obinopaul/DeepResearchAgent"
                  : "/chat"
              }
            >
              {tCommon("getStarted")} <ChevronRight />
            </Link>
          </Button>
          {!env.NEXT_PUBLIC_STATIC_WEBSITE_ONLY && (
            <Button className="w-48 text-base" size="lg" variant="outline" asChild>
              <Link href="https://github.com/obinopaul/DeepResearchAgent" target="_blank">
                <GithubFilled />
                {tCommon("learnMore")}
              </Link>
            </Button>
          )}
        </div>
        <LandingChatPreview
          title={t("chatPreview.title")}
          messages={previewMessages}
          hint={t("chatPreview.hint")}
        />
      </div>
      <div className="text-muted-foreground absolute bottom-6 flex text-xs md:text-sm">
        <p>{t("footnote")}</p>
      </div>
    </section>
  );
}
