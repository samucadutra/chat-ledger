"use client";

import Link from "next/link";
import { Tooltip } from "@/components/ui/Tooltip";
import { cn } from "@/lib/cn";

export const DISABLED_TAB_HINT = "Available after a completed processing run";

const TABS = [
  { key: "collections", label: "Collections", enabled: true },
  { key: "runs", label: "Runs", enabled: false },
  { key: "conversations", label: "Conversations", enabled: false },
  { key: "search", label: "Search", enabled: false },
  { key: "exports", label: "Exports", enabled: false },
] as const;

const tabBase =
  "relative -mb-px inline-flex h-10 items-center border-b-2 px-4 text-[13px] font-medium tracking-[0.01em]";

/** Route-based tab bar for a matter. Only Collections exists until runs ship. */
export function MatterTabs({ matterId, active = "collections" }: { matterId: string; active?: string }) {
  return (
    <div role="tablist" aria-label="Matter sections" className="mb-6 flex border-b border-rule">
      {TABS.map((tab) => {
        if (tab.enabled) {
          const selected = tab.key === active;
          return (
            <Link
              key={tab.key}
              role="tab"
              aria-selected={selected}
              href={`/matters/${matterId}/${tab.key}`}
              className={cn(
                tabBase,
                selected ? "border-accent text-ink" : "border-transparent text-ink-muted hover:text-ink",
              )}
            >
              {tab.label}
            </Link>
          );
        }
        return (
          <Tooltip key={tab.key} content={DISABLED_TAB_HINT}>
            <span
              role="tab"
              aria-selected={false}
              aria-disabled="true"
              tabIndex={0}
              className={cn(tabBase, "cursor-not-allowed border-transparent text-ink-faint")}
            >
              {tab.label}
            </span>
          </Tooltip>
        );
      })}
    </div>
  );
}
