// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { PythonOutlined } from "@ant-design/icons";
import { motion } from "framer-motion";
import { LRUCache } from "lru-cache";
import { CheckCircle2, ChevronDown, Circle, Loader2 } from "lucide-react";
import {
  BookOpenText,
  FileText,
  PencilRuler,
  Search,
} from "lucide-react";
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
import { Tooltip } from "~/components/deer-flow/tooltip";
import {
  Accordion,
  AccordionContent,
  AccordionItem,
  AccordionTrigger,
} from "~/components/ui/accordion";
import { Badge } from "~/components/ui/badge";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "~/components/ui/collapsible";
import { Skeleton } from "~/components/ui/skeleton";

const MAX_ANIMATED_ACTIVITY_ITEMS = 10;
const ACTIVITY_ANIMATION_DELAY = 0.05;
const MAX_PAGE_RESULTS = 20;
const MAX_PAGE_ANIMATIONS = 6;
const MAX_IMAGE_RESULTS = 10;
const MAX_IMAGE_ANIMATIONS = 4;
const MAX_DOCUMENT_ANIMATIONS = 4;
import { findMCPTool } from "~/core/mcp";
import type { Message, ToolCallRuntime } from "~/core/messages";
import { useMessage, useStore } from "~/core/store";
import { parseJSON } from "~/core/utils";
import { cn } from "~/lib/utils";

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

type TodoStatus = "pending" | "in_progress" | "completed";

interface DerivedStep {
  index: number;
  title: string;
  description: string;
  status: TodoStatus;
  rawContent?: string;
}

