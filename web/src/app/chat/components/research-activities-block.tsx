// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { PythonOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { LRUCache } from "lru-cache";
import { CheckCircle2, ChevronDown, Circle, Loader2 } from "lucide-react";
import { BookOpenText, FileText, Search } from "lucide-react";
import { useTranslations } from "next-intl";
import { useTheme } from "next-themes";
import React, { useEffect, useMemo, useState } from "react";
import SyntaxHighlighter from "react-syntax-highlighter";
import { docco } from "react-syntax-highlighter/dist/esm/styles/hljs";
import { dark } from "react-syntax-highlighter/dist/esm/styles/prism";
import { useShallow } from "zustand/react/shallow";

import { FavIcon } from "~/components/deer-flow/fav-icon";
import Image from "~/components/deer-flow/image";
import { LoadingAnimation } from "~/components/deer-flow/loading-animation";
import { Markdown } from "~/components/deer-flow/markdown";
import { RainbowText } from "~/components/deer-flow/rainbow-text";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "~/components/ui/collapsible";
import { Skeleton } from "~/components/ui/skeleton";
import type { Message, ToolCallRuntime } from "~/core/messages";
import { appendResearchSources, useMessage, useStore } from "~/core/store";
import {
  extractTodosFromMessages,
  type TodoItem,
  type TodoStatus,
} from "~/core/todos";
import { parseJSON } from "~/core/utils";
import { cn } from "~/lib/utils";

const MAX_ANIMATED_ACTIVITY_ITEMS = 10;
const ACTIVITY_ANIMATION_DELAY = 0.05;
const MAX_PAGE_RESULTS = 20;
const MAX_PAGE_ANIMATIONS = 6;
const MAX_IMAGE_RESULTS = 10;
const MAX_IMAGE_ANIMATIONS = 4;
const MAX_DOCUMENT_ANIMATIONS = 4;

export function ResearchActivitiesBlock({
  className,
  researchId,
}: {
  className?: string;
  researchId: string;
}) {
  const activityIds = useStore((state) =>
    state.researchActivityIds.get(researchId),
  )!;
  const ongoing = useStore((state) => state.ongoingResearchId === researchId);
  const planMessageId = activityIds[0];
  const timelineActivityIds = activityIds.slice(1);
  const activityMessages = useStore(
    useShallow((state) =>
      timelineActivityIds
        .map((id) => state.messages.get(id))
        .filter((message): message is Message => Boolean(message)),
    ),
  );
  return (
    <div className={cn("flex flex-col gap-4", className)}>
      {planMessageId && (
        <div className="sticky top-2 z-20">
          <PlanActivityOverview
            researchId={researchId}
            planMessageId={planMessageId}
            ongoing={ongoing}
            activityMessages={activityMessages}
          />
        </div>
      )}
      <div className="relative">
        <ul className="flex flex-col py-4">
          {timelineActivityIds.map((activityId, i) => {
            const shouldAnimate = i < MAX_ANIMATED_ACTIVITY_ITEMS;
            const animationDelay = shouldAnimate
              ? Math.min(i * ACTIVITY_ANIMATION_DELAY, 0.5)
              : 0;
            return (
              <motion.li
                key={activityId}
                style={{
                  transition: shouldAnimate ? "all 0.3s ease-out" : "none",
                }}
                initial={shouldAnimate ? { opacity: 0, y: 24 } : { opacity: 1, y: 0 }}
                animate={{ opacity: 1, y: 0 }}
                transition={
                  shouldAnimate
                    ? {
                        duration: 0.3,
                        delay: animationDelay,
                        ease: "easeOut",
                      }
                    : undefined
                }
              >
                <ActivityMessage messageId={activityId} />
                <ActivityListItem messageId={activityId} />
                {i !== timelineActivityIds.length - 1 && <hr className="my-8" />}
              </motion.li>
            );
          })}
        </ul>
        {ongoing && <LoadingAnimation className="mx-4 my-12" />}
      </div>
    </div>
  );
}

interface DerivedStep {
  index: number;
  title: string;
  description: string;
  status: TodoStatus;
  rawContent?: string;
}

function pickFirstFilledText(
  ...values: Array<string | null | undefined>
): string | undefined {
  for (const value of values) {
    if (typeof value === "string") {
      const trimmed = value.trim();
      if (trimmed) {
        return trimmed;
      }
    }
  }
  return undefined;
}

