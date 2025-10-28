// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { LoadingOutlined } from "@ant-design/icons";
import { motion, useReducedMotion } from "framer-motion";
import {
  Download,
  Headphones,
  ChevronDown,
  ChevronRight,
  Lightbulb,
  Wrench,
} from "lucide-react";
import { useTranslations } from "next-intl";
import React, { useCallback, useLayoutEffect, useMemo, useRef, useState } from "react";
import { Virtuoso, type VirtuosoHandle } from "react-virtuoso";

import { LoadingAnimation } from "~/components/deer-flow/loading-animation";
import { Markdown } from "~/components/deer-flow/markdown";
import { RainbowText } from "~/components/deer-flow/rainbow-text";
import { RollingText } from "~/components/deer-flow/rolling-text";
import { ScrollContainer } from "~/components/deer-flow/scroll-container";
import { Tooltip } from "~/components/deer-flow/tooltip";
import { Button } from "~/components/ui/button";
import {
  Card,
  CardContent,
  CardFooter,
  CardHeader,
  CardTitle,
} from "~/components/ui/card";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "~/components/ui/collapsible";
import type { Message, Option } from "~/core/messages";
import {
  closeResearch,
  openResearch,
  useLastFeedbackMessageId,
  useLastInterruptMessage,
  useMessage,
  useMessageIds,
  useResearchMessage,
  useStore,
} from "~/core/store";
import { useInterruptMessageFor } from "~/core/store";
import { parseJSON } from "~/core/utils";
import { debugLog } from "~/lib/debug";
import { usePageVisibility } from "~/hooks/use-page-visibility";
import { cn } from "~/lib/utils";

export function MessageListView({
  className,
  onFeedback,
  onSendMessage,
}: {
  className?: string;
  onFeedback?: (feedback: { option: Option }) => void;
  onSendMessage?: (
    message: string,
    options?: { interruptFeedback?: string },
  ) => void;
}) {
  const messageIds = useMessageIds();
  const interruptMessage = useLastInterruptMessage();
  const waitingForFeedbackMessageId = useLastFeedbackMessageId();
  const responding = useStore((state) => state.responding);
  const noOngoingResearch = useStore(
    (state) => state.ongoingResearchId === null,
  );
  const ongoingResearchIsOpen = useStore(
    (state) => state.ongoingResearchId === state.openResearchId,
  );
  const containerRef = useRef<HTMLDivElement>(null);
  const virtuosoRef = useRef<VirtuosoHandle>(null);
  const [isAtBottom, setIsAtBottom] = useState(true);
  const [viewportReady, setViewportReady] = useState(false);
  const prefersReducedMotion = useReducedMotion();
  const isPageVisible = usePageVisibility();
  const shouldAnimate = isPageVisible && !prefersReducedMotion;

  const footerComponent = useMemo(() => {
    const shouldShowLoader = responding && (noOngoingResearch || !ongoingResearchIsOpen);
    const Footer = () => (
      <div className="flex w-full justify-start">
        {shouldShowLoader ? <LoadingAnimation className="ml-4" /> : <div className="h-8 w-full" />}
      </div>
    );
    return Footer;
  }, [responding, noOngoingResearch, ongoingResearchIsOpen]);

  const handleToggleResearch = useCallback(() => {
    requestAnimationFrame(() => {
      virtuosoRef.current?.scrollToIndex({
        index: Math.max(messageIds.length - 1, 0),
        align: "end",
        behavior: "smooth",
      });
    });
  }, [messageIds.length]);

  useLayoutEffect(() => {
    const node = containerRef.current;
    if (!node) {
      return;
    }
    if (typeof ResizeObserver === "undefined") {
      setViewportReady(true);
      return;
    }
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) {
        return;
      }
      const { width, height } = entry.contentRect;
      const hasViewport = width > 0 && height > 0;
      setViewportReady((prev) => (prev === hasViewport ? prev : hasViewport));
    });
    observer.observe(node);
    return () => {
      observer.disconnect();
    };
  }, []);

  return (
    <div ref={containerRef} className={cn("relative flex h-full w-full min-h-0 flex-1", className)}>
      <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-10 bg-gradient-to-t from-transparent to-[var(--app-background)]" />
      <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-10 bg-gradient-to-b from-transparent to-[var(--app-background)]" />
      {viewportReady ? (
        <Virtuoso
          ref={virtuosoRef}
          style={{ height: "100%", width: "100%" }}
          data={messageIds}
          computeItemKey={(_, messageId) => messageId}
          followOutput={isPageVisible && isAtBottom ? "smooth" : false}
          atBottomStateChange={setIsAtBottom}
          increaseViewportBy={{ top: 400, bottom: 600 }}
          components={{ Footer: footerComponent }}
          itemContent={(_, messageId) => (
            <MessageListItem
              messageId={messageId}
              waitForFeedback={waitingForFeedbackMessageId === messageId}
              interruptMessage={interruptMessage}
              onFeedback={onFeedback}
              onSendMessage={onSendMessage}
              onToggleResearch={handleToggleResearch}
              shouldAnimate={shouldAnimate}
            />
          )}
        />
      ) : (
        <div className="flex h-full w-full items-center justify-center">
          <LoadingOutlined className="text-lg text-muted-foreground" />
        </div>
      )}
    </div>
  );
}

