// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import type { Metadata } from "next";

import { ChatShell } from "./chat-shell";

export const metadata: Metadata = {
  title: "Chat",
};

export default function ChatPage() {
  return <ChatShell />;
}