interface ToolActivitySummary {
  status: "running" | "finished";
  tool: "web_search" | "crawl_tool" | "local_search_tool" | "python_repl_tool";
  text: string;
}
function PlanActivityOverview({
  researchId,
  planMessageId,
  ongoing,
  activityMessages,
}: {
  researchId: string;
  planMessageId: string;
  ongoing: boolean;
  activityMessages: Message[];
}) {
  const planMessage = useMessage(planMessageId);
  const persistedTodos = useStore(
    (state) => state.researchTodos.get(researchId) ?? null,
  );

  const liveTodos = useMemo(
    () => extractTodosFromMessages(activityMessages),
    [activityMessages],
  );

  const todos = useMemo(
    () => persistedTodos ?? liveTodos ?? null,
    [persistedTodos, liveTodos],
  );

  const planTitle = useMemo(() => {
    const content = planMessage?.content;
    if (typeof content === "string") {
      const parsed = parseJSON<Record<string, unknown> | null>(content, null);
      if (parsed && typeof parsed.title === "string" && parsed.title.trim()) {
        return parsed.title.trim();
      }
      const trimmed = content.trim();
      if (trimmed) {
        return trimmed;
      }
    }
    if (Array.isArray(content)) {
      const textPart = content
        .map((part) => {
          if (typeof part === "string") {
            return part;
          }
          if (part && typeof part === "object" && "text" in part) {
            const raw = (part as { text?: unknown }).text;
            if (typeof raw === "string") {
              return raw;
            }
          }
          return "";
        })
        .find(
          (value): value is string =>
            typeof value === "string" && value.trim().length > 0,
        );
      if (textPart) {
        return textPart.trim();
      }
    }
    return null;
  }, [planMessage?.content]);

  const steps = useMemo<DerivedStep[]>(() => deriveSteps(todos), [todos]);
  const hasSteps = steps.length > 0;

  const statusSummary = useMemo(() => summarizeStatuses(steps), [steps]);
  const progress = useMemo(
    () => computeProgress(steps, ongoing),
    [steps, ongoing],
  );
  const latestAction = useMemo(
    () => extractLatestToolActivity(activityMessages),
    [activityMessages],
  );
  const activeStep = progress.activeStep;

  const safePercent = Number.isFinite(progress.percent) ? progress.percent : 0;
  const progressWidth = Math.max(0, Math.min(safePercent, 100));
  const percentLabel = Math.round(progressWidth);
  const [expanded, setExpanded] = useState(true);
  const [activeExpanded, setActiveExpanded] = useState(true);

  useEffect(() => {
    if (hasSteps) {
      setExpanded(true);
    }
  }, [hasSteps]);

  useEffect(() => {
    if (activeStep) {
      setActiveExpanded(true);
    }
  }, [activeStep]);

  const headerTitle = planTitle ?? "Deep Agent Plan";

  return (
    <Collapsible
      open={expanded}
      onOpenChange={setExpanded}
      className={cn(
        "overflow-hidden rounded-3xl border border-border/60 bg-gradient-to-br from-card/95 via-card/90 to-background/90 shadow-lg",
        "supports-[backdrop-filter]:backdrop-blur-md supports-[backdrop-filter]:bg-card/75",
      )}
    >
      <CollapsibleTrigger asChild>
        <button
          type="button"
          className="flex w-full items-start justify-between gap-4 px-5 py-4 text-left transition-colors hover:bg-white/5 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60 dark:hover:bg-slate-950/20"
          aria-expanded={expanded}
        >
          <div className="flex flex-1 flex-col gap-2">
            <span className="text-[11px] font-semibold uppercase tracking-[0.18em] text-muted-foreground">
              Deep Agent Overview
            </span>
            <h3 className="text-lg font-semibold leading-tight text-foreground">
              {headerTitle}
            </h3>
            {hasSteps ? (
              <div className="flex flex-wrap gap-2">
                <StatusSummaryPill
                  label="completed"
                  value={statusSummary.completed}
                  tone="success"
                />
                <StatusSummaryPill
                  label="in progress"
                  value={statusSummary.in_progress}
                  tone="info"
                />
                <StatusSummaryPill
                  label="pending"
                  value={statusSummary.pending}
                  tone="muted"
                />
              </div>
            ) : (
              <p className="text-xs text-muted-foreground">
                Waiting for deep agent todo updates…
              </p>
            )}
            {!expanded && hasSteps && (
              <p className="text-xs text-muted-foreground">
                {progress.percent >= 100
                  ? "All todos completed"
                  : `${progress.completed} done • ${statusSummary.in_progress} active • ${statusSummary.pending} waiting`}
              </p>
            )}
          </div>
          <div className="flex flex-col items-end gap-3">
            <div className="flex items-center gap-2 rounded-full bg-muted/40 px-3 py-1 text-[11px] font-semibold uppercase tracking-wide text-muted-foreground">
              <span>{percentLabel}%</span>
              <span>
                {progress.percent >= 100
                  ? "Complete"
                  : ongoing
                    ? "Running"
                    : "Standby"}
              </span>
            </div>
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-border/60 bg-background/70 text-muted-foreground">
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform duration-300",
                  expanded && "rotate-180",
                )}
              />
            </div>
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="px-5 pb-5 pt-2">
        <div className="space-y-5">
          {hasSteps ? (
            <div className="space-y-2">
              <div className="relative h-2 overflow-hidden rounded-full bg-muted/50">
                <div
                  className={cn(
                    "absolute left-0 top-0 h-full rounded-full bg-primary transition-all duration-500",
                    progressWidth === 0 && "bg-primary/60",
                  )}
                  style={{ width: `${progressWidth}%` }}
                />
              </div>
              <div className="flex flex-wrap items-center justify-between gap-2 text-xs text-muted-foreground">
                <span>
                  {progress.percent >= 100
                    ? "All todos completed"
                    : ongoing
                      ? "Agent is executing tasks"
                      : "Awaiting agent activity"}
                </span>
                <span>
                  {progress.completed}/{steps.length} complete · {statusSummary.in_progress} active
                </span>
              </div>
            </div>
          ) : (
            <div className="rounded-2xl border border-dashed border-border/60 bg-background/80 p-4 text-xs text-muted-foreground">
              The deep agent has not published any todos yet. Updates will appear here once they are available.
            </div>
          )}

          {activeStep && hasSteps && (
            <div className="rounded-2xl border border-primary/40 bg-primary/10 p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-wide text-primary">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  Active Step
                </div>
                <button
                  type="button"
                  onClick={() => setActiveExpanded((prev) => !prev)}
                  className="flex h-7 w-7 items-center justify-center rounded-full border border-primary/40 bg-primary/20 text-primary transition-colors hover:bg-primary/30 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
                  aria-expanded={activeExpanded}
                  aria-label={activeExpanded ? "Collapse active step" : "Expand active step"}
                >
                  <ChevronDown
                    className={cn(
                      "h-4 w-4 transition-transform",
                      activeExpanded ? "rotate-0" : "-rotate-90",
                    )}
                  />
                </button>
              </div>
              <p className="mt-3 text-sm font-semibold leading-snug text-foreground">
                {activeStep.index + 1}. {activeStep.title}
              </p>
              {activeExpanded && (
                <>
                  {activeStep.description && (
                    <p className="mt-1 text-xs text-muted-foreground">
                      {activeStep.description}
                    </p>
                  )}
                  {latestAction && (
                    <div className="mt-3 flex items-center gap-2 rounded-full bg-background/70 px-3 py-1 text-xs text-muted-foreground">
                      {renderToolIcon(latestAction.tool, "h-4 w-4 text-primary")}
                      <span>{latestAction.text}</span>
                    </div>
                  )}
                </>
              )}
            </div>
          )}

          {hasSteps && (
            <div className="max-h-[60vh] overflow-y-auto overscroll-contain pr-3 pb-4">
              <ol className="relative flex flex-col gap-4">
                {steps.map((step, index) => (
                  <PlanStepRow
                    key={`${step.index}-${step.title}`}
                    step={step}
                    isLast={index === steps.length - 1}
                  />
                ))}
              </ol>
            </div>
          )}
        </div>
      </CollapsibleContent>
    </Collapsible>
  );
}

