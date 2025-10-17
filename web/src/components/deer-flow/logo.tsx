// Copyright (c) 2025 Bytedance Ltd. and/or its affiliates
// SPDX-License-Identifier: MIT

import Link from "next/link";
import Image from "next/image";

export function Logo({ label = "HOME" }: { label?: string }) {
  return (
    <Link
      className="group relative flex items-center gap-2 rounded-full border border-border/40 bg-background/70 px-3 py-1.5 text-xs font-semibold uppercase tracking-[0.35em] text-foreground/70 shadow-lg shadow-black/5 backdrop-blur transition hover:border-primary/60 hover:text-primary"
      href="/"
    >
      <span className="relative flex h-8 w-8 items-center justify-center overflow-hidden rounded-2xl bg-gradient-to-br from-primary via-primary/70 to-purple-500 text-white shadow-lg transition group-hover:scale-105">
        <Image
          alt="Morgana tab logo"
          src="/tab-logo.svg"
          fill
          sizes="32px"
          className="object-cover"
          priority
        />
      </span>
      <span className="hidden pr-1 md:inline">{label}</span>
    </Link>
  );
}
