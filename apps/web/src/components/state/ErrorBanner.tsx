"use client";

import { useState, type ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface ErrorBannerProps {
  children: ReactNode;
  /** Dismissible banners render a close button; persistent ones do not. */
  dismissible?: boolean;
  onDismiss?: () => void;
  tone?: "error" | "warning";
  className?: string;
}

/** Full-width alert strip used for API and page-level errors. */
export function ErrorBanner({ children, dismissible = false, onDismiss, tone = "error", className }: ErrorBannerProps) {
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  return (
    <div
      role="alert"
      data-tone={tone}
      className={cn(
        "flex items-center gap-3 px-6 py-2.5 text-[13px]",
        tone === "error"
          ? "bg-accent text-accent-ink"
          : "border-b border-rule-strong bg-accent-wash text-ink",
        className,
      )}
    >
      <span aria-hidden className="font-mono text-[11px] uppercase tracking-[0.1em] opacity-80">
        {tone === "error" ? "Error" : "Notice"}
      </span>
      <span className="flex-1">{children}</span>
      {dismissible ? (
        <button
          type="button"
          aria-label="Dismiss"
          onClick={() => {
            setDismissed(true);
            onDismiss?.();
          }}
          className="h-7 w-7 rounded-sm opacity-80 hover:opacity-100"
        >
          ×
        </button>
      ) : null}
    </div>
  );
}
