// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import { cn } from "~/lib/utils";

export function FavIcon({
  className,
  url,
  title,
}: {
  className?: string;
  url: string;
  title?: string;
}) {
  const fallbackIcon =
    "https://perishablepress.com/wp/wp-content/images/2021/favicon-standard.png";

  const faviconUrl = (() => {
    try {
      if (typeof url !== "string" || url.trim() === "") {
        return fallbackIcon;
      }
      const parsed = new URL(url);
      return `${parsed.origin}/favicon.ico`;
    } catch {
      return fallbackIcon;
    }
  })();

  return (
    <img
      className={cn("bg-accent h-4 w-4 rounded-full shadow-sm", className)}
      width={16}
      height={16}
      src={faviconUrl}
      alt={title}
      onError={(e) => {
        e.currentTarget.src = fallbackIcon;
      }}
    />
  );
}