interface PlanStepLike {
  title?: string;
  description?: string;
  status?: string;
  content?: string;
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

function hasMeaningfulTodo(item?: TodoItemLike | null) {
  if (!item) return false;
  return Boolean(
    pickFirstFilledText(item.content, item.title, item.description),
  );
}

interface ToolActivitySummary {
  status: "running" | "finished";
  tool: "web_search" | "crawl_tool" | "local_search_tool" | "python_repl_tool";
  text: string;
}
function PlanActivityOverview({
  planMessageId,
  ongoing,
  activityMessages,
}: {
  planMessageId: string;
  ongoing: boolean;
  activityMessages: Message[];
}) {
  const planMessage = useMessage(planMessageId);

  const planPayload = useMemo(() => {
    const parsed = parseJSON<Record<string, unknown> | null>(
      planMessage?.content,
      null,
    );
    if (!parsed) {
      return null;
    }
    const steps = Array.isArray(parsed.steps)
      ? parsed.steps
          .map((step) => normalizePlanStep(step))
          .filter((step): step is PlanStepLike => step !== null)
      : [];
    const title =
      typeof parsed.title === "string" && parsed.title.trim()
        ? parsed.title.trim()
        : "Research Plan";
    return { title, steps };
  }, [planMessage?.content]);

  const todos = useMemo(
    () => extractTodosFromMessages(activityMessages),
    [activityMessages],
  );

  const steps = useMemo<DerivedStep[]>(() => {
    const derived = deriveSteps(planPayload, todos, ongoing);
    return derived;
  }, [ongoing, planPayload, todos]);

  const progress = useMemo(() => computeProgress(steps, ongoing), [steps, ongoing]);
  const latestAction = useMemo(
    () => extractLatestToolActivity(activityMessages),
    [activityMessages],
  );

  const [expanded, setExpanded] = useState(true);

  if (!planPayload && !steps.length) {
    return (
      <div className="rounded-2xl border border-border/60 bg-card/80 p-4">
        <div className="flex items-center gap-2">
          <Loader2 className="h-4 w-4 animate-spin text-primary" />
          <span className="text-sm font-medium text-muted-foreground">
            Preparing research plan…
          </span>
        </div>
        <p className="mt-2 text-xs text-muted-foreground">
          The planner is generating actionable steps for this deep agent run.
        </p>
      </div>
    );
  }

  return (
    <Collapsible
      open={expanded}
      onOpenChange={setExpanded}
      className={cn(
        "rounded-2xl border border-border/60 bg-card/95 shadow-sm",
        "supports-[backdrop-filter]:backdrop-blur",
      )}
    >
        <CollapsibleTrigger asChild>
          <button
            type="button"
            className="flex w-full items-start justify-between gap-3 rounded-2xl px-4 py-3 text-left transition-colors hover:bg-card/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary/60"
            aria-expanded={expanded}
        >
          <div className="flex flex-1 flex-col gap-1">
            <p className="text-xs uppercase tracking-wide text-muted-foreground">
              Deep Agent Plan
            </p>
            <h3
              className={cn(
                "font-semibold leading-tight",
                expanded ? "text-lg" : "text-sm",
              )}
            >
              {planPayload?.title ?? "Research Plan"}
            </h3>
            {!expanded && (
              <p className="text-xs text-muted-foreground">
                {progress.percent >= 100
                  ? "Plan completed"
                  : `${progress.completed}/${steps.length} steps complete · ${Math.round(progress.percent)}%`}
              </p>
            )}
          </div>
          <div className="flex items-center gap-3">
            {steps.length > 0 && (
              <Badge
                variant="outline"
                className="text-[11px] font-semibold uppercase tracking-tight text-muted-foreground"
              >
                {progress.completed}/{steps.length} steps
              </Badge>
            )}
            <div className="flex h-8 w-8 items-center justify-center rounded-full border border-muted-foreground/40 bg-muted/40 text-muted-foreground transition-transform">
              <ChevronDown
                className={cn(
                  "h-4 w-4 transition-transform duration-300",
                  expanded && "-rotate-180",
                )}
              />
            </div>
          </div>
        </button>
      </CollapsibleTrigger>
      <CollapsibleContent className="px-4 pb-4">
        <div className="space-y-4">
          {steps.length > 0 && (
            <div>
              <div className="relative h-2 rounded-full bg-muted/60">
                <div
                  className={cn(
                    "absolute left-0 top-0 h-2 rounded-full bg-primary transition-all duration-500",
                    progress.percent === 0 && "bg-primary/60",
                  )}
                  style={{ width: `${progress.percent}%` }}
                />
              </div>
              <div className="mt-1 flex items-center justify-between text-xs text-muted-foreground">
                <span>
                  {progress.percent >= 100
                    ? "Plan completed"
                    : ongoing
                      ? "Agent is executing tasks"
                      : "Awaiting agent activity"}
                </span>
                <span>{Math.round(progress.percent)}%</span>
              </div>
            </div>
          )}

          {progress.activeStep && (
            <div className="rounded-xl border border-dashed border-primary/40 bg-background/80 p-3">
              <div className="flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
                <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />
                Active Step
              </div>
              <p className="mt-2 text-sm font-medium">
                {progress.activeStep.index + 1}. {progress.activeStep.title}
              </p>
              {progress.activeStep.description && (
                <p className="mt-1 text-xs text-muted-foreground">
                  {progress.activeStep.description}
                </p>
              )}
              {latestAction && (
                <div className="mt-3 flex items-center gap-2 text-xs text-muted-foreground">
                  {renderToolIcon(latestAction.tool, "h-4 w-4 text-primary/80")}
                  <span>{latestAction.text}</span>
                </div>
              )}
            </div>
          )}

          <div className="max-h-[55vh] space-y-2 overflow-y-auto pr-1">
            {steps.map((step) => (
              <PlanStepRow key={step.index} step={step} />
            ))}
          </div>
        </div>
        </CollapsibleContent>
    </Collapsible>
  );
}

function PlanStepRow({ step }: { step: DerivedStep }) {
  const statusMeta = getStatusMeta(step.status);
  return (
    <div
      className={cn(
        "flex items-start gap-3 rounded-xl border border-transparent px-3 py-2 transition-colors",
        step.status === "in_progress" && "border-primary/40 bg-primary/5",
        step.status === "completed" && "bg-muted/40",
        step.status === "pending" && "hover:bg-muted/30",
      )}
    >
      <div
        className={cn(
          "mt-0.5 flex h-6 w-6 flex-shrink-0 items-center justify-center rounded-full border text-xs",
          statusMeta.indicatorClassName,
        )}
      >
        {statusMeta.icon}
      </div>
      <div className="flex-1">
        <div className="flex flex-wrap items-center gap-2">
          <p className="text-sm font-medium leading-snug">
            {step.index + 1}. {step.title}
          </p>
          <Badge
            variant={step.status === "pending" ? "outline" : "secondary"}
            className={cn(
              "text-[10px] uppercase tracking-wide",
              step.status === "pending" && "bg-transparent text-muted-foreground",
            )}
          >
            {statusMeta.label}
          </Badge>
        </div>
        {step.description && (
          <p className="mt-1 text-xs text-muted-foreground">{step.description}</p>
        )}
      </div>
    </div>
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
      };
    case "in_progress":
      return {
        label: "In progress",
        icon: <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" />,
        indicatorClassName: "border-primary/60 bg-primary/10 text-primary",
      };
    default:
      return {
        label: "Pending",
        icon: <Circle className="h-3.5 w-3.5 text-muted-foreground" />,
        indicatorClassName:
          "border-dashed border-muted-foreground/40 text-muted-foreground",
      };
  }
}

