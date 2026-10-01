import { cn } from "@/lib/cn";

export interface SkeletonProps {
  rows?: number;
  className?: string;
  label?: string;
}

/** Loading placeholder: shimmering ledger rows. */
export function Skeleton({ rows = 3, className, label = "Loading" }: SkeletonProps) {
  return (
    <div role="status" aria-live="polite" aria-label={label} className={cn("flex flex-col", className)}>
      {Array.from({ length: rows }, (_, i) => (
        <div key={i} className="flex items-center gap-4 border-b border-rule py-3">
          <span
            className="h-3 w-24 rounded-sm bg-[linear-gradient(90deg,var(--cl-paper-sunken),var(--cl-rule),var(--cl-paper-sunken))] bg-[length:400px_100%] animate-[cl-shimmer_1.2s_linear_infinite]"
          />
          <span
            className="h-3 flex-1 rounded-sm bg-[linear-gradient(90deg,var(--cl-paper-sunken),var(--cl-rule),var(--cl-paper-sunken))] bg-[length:400px_100%] animate-[cl-shimmer_1.2s_linear_infinite]"
            style={{ maxWidth: `${60 + ((i * 17) % 35)}%` }}
          />
        </div>
      ))}
      <span className="sr-only">{label}…</span>
    </div>
  );
}
