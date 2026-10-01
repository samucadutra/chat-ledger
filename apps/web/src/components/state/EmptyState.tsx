import type { ReactNode } from "react";
import { cn } from "@/lib/cn";

export interface EmptyStateProps {
  title: string;
  description?: ReactNode;
  action?: ReactNode;
  eyebrow?: string;
  className?: string;
}

/** Reusable empty state: a ruled ledger card with a message and an optional action. */
export function EmptyState({ title, description, action, eyebrow, className }: EmptyStateProps) {
  return (
    <section
      aria-label={title}
      className={cn(
        "relative border border-dashed border-rule-strong bg-paper-raised px-8 py-12",
        "bg-[repeating-linear-gradient(to_bottom,transparent_0,transparent_27px,var(--cl-rule)_27px,var(--cl-rule)_28px)] bg-[length:100%_28px]",
        className,
      )}
    >
      <div className="mx-auto flex max-w-md flex-col items-center gap-3 bg-paper-raised px-6 py-4 text-center">
        {eyebrow ? <span className="cl-label">{eyebrow}</span> : null}
        <p className="text-[15px] font-medium text-ink">{title}</p>
        {description ? <div className="text-[13px] text-ink-muted">{description}</div> : null}
        {action ? <div className="mt-2">{action}</div> : null}
      </div>
    </section>
  );
}