function MessageListItem({
  messageId,
  waitForFeedback,
  interruptMessage,
  onFeedback,
  onSendMessage,
  onToggleResearch,
  shouldAnimate = true,
}: {
  messageId: string;
  waitForFeedback?: boolean;
  onFeedback?: (feedback: { option: Option }) => void;
  interruptMessage?: Message | null;
  onSendMessage?: (
    message: string,
    options?: { interruptFeedback?: string },
  ) => void;
  onToggleResearch?: () => void;
  shouldAnimate?: boolean;
}) {
  const message = useMessage(messageId);
  const researchIds = useStore((state) => state.researchIds);
  const startOfResearch = useMemo(() => {
    return researchIds.includes(messageId);
  }, [researchIds, messageId]);
  if (message) {
    if (
      message.role === "user" ||
      message.agent === "coordinator" ||
      message.agent === "planner" ||
      message.agent === "podcast" ||
      startOfResearch
    ) {
      let content: React.ReactNode;
      if (message.agent === "planner") {
        content = (
          <div className="w-full px-4">
            <PlanCard
              message={message}
              waitForFeedback={waitForFeedback}
              interruptMessage={interruptMessage}
              onFeedback={onFeedback}
              onSendMessage={onSendMessage}
            />
          </div>
        );
      } else if (message.agent === "podcast") {
        content = (
          <div className="w-full px-4">
            <PodcastCard message={message} />
          </div>
        );
      } else if (startOfResearch) {
        content = (
          <div className="w-full px-4">
            <ResearchCard
              researchId={message.id}
              onToggleResearch={onToggleResearch}
            />
          </div>
        );
      } else {
        // Ensure we render strings; if content is a non-string (e.g. object), stringify it
        const contentString =
          typeof message.content === "string"
            ? message.content
            : JSON.stringify(message.content);
        content = contentString ? (
          <div
            className={cn(
              "flex w-full px-4",
              message.role === "user" && "justify-end",
            )}
          >
            <MessageBubble message={message}>
              <div className="flex w-full flex-col break-words">
                <Markdown
                  className={cn(
                    message.role === "user" &&
                      "prose-invert not-dark:text-secondary dark:text-inherit",
                  )}
                >
                  {contentString}
                </Markdown>
              </div>
            </MessageBubble>
          </div>
        ) : null;
      }
      if (content) {
        return (
          <motion.div
            className="mt-10"
            key={messageId}
            initial={shouldAnimate ? { opacity: 0, y: 24 } : { opacity: 1, y: 0 }}
            animate={{ opacity: 1, y: 0 }}
            style={shouldAnimate ? { transition: "all 0.2s ease-out" } : undefined}
            transition={
              shouldAnimate
                ? {
                    duration: 0.2,
                    ease: "easeOut",
                  }
                : { duration: 0 }
            }
          >
            {content}
          </motion.div>
        );
      }
    }
    return null;
  }
}

function MessageBubble({
  className,
  message,
  children,
}: {
  className?: string;
  message: Message;
  children: React.ReactNode;
}) {
  return (
    <div
      className={cn(
        "group flex w-auto max-w-[90vw] flex-col rounded-2xl px-4 py-3 break-words",
        message.role === "user" && "bg-brand rounded-ee-none",
        message.role === "assistant" && "bg-card rounded-es-none",
        className,
      )}
      style={{ wordBreak: "break-all" }}
    >
      {children}
    </div>
  );
}

