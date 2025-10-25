// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { Message, ToolCallRuntime } from "../messages";
import { parseJSON } from "../utils";

export type TodoStatus = "pending" | "in_progress" | "completed";

export interface TodoItem {
  title?: string;
  description?: string;
  content?: string;
  status: TodoStatus;
  rawStatus?: string;
  rawContent?: string;
}

type TodoCandidate = {
  title?: unknown;
  description?: unknown;
  content?: unknown;
  task?: unknown;
  name?: unknown;
  detail?: unknown;
  status?: unknown;
  state?: unknown;
};

const STATUS_ALIASES: Record<string, TodoStatus> = {
  done: "completed",
  finished: "completed",
  complete: "completed",
  completed: "completed",
  success: "completed",
  succeed: "completed",
  successful: "completed",
  accomplished: "completed",
  in_progress: "in_progress",
  inprogres: "in_progress",
  running: "in_progress",
  executing: "in_progress",
  active: "in_progress",
  working: "in_progress",
  ongoing: "in_progress",
  pending: "pending",
  todo: "pending",
  "to-do": "pending",
  waiting: "pending",
  queued: "pending",
  new: "pending",
  not_started: "pending",
  "not-started": "pending",
};

export function extractTodosFromMessages(messages: Message[]): TodoItem[] | null {
  for (let i = messages.length - 1; i >= 0; i -= 1) {
    const todos = extractTodosFromMessage(messages[i]);
    if (todos?.length) {
      return todos;
    }
  }
  return null;
}

export function extractTodosFromMessage(message: Message | undefined): TodoItem[] | null {
  if (!message) return null;

  let latest: TodoItem[] | null = null;

  const fromContent = parseTodoPayload(message.content);
  if (fromContent?.length) {
    latest = fromContent;
  }

  if (message.toolCalls?.length) {
    for (const toolCall of message.toolCalls) {
      if (!toolCall) continue;
      const resultTodos = parseTodoPayload(toolCall.result);
      if (resultTodos?.length) {
        latest = resultTodos;
      }
      const argsTodos = parseTodoPayload(toolCall.args);
      if (argsTodos?.length) {
        latest = argsTodos;
      }
    }
  }

  return latest;
}

export function parseTodoPayload(payload: unknown): TodoItem[] | null {
  if (payload == null) return null;

  if (typeof payload === "string") {
    const trimmed = payload.trim();
    if (!trimmed) return null;

    const direct = attemptParse(trimmed);
    if (direct?.length) {
      return direct;
    }

    const jsonStartIndex = findJsonStart(trimmed);
    if (jsonStartIndex != null) {
      const jsonCandidate = trimmed.slice(jsonStartIndex);
      const extracted = attemptParse(jsonCandidate);
      if (extracted?.length) {
        return extracted;
      }
    }

    return null;
  }

  return finalizeTodos(payload);
}

function attemptParse(text: string): TodoItem[] | null {
  const parsed = parseJSON<unknown>(text, undefined);
  return finalizeTodos(parsed);
}

function finalizeTodos(value: unknown): TodoItem[] | null {
  if (!value) return null;

  if (Array.isArray(value)) {
    const todos = value
      .map(normalizeCandidate)
      .filter((item): item is TodoItem => item != null);
    return todos.length ? todos : null;
  }

  if (typeof value === "object") {
    const record = value as {
      todos?: unknown;
      state?: { todos?: unknown };
      data?: { todos?: unknown };
      result?: unknown;
    };

    const viaTodos = finalizeTodos(record.todos);
    if (viaTodos?.length) {
      return viaTodos;
    }

    const viaState = finalizeTodos(record.state?.todos);
    if (viaState?.length) {
      return viaState;
    }

    const viaData = finalizeTodos(record.data?.todos ?? record.result);
    if (viaData?.length) {
      return viaData;
    }
  }

  return null;
}

function normalizeCandidate(candidate: unknown): TodoItem | null {
  if (!candidate || typeof candidate !== "object") return null;
  const record = candidate as TodoCandidate;

  const content = pickFirstText(
    record.content,
    record.task,
    record.title,
    record.description,
    record.name,
    record.detail,
  );
  const description = pickFirstText(record.description, record.detail);
  const title = pickFirstText(record.title, record.name, record.task);

  const rawStatus = pickFirstText(record.status, record.state);
  const status = normalizeStatus(rawStatus);

  if (!content && !title && !description) {
    return null;
  }

  return {
    content: content ?? undefined,
    description: description ?? undefined,
    title: title ?? undefined,
    rawStatus: rawStatus ?? undefined,
    status,
    rawContent: typeof record.content === "string" ? record.content : undefined,
  };
}

function normalizeStatus(status: unknown): TodoStatus {
  if (typeof status !== "string") return "pending";
  const collapsed = status
    .replace(/([a-z0-9])([A-Z])/g, "$1_$2")
    .toLowerCase()
    .replace(/[^a-z]+/g, "_")
    .replace(/^_+|_+$/g, "");

  if (!collapsed) return "pending";
  if (STATUS_ALIASES[collapsed]) {
    return STATUS_ALIASES[collapsed];
  }
  if (collapsed.includes("progress") || collapsed.includes("active")) {
    return "in_progress";
  }
  if (collapsed.includes("complete") || collapsed.includes("success")) {
    return "completed";
  }
  return "pending";
}

function pickFirstText(...values: Array<unknown>): string | null {
  for (const raw of values) {
    if (typeof raw === "string") {
      const trimmed = raw.trim();
      if (trimmed) {
        return trimmed;
      }
    }
  }
  return null;
}

function findJsonStart(text: string): number | null {
  const start = Math.min(
    ...["{", "["].map((char) => {
      const idx = text.indexOf(char);
      return idx === -1 ? Number.POSITIVE_INFINITY : idx;
    }),
  );
  return Number.isFinite(start) ? start : null;
}

export function hasTodos(toolCalls: ToolCallRuntime[] | undefined): boolean {
  if (!toolCalls?.length) return false;
  return toolCalls.some((call) => {
    const fromArgs = parseTodoPayload(call.args);
    const fromResult = parseTodoPayload(call.result);
    const hasArgs = (fromArgs?.length ?? 0) > 0;
    const hasResult = (fromResult?.length ?? 0) > 0;
    return hasArgs || hasResult;
  });
}
