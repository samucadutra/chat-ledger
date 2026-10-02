"use client";

import type { ReactNode } from "react";
import { useCurrentMatterName } from "./CurrentMatter";

export interface HeaderBarProps {
  /** Explicit override for the current matter; defaults to the `CurrentMatter` context. */
  currentMatter?: ReactNode;
}

export function HeaderBar({ currentMatter }: HeaderBarProps) {
  const contextName = useCurrentMatterName();
  const matter = currentMatter ?? contextName;
  return (
    <header className="sticky top-0 z-20 flex h-[var(--cl-header-height)] shrink-0 items-center justify-between border-b border-rule bg-paper px-8">
      <div className="flex min-w-0 items-baseline gap-3" data-slot="current-matter">
        <span className="cl-label">Matter</span>
        {matter ? (
          <div className="truncate text-[14px] font-medium">{matter}</div>
        ) : (
          <span className="text-[13px] text-ink-faint">None selected</span>
        )}
      </div>
      <span className="cl-label hidden sm:inline">Local · single user</span>
    </header>
  );
}