function ResearchCard({
  className,
  researchId,
  onToggleResearch,
}: {
  className?: string;
  researchId: string;
  onToggleResearch?: () => void;
}) {
  const t = useTranslations("chat.research");
  const reportId = useStore((state) => state.researchReportIds.get(researchId));
  const hasReport = reportId !== undefined;
  const reportGenerating = useStore(
    (state) => hasReport && state.messages.get(reportId)!.isStreaming,
  );
  const openResearchId = useStore((state) => state.openResearchId);
  const state = useMemo(() => {
    if (hasReport) {
      return reportGenerating ? t("generatingReport") : t("reportGenerated");
    }
    return t("researching");
  }, [hasReport, reportGenerating, t]);
  const msg = useResearchMessage(researchId);
  const title = useMemo(() => {
    if (msg) {
      return parseJSON(msg.content ?? "", { title: "" }).title;
    }
    return undefined;
  }, [msg]);
  const handleOpen = useCallback(() => {
    if (openResearchId === researchId) {
      closeResearch();
    } else {
      openResearch(researchId);
    }
    onToggleResearch?.();
  }, [openResearchId, researchId, onToggleResearch]);
  return (
    <Card className={cn("w-full", className)}>
      <CardHeader>
        <CardTitle>
          <RainbowText animated={state !== t("reportGenerated")}>
            {title !== undefined && title !== "" ? title : t("deepResearch")}
          </RainbowText>
        </CardTitle>
      </CardHeader>
      <CardFooter>
        <div className="flex w-full">
          <RollingText className="text-muted-foreground flex-grow text-sm">
            {state}
          </RollingText>
          <Button
            variant={!openResearchId ? "default" : "outline"}
            onClick={handleOpen}
          >
            {researchId !== openResearchId ? t("open") : t("close")}
          </Button>
        </div>
      </CardFooter>
    </Card>
  );
}

function ThoughtBlock({
  className,
  content,
  isStreaming,
  hasMainContent,
}: {
  className?: string;
  content: string;
  isStreaming?: boolean;
  hasMainContent?: boolean;
}) {
  const t = useTranslations("chat.research");
  const [isOpen, setIsOpen] = useState(true);

  const [hasAutoCollapsed, setHasAutoCollapsed] = useState(false);

  React.useEffect(() => {
    if (hasMainContent && !hasAutoCollapsed) {
      setIsOpen(false);
      setHasAutoCollapsed(true);
    }
  }, [hasMainContent, hasAutoCollapsed]);

  if (!content || content.trim() === "") {
    return null;
  }

  return (
    <div className={cn("mb-6 w-full", className)}>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CollapsibleTrigger asChild>
          <Button
            variant="ghost"
            className={cn(
              "h-auto w-full justify-start rounded-xl border px-6 py-4 text-left transition-all duration-200",
              "hover:bg-accent hover:text-accent-foreground",
              isStreaming
                ? "border-primary/20 bg-primary/5 shadow-sm"
                : "border-border bg-card",
            )}
          >
            <div className="flex w-full items-center gap-3">
              <Lightbulb
                size={18}
                className={cn(
                  "shrink-0 transition-colors duration-200",
                  isStreaming ? "text-primary" : "text-muted-foreground",
                )}
              />
              <span
                className={cn(
                  "leading-none font-semibold transition-colors duration-200",
                  isStreaming ? "text-primary" : "text-foreground",
                )}
              >
                {t("deepThinking")}
              </span>
              {isStreaming && <LoadingAnimation className="ml-2 scale-75" />}
              <div className="flex-grow" />
              {isOpen ? (
                <ChevronDown
                  size={16}
                  className="text-muted-foreground transition-transform duration-200"
                />
              ) : (
                <ChevronRight
                  size={16}
                  className="text-muted-foreground transition-transform duration-200"
                />
              )}
            </div>
          </Button>
        </CollapsibleTrigger>
        <CollapsibleContent className="data-[state=open]:animate-in data-[state=closed]:animate-out data-[state=closed]:fade-out-0 data-[state=open]:fade-in-0 data-[state=closed]:slide-up-2 data-[state=open]:slide-down-2 mt-3">
          <Card
            className={cn(
              "transition-all duration-200",
              isStreaming ? "border-primary/20 bg-primary/5" : "border-border",
            )}
          >
            <CardContent>
              <div className="flex h-40 w-full overflow-y-auto">
                <ScrollContainer
                  className={cn(
                    "flex h-full w-full flex-col overflow-hidden",
                    className,
                  )}
                  scrollShadow={false}
                  autoScrollToBottom
                >
                  <Markdown
                    className={cn(
                      "prose dark:prose-invert max-w-none transition-colors duration-200",
                      isStreaming ? "prose-primary" : "opacity-80",
                    )}
                    animated={isStreaming}
                  >
                    {content}
                  </Markdown>
                </ScrollContainer>
              </div>
            </CardContent>
          </Card>
        </CollapsibleContent>
      </Collapsible>
    </div>
  );
}