type StatusSummary = Record<TodoStatus, number>;

function summarizeStatuses(steps: DerivedStep[]): StatusSummary {
  return steps.reduce<StatusSummary>(
    (acc, step) => {
      acc[step.status] += 1;
      return acc;
    },
    { completed: 0, in_progress: 0, pending: 0 },
  );
}

function StatusSummaryPill({
  label,
  value,
  tone,
}: {
  label: string;
  value: number;
  tone: "muted" | "info" | "success";
}) {
  const toneClassName =
    tone === "success"
      ? "border-emerald-400/40 bg-emerald-500/15 text-emerald-600"
      : tone === "info"
        ? "border-sky-400/40 bg-sky-500/15 text-sky-600"
        : "border-border/60 bg-muted/30 text-muted-foreground";
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-full border px-3 py-1 text-[11px] font-semibold uppercase tracking-wide",
        toneClassName,
        value === 0 && "opacity-60",
      )}
    >
      <span>{value}</span>
      <span>{label}</span>
    </span>
  );
}

function PlanStepRow({ step, isLast }: { step: DerivedStep; isLast: boolean }) {
  const statusMeta = getStatusMeta(step.status);
  const showRawContent =
    typeof step.rawContent === "string" &&
    step.rawContent.trim() &&
    step.rawContent !== step.description &&
    step.rawContent !== step.title;
  return (
    <li className="relative pl-9">
      <span
        aria-hidden
        className={cn(
          "absolute left-0 top-2 flex h-6 w-6 items-center justify-center rounded-full border text-xs shadow-sm",
          statusMeta.indicatorClassName,
        )}
      >
        {statusMeta.icon}
      </span>
      {!isLast && (
        <span
          aria-hidden
          className={cn(
            "absolute left-[11px] top-8 h-full w-px bg-border/50",
            statusMeta.connectorClassName,
          )}
        />
      )}
      <div
        className={cn(
          "rounded-2xl border px-4 py-3 transition-colors",
          statusMeta.containerClassName,
        )}
      >
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-semibold leading-snug">
            {step.index + 1}. {step.title}
          </p>
          <span
            className={cn(
              "rounded-full px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide",
              statusMeta.pillClassName,
            )}
          >
            {statusMeta.label}
          </span>
        </div>
        {step.description && (
          <p className="mt-1 text-xs text-muted-foreground">{step.description}</p>
        )}
        {showRawContent && (
          <p className="mt-1 text-xs text-muted-foreground/80">
            {step.rawContent}
          </p>
        )}
      </div>
    </li>
  );
}

