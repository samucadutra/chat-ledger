import type { ReactNode } from "react";

export interface HeaderBarProps {
  /** Slot for the current matter (filled by F02; empty in F01). */
  currentMatter?: ReactNode;
}

export function HeaderBar({ currentMatter }: HeaderBarProps) {
  return (
    <header className="sticky top-0 z-20 flex h-[var(--cl-header-height)] shrink-0 items-center justify-between border-b border-rule bg-paper px-8">
      <div className="flex min-w-0 items-baseline gap-3" data-slot="current-matter">
        <span className="cl-label">Matter</span>
        {currentMatter ? (
          <div className="truncate text-[14px] font-medium">{currentMatter}</div>
        ) : (
          <span className="text-[13px] text-ink-faint">None selected</span>
        )}
      </div>
      <span className="cl-label hidden sm:inline">Local · single user</span>
    </header>
  );
}