type TodoItemLike = {
  content?: string;
  description?: string;
  title?: string;
  status?: string;
};

function normalizePlanStep(step: unknown): PlanStepLike | null {
  if (!step || typeof step !== "object") return null;
  const record = step as Record<string, unknown>;
  const title =
    getStringField(record, "title") ?? getStringField(record, "name");
  const description =
    getStringField(record, "description") ?? getStringField(record, "detail");
  const status = getStringField(record, "status");
  const content =
    getStringField(record, "content") ?? getStringField(record, "task");
  return { title, description, status, content };
}

function getStringField(
  record: Record<string, unknown>,
  key: string,
): string | undefined {
  const value = record[key];
  return typeof value === "string" ? value : undefined;
}

function deriveSteps(
  planPayload: { steps: PlanStepLike[] } | null,
  todos: TodoItemLike[] | null,
  ongoing: boolean,
): DerivedStep[] {
  const planSteps = planPayload?.steps ?? [];
  const todoSteps = todos ?? [];

  let derived: DerivedStep[] = [];

  if (todoSteps.length > 0) {
    derived = todoSteps.map((todoStep, index) => {
      const planStep = planSteps[index];
      const title =
        pickFirstFilledText(
          todoStep?.title,
          todoStep?.content,
          planStep?.title,
          planStep?.content,
        ) ?? `Step ${index + 1}`;
      const description =
        pickFirstFilledText(todoStep?.description, planStep?.description) ?? "";
      const statusCandidate =
        (typeof todoStep?.status === "string" ? todoStep.status : undefined) ??
        planStep?.status;
      return {
        index,
        title,
        description,
        status: normalizeStatus(statusCandidate),
        rawContent: todoStep?.content ?? planStep?.content,
      };
    });
  } else if (planSteps.length > 0) {
    derived = planSteps.map((planStep, index) => ({
      index,
      title:
        pickFirstFilledText(planStep?.title, planStep?.content) ??
        `Step ${index + 1}`,
      description:
        pickFirstFilledText(planStep?.description, planStep?.content) ?? "",
      status: normalizeStatus(planStep?.status),
      rawContent: planStep?.content,
    }));
  }

  if (ongoing && derived.length > 0) {
    const hasActive = derived.some((step) => step.status === "in_progress");
    if (!hasActive) {
      const firstPending = derived.find((step) => step.status === "pending");
      if (firstPending) {
        firstPending.status = "in_progress";
      }
    }
  }

  return derived;
}

function normalizeStatus(status?: string | null): TodoStatus {
  if (!status) return "pending";
  const normalized = status.toLowerCase().replace(/[\s-]+/g, "_");
  if (
    normalized.includes("complete") ||
    normalized === "done" ||
    normalized === "finished" ||
    normalized === "success"
  ) {
    return "completed";
  }
  if (
    normalized.includes("progress") ||
    normalized.includes("active") ||
    normalized.includes("working") ||
    normalized.includes("current")
  ) {
    return "in_progress";
  }
  return "pending";
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

function extractTodosFromMessages(
  messages: Message[],
): TodoItemLike[] | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const message = messages[i];
    if (!message) {
      continue;
    }
    const fromContent = parseTodoPayload(message.content);
    if (fromContent?.length) {
      return fromContent;
    }
    if (message.toolCalls?.length) {
      for (const toolCall of message.toolCalls) {
        if (!toolCall) continue;
        const fromResult = parseTodoPayload(toolCall.result);
        if (fromResult?.length) {
          return fromResult;
        }
        const fromArgs = parseTodoPayload(toolCall.args);
        if (fromArgs?.length) {
          return fromArgs;
        }
      }
    }
  }
  return null;
}