function getStatusMeta(status: TodoStatus) {
  switch (status) {
    case "completed":
      return {
        label: "Completed",
        icon: <CheckCircle2 className="h-3.5 w-3.5 text-emerald-500" />,
        indicatorClassName:
          "border-transparent bg-emerald-500/10 text-emerald-500",
        containerClassName:
          "border-emerald-400/30 bg-emerald-500/10 text-emerald-600",
        pillClassName: "bg-emerald-500/15 text-emerald-600",
        connectorClassName: "bg-emerald-500/40",
      };
    case "in_progress":
      return {
        label: "In progress",
        icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />,
        indicatorClassName: "border-primary/60 bg-primary/10 text-primary",
        containerClassName: "border-primary/50 bg-primary/10",
        pillClassName: "bg-primary/15 text-primary",
        connectorClassName: "bg-primary/40",
      };
    default:
      return {
        label: "Pending",
        icon: <Circle className="h-3.5 w-3.5 text-muted-foreground" />,
        indicatorClassName:
          "border-dashed border-muted-foreground/40 bg-background text-muted-foreground",
        containerClassName: "border-border/60 bg-background/80",
        pillClassName: "bg-muted/30 text-muted-foreground",
        connectorClassName: "bg-border/50",
      };
  }
}

function deriveSteps(todos: TodoItem[] | null): DerivedStep[] {
  if (!todos?.length) {
    return [];
  }

  return todos.map((todo, index) => {
    const title =
      pickFirstFilledText(todo.title, todo.content) ?? `Task ${index + 1}`;
    const description = pickFirstFilledText(
      todo.description,
      todo.rawContent,
    );

    return {
      index,
      title,
      description: description ?? "",
      status: todo.status ?? "pending",
      rawContent: todo.rawContent ?? todo.content ?? undefined,
    };
  });
}

function computeProgress(steps: DerivedStep[], ongoing: boolean) {
  const total = steps.length;
  const completed = steps.filter((step) => step.status === "completed").length;
  const percent = total === 0 ? 0 : (completed / total) * 100;
  const activeStep =
    steps.find((step) => step.status === "in_progress") ??
    (ongoing ? steps.find((step) => step.status === "pending") : undefined);
  return {
    completed,
    total,
    percent: Number.isFinite(percent) ? percent : 0,
    activeStep,
  };
}


const SUMMARY_TOOLS = new Set([
  "web_search",
  "crawl_tool",
  "local_search_tool",
  "python_repl_tool",
]);

function extractLatestToolActivity(
  messages: Message[],
): ToolActivitySummary | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (!message?.toolCalls?.length) continue;
    for (let j = message.toolCalls.length - 1; j >= 0; j -= 1) {
      const toolCall = message.toolCalls[j];
      if (!toolCall || !SUMMARY_TOOLS.has(toolCall.name)) continue;
      const normalizedArgs = normalizeToolArgs(toolCall.args);
      const status = toolCall.result === undefined ? "running" : "finished";
      let text = "";

      switch (toolCall.name) {
        case "web_search": {
          const query =
            typeof normalizedArgs.query === "string"
              ? normalizedArgs.query
              : typeof normalizedArgs.__raw === "string"
                ? normalizedArgs.__raw
                : "";
          text = query
            ? status === "running"
              ? `Searching for “${query}”`
              : `Search complete for “${query}”`
            : status === "running"
              ? "Searching the web…"
              : "Search complete";
          break;
        }
        case "crawl_tool": {
          const url =
            typeof normalizedArgs.url === "string"
              ? normalizedArgs.url
              : typeof normalizedArgs.start_url === "string"
                ? normalizedArgs.start_url
                : "";
          text = url
            ? status === "running"
              ? `Crawling ${truncateText(url, 60)}`
              : `Crawl finished for ${truncateText(url, 60)}`
            : status === "running"
              ? "Crawling content…"
              : "Crawl finished";
          break;
        }
        case "local_search_tool": {
          const query =
            typeof normalizedArgs.query === "string"
              ? normalizedArgs.query
              : typeof normalizedArgs.question === "string"
                ? normalizedArgs.question
                : "";
          text = query
            ? status === "running"
              ? `Scanning local resources for “${query}”`
              : `Local search complete for “${query}”`
            : status === "running"
              ? "Scanning local resources…"
              : "Local search complete";
          break;
        }
        case "python_repl_tool": {
          text =
            status === "running"
              ? "Executing Python snippet…"
              : "Python execution finished";
          break;
        }
        default:
          break;
      }

      if (text) {
        return {
          status,
          tool: toolCall.name as ToolActivitySummary["tool"],
          text,
        };
      }
    }
  }
  return null;
}