const GREETINGS = ["Cool", "Sounds great", "Looks good", "Great", "Awesome"];
function PlanCard({
  className,
  message,
  interruptMessage,
  onFeedback,
  waitForFeedback,
  onSendMessage,
}: {
  className?: string;
  message: Message;
  interruptMessage?: Message | null;
  onFeedback?: (feedback: { option: Option }) => void;
  onSendMessage?: (
    message: string,
    options?: { interruptFeedback?: string },
  ) => void;
  waitForFeedback?: boolean;
}) {
  const t = useTranslations("chat.research");
  // Prefer an interrupt that occurs after this specific plan message, falling back to global
  const interruptForThisPlan = useInterruptMessageFor(message.id);
  const effectiveInterruptMessage = interruptForThisPlan ?? interruptMessage;
  const effectiveWaitForFeedback = interruptForThisPlan ? true : waitForFeedback;
  const plan = useMemo<{
    title?: string;
    thought?: string;
    steps?: { title?: string; description?: string; tools?: string[] }[];
  }>(() => {
    return parseJSON(message.content ?? "", {});
  }, [message.content]);

  // Log render state including interrupt linkage
  try {
    debugLog(
      "[PlanCard] state",
      {
        id: message.id,
        agent: message.agent,
        isStreaming: message.isStreaming,
        hasInterruptOptions: !!effectiveInterruptMessage?.options?.length,
        waitForFeedback: effectiveWaitForFeedback,
        hasPlan: !!plan?.steps?.length || !!plan?.title || !!plan?.thought,
      },
    );
  } catch {}

  const reasoningContent = message.reasoningContent;
  const hasMainContent = Boolean(
    message.content && message.content.trim() !== "",
  );

  // 判断是否正在思考：有推理内容但还没有主要内容
  const isThinking = Boolean(reasoningContent && !hasMainContent);

  // 判断是否应该显示计划：有主要内容就显示（无论是否还在流式传输）
  const shouldShowPlan = hasMainContent;
  const handleAccept = useCallback(async () => {
    if (onSendMessage) {
      onSendMessage(
        `${GREETINGS[Math.floor(Math.random() * GREETINGS.length)]}! ${Math.random() > 0.5 ? "Let's get started." : "Let's start."}`,
        {
          interruptFeedback: "accepted",
        },
      );
    }
  }, [onSendMessage]);
  return (
    <div className={cn("w-full", className)}>
      {reasoningContent && (
        <ThoughtBlock
          content={reasoningContent}
          isStreaming={isThinking}
          hasMainContent={hasMainContent}
        />
      )}
      {shouldShowPlan && (
        <motion.div
          initial={{ opacity: 0, y: 20 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.3, ease: "easeOut" }}
        >
          <Card className="w-full">
            <CardHeader>
              <CardTitle>
                <Markdown animated={message.isStreaming}>
                  {`### ${
                    plan.title !== undefined && plan.title !== ""
                      ? plan.title
                      : t("deepResearch")
                  }`}
                </Markdown>
              </CardTitle>
            </CardHeader>
            <CardContent>
              <div style={{ wordBreak: 'break-all', whiteSpace: 'normal' }}>
                <Markdown className="opacity-80" animated={message.isStreaming}>
                  {plan.thought}
                </Markdown>
                {plan.steps && (
                  <ul className="my-2 flex list-decimal flex-col gap-4 border-l-[2px] pl-8">
                    {plan.steps.map((step, i) => (
                      <li key={`step-${i}`} style={{ wordBreak: 'break-all', whiteSpace: 'normal' }}>
                        <div className="flex items-start gap-2">
                          <div className="flex-1">
                            <h3 className="mb flex items-center gap-2 text-lg font-medium">
                              <Markdown animated={message.isStreaming}>
                                {step.title}
                              </Markdown>
                              {step.tools && step.tools.length > 0 && (
                                <Tooltip
                                  title={`Uses ${step.tools.length} MCP tool${step.tools.length > 1 ? "s" : ""}`}
                                >
                                  <div className="flex items-center gap-1 rounded-full bg-blue-100 px-2 py-1 text-xs text-blue-800">
                                    <Wrench size={12} />
                                    <span>{step.tools.length}</span>
                                  </div>
                                </Tooltip>
                              )}
                            </h3>
                            <div className="text-muted-foreground text-sm" style={{ wordBreak: 'break-all', whiteSpace: 'normal' }}>
                              <Markdown animated={message.isStreaming}>
                                {step.description}
                              </Markdown>
                            </div>
                            {step.tools && step.tools.length > 0 && (
                              <ToolsDisplay tools={step.tools} />
                            )}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            </CardContent>
            <CardFooter className="flex justify-end">
              {effectiveInterruptMessage?.options?.length && (
                <motion.div
                  className="flex gap-2"
                  initial={{ opacity: 0, y: 12 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={{ duration: 0.3, delay: 0.3 }}
                >
                  {effectiveInterruptMessage?.options.map((option) => (
                    <Button
                      key={option.value}
                      variant={
                        option.value === "accepted" ? "default" : "outline"
                      }
                      disabled={!effectiveWaitForFeedback}
                      onClick={() => {
                        if (option.value === "accepted") {
                          void handleAccept();
                        } else {
                          onFeedback?.({
                            option,
                          });
                        }
                      }}
                    >
                      {option.text}
                    </Button>
                  ))}
                </motion.div>
              )}
            </CardFooter>
          </Card>
        </motion.div>
      )}
    </div>
  );
}

function PodcastCard({
  className,
  message,
}: {
  className?: string;
  message: Message;
}) {
  const data = useMemo(() => {
    return JSON.parse(message.content ?? "");
  }, [message.content]);
  const title = useMemo<string | undefined>(() => data?.title, [data]);
  const audioUrl = useMemo<string | undefined>(() => data?.audioUrl, [data]);
  const isGenerating = useMemo(() => {
    return message.isStreaming;
  }, [message.isStreaming]);
  const hasError = useMemo(() => {
    return data?.error !== undefined;
  }, [data]);
  const [isPlaying, setIsPlaying] = useState(false);
  return (
    <Card className={cn("w-[508px]", className)}>
      <CardHeader>
        <div className="text-muted-foreground flex items-center justify-between text-sm">
          <div className="flex items-center gap-2">
            {isGenerating ? <LoadingOutlined /> : <Headphones size={16} />}
            {!hasError ? (
              <RainbowText animated={isGenerating}>
                {isGenerating
                  ? "Generating podcast..."
                  : isPlaying
                    ? "Now playing podcast..."
                    : "Podcast"}
              </RainbowText>
            ) : (
              <div className="text-red-500">
                Error when generating podcast. Please try again.
              </div>
            )}
          </div>
          {!hasError && !isGenerating && (
            <div className="flex">
              <Tooltip title="Download podcast">
                <Button variant="ghost" size="icon" asChild>
                  <a
                    href={audioUrl}
                    download={`${(title ?? "podcast").replaceAll(" ", "-")}.mp3`}
                  >
                    <Download size={16} />
                  </a>
                </Button>
              </Tooltip>
            </div>
          )}
        </div>
        <CardTitle>
          <div className="text-lg font-medium">
            <RainbowText animated={isGenerating}>{title}</RainbowText>
          </div>
        </CardTitle>
      </CardHeader>
      <CardContent>
        {audioUrl ? (
          <audio
            className="w-full"
            src={audioUrl}
            controls
            onPlay={() => setIsPlaying(true)}
            onPause={() => setIsPlaying(false)}
          />
        ) : (
          <div className="w-full"></div>
        )}
      </CardContent>
    </Card>
  );
}

function ToolsDisplay({ tools }: { tools: string[] }) {
  return (
    <div className="mt-2 flex flex-wrap gap-1">
      {tools.map((tool, index) => (
        <span
          key={index}
          className="rounded-md bg-muted px-2 py-1 text-xs font-mono text-muted-foreground"
        >
          {tool}
        </span>
      ))}
    </div>
  );
}