function parseTodoPayload(payload: unknown) {
  if (payload == null) return null;
  if (typeof payload === "string") {
    const trimmed = payload.trim();
    if (!trimmed) return null;
    const parsed = parseJSON<unknown>(trimmed, undefined);
    const normalized = normalizeTodoValue(parsed);
    if (normalized?.length) {
      return normalized;
    }
    const candidates = [trimmed.indexOf("{"), trimmed.indexOf("[")].filter(
      (index) => index >= 0,
    );
    if (candidates.length) {
      const jsonStart = Math.min(...candidates);
      const startChar = trimmed[jsonStart]!;
      const endChar = startChar === "{" ? "}" : "]";
      const endIndex = trimmed.lastIndexOf(endChar);
      if (endIndex > jsonStart) {
        const candidate = trimmed.slice(jsonStart, endIndex + 1);
        const parsedCandidate = parseJSON<unknown>(candidate, undefined);
        return normalizeTodoValue(parsedCandidate);
      }
    }
    return null;
  }
  return normalizeTodoValue(payload);
}

function normalizeTodoValue(value: unknown): TodoItemLike[] | null {
  if (Array.isArray(value)) {
    const todos = value
      .map((item) => normalizeTodoItem(item))
      .filter((item): item is TodoItemLike => hasMeaningfulTodo(item));
    return todos.length ? todos : null;
  }
  if (value && typeof value === "object") {
    const record = value as { todos?: unknown; state?: unknown };
    if (Array.isArray(record.todos)) {
      const todos = record.todos
        .map((item) => normalizeTodoItem(item))
        .filter((item): item is TodoItemLike => hasMeaningfulTodo(item));
      return todos.length ? todos : null;
    }
    if (record.state && typeof record.state === "object") {
      const stateRecord = record.state as { todos?: unknown };
      if (Array.isArray(stateRecord.todos)) {
        const todos = stateRecord.todos
          .map((item) => normalizeTodoItem(item))
          .filter((item): item is TodoItemLike => hasMeaningfulTodo(item));
        return todos.length ? todos : null;
      }
    }
  }
  return null;
}

function normalizeTodoItem(item: unknown): TodoItemLike | null {
  if (!item || typeof item !== "object") return null;
  const record = item as (Partial<TodoItemLike> & { state?: string });
  const contentCandidate = pickFirstFilledText(
    record.content,
    record.title,
    record.description,
  );
  const description =
    typeof record.description === "string" ? record.description : undefined;
  const title = typeof record.title === "string" ? record.title : undefined;
  const status =
    typeof record.status === "string"
      ? record.status
      : typeof record.state === "string"
        ? record.state
        : undefined;
  return {
    content: contentCandidate,
    description,
    title,
    status,
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
      const parsed = parseJSON(toolCall.result, undefined);
      if (Array.isArray(parsed)) {
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
    const value = normalizedArgs["url"];
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof normalizedArgs.__raw === "string" && normalizedArgs.__raw.trim()) {
      return normalizedArgs.__raw.trim();
    }
    return "";
  }, [normalizedArgs]);
  const title = useMemo(() => __pageCache.get(url), [url]);
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
    const value = normalizedArgs["keywords"];
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
    const value = normalizedArgs["code"];
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

function MCPToolCall({ toolCall }: { toolCall: ToolCallRuntime }) {
  const tool = useMemo(() => findMCPTool(toolCall.name), [toolCall.name]);
  const { resolvedTheme } = useTheme();
  return (
    <section className="mt-4 pl-4">
      <div className="w-fit overflow-y-auto rounded-md py-0">
        <Accordion type="single" collapsible className="w-full">
          <AccordionItem value="item-1">
            <AccordionTrigger>
              <Tooltip title={tool?.description}>
                <div className="flex items-center font-medium italic">
                  <PencilRuler size={16} className={"mr-2"} />
                  <RainbowText
                    className="pr-0.5 text-base font-medium italic"
                    animated={toolCall.result === undefined}
                  >
                    Running {toolCall.name ? toolCall.name + "()" : "MCP tool"}
                  </RainbowText>
                </div>
              </Tooltip>
            </AccordionTrigger>
            <AccordionContent>
              {toolCall.result && (
                <div className="bg-accent max-h-[400px] max-w-[560px] overflow-y-auto rounded-md text-sm">
                  <SyntaxHighlighter
                    language="json"
                    style={resolvedTheme === "dark" ? dark : docco}
                    customStyle={{
                      background: "transparent",
                      border: "none",
                      boxShadow: "none",
                    }}
                  >
                    {toolCall.result.trim()}
                  </SyntaxHighlighter>
                </div>
              )}
            </AccordionContent>
          </AccordionItem>
        </Accordion>
      </div>
    </section>
  );
}