function renderToolIcon(
  tool: ToolActivitySummary["tool"],
  className?: string,
) {
  const baseClass = className ?? "h-4 w-4";
  if (tool === "web_search") {
    return <Search className={baseClass} />;
  }
  if (tool === "crawl_tool") {
    return <FileText className={baseClass} />;
  }
  if (tool === "local_search_tool") {
    return <BookOpenText className={baseClass} />;
  }
  return <PythonOutlined className={baseClass} />;
}

function truncateText(value: string, max = 80) {
  if (value.length <= max) return value;
  return `${value.slice(0, max - 1)}…`;
}

const ActivityMessage = React.memo(({ messageId }: { messageId: string }) => {
  const message = useMessage(messageId);
  if (message?.agent) {
    if (message.agent === "researcher" && message.isStreaming) {
      return (
        <div className="px-4 py-2">
          <RainbowText animated>Researching…</RainbowText>
        </div>
      );
    }
    if (message.agent === "researcher") {
      return null;
    }
    if (
      message.content &&
      message.agent !== "reporter" &&
      message.agent !== "planner"
    ) {
      const raw =
        typeof message.content === "string"
          ? message.content
          : JSON.stringify(message.content);
      // Filter out internal deep-agent operations to avoid noisy UI
      const blockedTools = new Set([
        "write_file",
        "write_todos",
        "ls",
        "task",
        "read_file",
        "edit_file",
      ]);
      const contentString = raw
        .split("\n")
        .filter((line) => {
          const t = line.trim();
          if (t.startsWith("Updated todo list") || t.startsWith("Updated file")) {
            return false;
          }
          if (t.startsWith("Running ")) {
            const match = /^Running\s+([a-zA-Z0-9_]+)\s*\(\)\s*$/.exec(t);
            if (match && blockedTools.has(match[1]!)) {
              return false;
            }
          }
          return true;
        })
        .join("\n")
        .trim();
      if (!contentString) {
        // Show a lightweight placeholder while internal operations are filtered
        if (message.isStreaming) {
          return (
            <div className="px-4 py-2">
              <RainbowText animated>Researching…</RainbowText>
            </div>
          );
        }
        return null;
      }
      return (
        <div className="px-4 py-2">
          <Markdown animated checkLinkCredibility>
            {contentString}
          </Markdown>
        </div>
      );
    }
  }
  return null;
});
ActivityMessage.displayName = "ActivityMessage";

const ActivityListItem = React.memo(({ messageId }: { messageId: string }) => {
  const message = useMessage(messageId);
  if (message) {
    // Render allowed tools as soon as we see tool calls, even while streaming
    if (message.toolCalls?.length) {
      const allowedTools = new Set([
        "web_search",
        "crawl_tool",
        "local_search_tool",
        "python_repl_tool",
      ]);
      for (const toolCall of message.toolCalls) {
        if (toolCall.result?.startsWith("Error")) {
          return null;
        }
        if (!allowedTools.has(toolCall.name)) {
          continue;
        }
        if (toolCall.name === "web_search") {
          return <WebSearchToolCall key={toolCall.id} toolCall={toolCall} />;
        } else if (toolCall.name === "crawl_tool") {
          return <CrawlToolCall key={toolCall.id} toolCall={toolCall} />;
        } else if (toolCall.name === "python_repl_tool") {
          return <PythonToolCall key={toolCall.id} toolCall={toolCall} />;
        } else if (toolCall.name === "local_search_tool") {
          return <RetrieverToolCall key={toolCall.id} toolCall={toolCall} />;
        }
      }
    }
    // Fallback: if no allowed tool rendered and message is streaming, show a subtle indicator
    if (message.isStreaming) {
      return (
        <div className="px-4 py-2">
          <RainbowText animated>Working…</RainbowText>
        </div>
      );
    }
  }
  return null;
});
ActivityListItem.displayName = "ActivityListItem";

const __pageCache = new LRUCache<string, string>({ max: 100 });
type SearchResult =
  | {
    type: "page";
    title: string;
    url: string;
    content: string;
  }
  | {
    type: "image";
    image_url: string;
    image_description: string;
  };

type NormalizedToolArgs = Record<string, unknown> & { __raw?: string };

function isPlainObject(value: unknown): value is Record<string, unknown> {
  return value != null && typeof value === "object" && !Array.isArray(value);
}

function normalizeToolArgs(args: ToolCallRuntime["args"]): NormalizedToolArgs {
  if (args == null) {
    return { __raw: "" };
  }

  if (typeof args === "string") {
    const raw = args.trim();
    if (!raw) {
      return { __raw: "" };
    }
    try {
      const parsed = JSON.parse(raw);
      if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
        return { ...(parsed as Record<string, unknown>), __raw: raw };
      }
    } catch {
      // fall through to returning raw payload
    }
    return { __raw: raw };
  }

  if (Array.isArray(args)) {
    const entries: Record<string, unknown> = {};
    args.forEach((item) => {
      if (isPlainObject(item)) {
        const key =
          typeof item.key === "string"
            ? item.key
            : typeof item.name === "string"
              ? item.name
              : undefined;
        if (key) {
          entries[key] = item.value;
        }
      }
    });
    return {
      ...entries,
      __raw: JSON.stringify(args),
    };
  }

  if (isPlainObject(args)) {
    const flattened = { ...args };
    if (isPlainObject(args.input)) {
      Object.assign(flattened, args.input);
    }
    return {
      ...flattened,
      __raw: JSON.stringify(args),
    };
  }

  return { __raw: String(args) };
}

function WebSearchToolCall({ toolCall }: { toolCall: ToolCallRuntime }) {
  const t = useTranslations("chat.research");
  const searching = toolCall.result === undefined;
  const normalizedArgs = useMemo(
    () => normalizeToolArgs(toolCall.args),
    [toolCall.args],
  );
  const query = useMemo(() => {
    const value = normalizedArgs.query;
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (
      typeof normalizedArgs.__raw === "string" &&
      normalizedArgs.__raw.trim()
    ) {
      return normalizedArgs.__raw.trim();
    }
    return undefined;
  }, [normalizedArgs]);
  const [searchResults, setSearchResults] = useState<SearchResult[] | undefined>();

  useEffect(() => {
    if (toolCall.result === undefined) {
      setSearchResults(undefined);
      return;
    }

    if (typeof toolCall.result !== "string" || toolCall.result.trim() === "") {
      return;
    }

    try {
      const parsed = parseJSON<SearchResult[] | undefined>(
        toolCall.result,
        undefined,
      );
      if (Array.isArray(parsed)) {
        const pageResults = parsed.filter(
          (
            result,
          ): result is Extract<SearchResult, { type: "page" }> =>
            result?.type === "page" &&
            typeof result.url === "string" &&
            typeof result.title === "string",
        );
        if (pageResults.length > 0) {
          appendResearchSources(
            pageResults.map((r) => ({ url: r.url, title: r.title })),
          );
        }

        parsed.forEach((result) => {
          if (result?.type === "page" && typeof result.url === "string") {
            __pageCache.set(result.url, result.title ?? result.url);
          }
        });
        setSearchResults(parsed);
      }
    } catch {
      // Keep previous results if parsing fails (e.g., non-JSON status message)
    }
  }, [toolCall.result]);
  const pageResults = useMemo(
    () => searchResults?.filter((result) => result.type === "page") ?? [],
    [searchResults],
  );
  const imageResults = useMemo(
    () => searchResults?.filter((result) => result.type === "image") ?? [],
    [searchResults],
  );
  return (
    <section className="mt-4 pl-4">
      <div className="font-medium italic">
        <RainbowText
          className="flex items-center"
          animated={searchResults === undefined}
        >
          <Search size={16} className={"mr-2"} />
          {query ? (
            <>
              <span>{t("searchingFor")}&nbsp;</span>
              <span className="max-w-[500px] overflow-hidden text-ellipsis whitespace-nowrap">
                {query}
              </span>
            </>
          ) : (
            <span>{t("searchingGeneric")}</span>
          )}
        </RainbowText>
      </div>
      <div className="pr-4">
        {pageResults && (
          <ul className="mt-2 flex flex-wrap gap-4">
            {searching &&
              [...Array(6)].map((_, i) => (
                <li
                  key={`search-result-${i}`}
                  className="flex h-40 w-40 gap-2 rounded-md text-sm"
                >
                  <Skeleton
                    className="to-accent h-full w-full rounded-md bg-gradient-to-tl from-slate-400"
                    style={{ animationDelay: `${i * 0.2}s` }}
                  />
                </li>
              ))}
            {pageResults
              .slice(0, MAX_PAGE_RESULTS)
              .map((searchResult, i) => {
                const shouldAnimate = i < MAX_PAGE_ANIMATIONS;
                return (
                  <motion.li
                    key={`search-result-${i}`}
                    className="text-muted-foreground bg-accent flex max-w-40 gap-2 rounded-md px-2 py-1 text-sm"
                    initial={shouldAnimate ? { opacity: 0, y: 10 } : { opacity: 1, y: 0 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={
                      shouldAnimate
                        ? {
                            duration: 0.15,
                            delay: Math.min(i * 0.05, 0.3),
                            ease: "easeOut",
                          }
                        : undefined
                    }
                  >
                    <FavIcon
                      className="mt-1"
                      url={searchResult.url}
                      title={searchResult.title}
                    />
                    <a href={searchResult.url} target="_blank">
                      {searchResult.title}
                    </a>
                  </motion.li>
                );
              })}
            {imageResults
              .slice(0, MAX_IMAGE_RESULTS)
              .map((searchResult, i) => {
                const shouldAnimate = i < MAX_IMAGE_ANIMATIONS;
                return (
                  <motion.li
                    key={`search-result-image-${i}`}
                    initial={shouldAnimate ? { opacity: 0, y: 10 } : { opacity: 1, y: 0 }}
                    animate={{ opacity: 1, y: 0 }}
                    transition={
                      shouldAnimate
                        ? {
                            duration: 0.15,
                            delay: Math.min(i * 0.05, 0.2),
                            ease: "easeOut",
                          }
                        : undefined
                    }
                  >
                    <a
                      className="flex flex-col gap-2 overflow-hidden rounded-md opacity-75 transition-opacity duration-300 hover:opacity-100"
                      href={searchResult.image_url}
                      target="_blank"
                    >
                      <Image
                        src={searchResult.image_url}
                        alt={searchResult.image_description}
                        className="bg-accent h-40 w-40 max-w-full rounded-md bg-cover bg-center bg-no-repeat"
                        imageClassName="hover:scale-110"
                        imageTransition
                      />
                    </a>
                  </motion.li>
                );
              })}
          </ul>
        )}
      </div>
    </section>
  );
}

function CrawlToolCall({ toolCall }: { toolCall: ToolCallRuntime }) {
  const t = useTranslations("chat.research");
  const normalizedArgs = useMemo(
    () => normalizeToolArgs(toolCall.args),
    [toolCall.args],
  );
  const url = useMemo(() => {
    const value = normalizedArgs.url;
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof normalizedArgs.__raw === "string" && normalizedArgs.__raw.trim()) {
      return normalizedArgs.__raw.trim();
    }
    return "";
  }, [normalizedArgs]);
  const title = useMemo(() => __pageCache.get(url), [url]);

  useEffect(() => {
    if (url && title) {
      appendResearchSources([{ url, title }]);
    }
  }, [url, title]);
  return (
    <section className="mt-4 pl-4">
      <div>
        <RainbowText
          className="flex items-center text-base font-medium italic"
          animated={toolCall.result === undefined}
        >
          <BookOpenText size={16} className={"mr-2"} />
          <span>{t("reading")}</span>
        </RainbowText>
      </div>
      <ul className="mt-2 flex flex-wrap gap-4">
        <motion.li
          className="text-muted-foreground bg-accent flex h-40 w-40 gap-2 rounded-md px-2 py-1 text-sm"
          initial={{ opacity: 0, y: 10 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{
            duration: 0.15,
            ease: "easeOut",
          }}
        >
          <FavIcon className="mt-1" url={url} title={title} />
          <a
            className="h-full flex-grow overflow-hidden text-ellipsis whitespace-nowrap"
            href={url}
            target="_blank"
          >
            {title ?? url}
          </a>
        </motion.li>
      </ul>
    </section>
  );
}

function RetrieverToolCall({ toolCall }: { toolCall: ToolCallRuntime }) {
  const t = useTranslations("chat.research");
  const searching = useMemo(() => {
    return toolCall.result === undefined;
  }, [toolCall.result]);
  const normalizedArgs = useMemo(
    () => normalizeToolArgs(toolCall.args),
    [toolCall.args],
  );
  const keywords = useMemo(() => {
    const value = normalizedArgs.keywords;
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof normalizedArgs.__raw === "string" && normalizedArgs.__raw.trim()) {
      return normalizedArgs.__raw.trim();
    }
    return "";
  }, [normalizedArgs]);
  const documents = useMemo<
    Array<{ id: string; title: string; content: string }>
  >(() => {
    return toolCall.result ? parseJSON(toolCall.result, []) : [];
  }, [toolCall.result]);
  return (
    <section className="mt-4 pl-4">
      <div className="font-medium italic">
        <RainbowText className="flex items-center" animated={searching}>
          <Search size={16} className={"mr-2"} />
          <span>{t("retrievingDocuments")}&nbsp;</span>
          <span className="max-w-[500px] overflow-hidden text-ellipsis whitespace-nowrap">
            {keywords}
          </span>
        </RainbowText>
      </div>
      <div className="pr-4">
        {documents && (
          <ul className="mt-2 flex flex-wrap gap-4">
            {searching &&
              [...Array(2)].map((_, i) => (
                <li
                  key={`search-result-${i}`}
                  className="flex h-40 w-40 gap-2 rounded-md text-sm"
                >
                  <Skeleton
                    className="to-accent h-full w-full rounded-md bg-gradient-to-tl from-slate-400"
                    style={{ animationDelay: `${i * 0.2}s` }}
                  />
                </li>
              ))}
            {documents?.map((doc, i) => {
              const shouldAnimate = i < MAX_DOCUMENT_ANIMATIONS;
              return (
                <motion.li
                  key={`search-result-${i}`}
                  className="text-muted-foreground bg-accent flex max-w-40 gap-2 rounded-md px-2 py-1 text-sm"
                  initial={shouldAnimate ? { opacity: 0, y: 10 } : { opacity: 1, y: 0 }}
                  animate={{ opacity: 1, y: 0 }}
                  transition={
                    shouldAnimate
                      ? {
                          duration: 0.15,
                          delay: Math.min(i * 0.05, 0.2),
                          ease: "easeOut",
                        }
                      : undefined
                  }
                >
                  <FileText size={32} />
                  {doc.title} (chunk-{i},size-{doc.content.length})
                </motion.li>
              );
            })}
          </ul>
        )}
      </div>
    </section>
  );
}

function PythonToolCall({ toolCall }: { toolCall: ToolCallRuntime }) {
  const t = useTranslations("chat.research");
  const normalizedArgs = useMemo(
    () => normalizeToolArgs(toolCall.args),
    [toolCall.args],
  );
  const code = useMemo<string | undefined>(() => {
    const value = normalizedArgs.code;
    if (typeof value === "string" && value.length) {
      return value;
    }
    if (typeof normalizedArgs.__raw === "string" && normalizedArgs.__raw.length) {
      return normalizedArgs.__raw;
    }
    return undefined;
  }, [normalizedArgs]);
  const { resolvedTheme } = useTheme();
  return (
    <section className="mt-4 pl-4">
      <div className="flex items-center">
        <PythonOutlined className={"mr-2"} />
        <RainbowText
          className="text-base font-medium italic"
          animated={toolCall.result === undefined}
        >
          {t("runningPythonCode")}
        </RainbowText>
      </div>
      <div>
        <div className="bg-accent mt-2 max-h-[400px] max-w-[calc(100%-120px)] overflow-y-auto rounded-md p-2 text-sm">
          <SyntaxHighlighter
            language="python"
            style={resolvedTheme === "dark" ? dark : docco}
            customStyle={{
              background: "transparent",
              border: "none",
              boxShadow: "none",
            }}
          >
            {code?.trim() ?? ""}
          </SyntaxHighlighter>
        </div>
      </div>
      {toolCall.result && <PythonToolCallResult result={toolCall.result} />}
    </section>
  );
}

function PythonToolCallResult({ result }: { result: string }) {
  const t = useTranslations("chat.research");
  const { resolvedTheme } = useTheme();
  const hasError = useMemo(
    () => result.includes("Error executing code:\n"),
    [result],
  );
  const error = useMemo(() => {
    if (hasError) {
      const parts = result.split("```\nError: ");
      if (parts.length > 1) {
        return parts[1]!.trim();
      }
    }
    return null;
  }, [result, hasError]);
  const stdout = useMemo(() => {
    if (!hasError) {
      const parts = result.split("```\nStdout: ");
      if (parts.length > 1) {
        return parts[1]!.trim();
      }
    }
    return null;
  }, [result, hasError]);
  return (
    <>
      <div className="mt-4 font-medium italic">
        {hasError ? t("errorExecutingCode") : t("executionOutput")}
      </div>
      <div className="bg-accent mt-2 max-h-[400px] max-w-[calc(100%-120px)] overflow-y-auto rounded-md p-2 text-sm">
        <SyntaxHighlighter
          language="plaintext"
          style={resolvedTheme === "dark" ? dark : docco}
          customStyle={{
            color: hasError ? "red" : "inherit",
            background: "transparent",
            border: "none",
            boxShadow: "none",
          }}
        >
          {error ?? stdout ?? "(empty)"}
        </SyntaxHighlighter>
      </div>
    </>
  );
}
