"use client";

import { Button } from "@/components/ui/Button";
import { isActive, type Generation } from "./api";

const DUPLICATE = "COLLECTION_DUPLICATE";

export interface GenerationCardProps {
  generation: Generation;
  onRetry: (generation: Generation) => void;
  retrying?: boolean;
}

/** Pending (queued/running) and failed generations; done ones become collection cards. */
export function GenerationCard({ generation, onRetry, retrying }: GenerationCardProps) {
  const { progress_messages: done, total_messages: total } = generation;
  const title = `Synthetic export · seed ${generation.seed} · ${generation.profile}`;

  if (isActive(generation)) {
    const percent = total > 0 ? Math.min(100, Math.round((done / total) * 100)) : 0;
    return (
      <article
        aria-label={title}
        data-testid="generation-card"
        data-state={generation.state}
        className="border border-rule-strong bg-paper-raised px-5 py-4"
      >
        <h3 className="text-[15px] font-semibold">{title}</h3>
        <p className="mt-2 font-mono text-[13px]" aria-live="polite">
          Generating… {done} / {total} messages
        </p>
        <div
          role="progressbar"
          aria-label="Generation progress"
          aria-valuemin={0}
          aria-valuemax={total}
          aria-valuenow={done}
          className="mt-2 h-1.5 w-full bg-paper-sunken"
        >
          <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
        </div>
      </article>
    );
  }

  const error = generation.error;
  const isDuplicate = error?.code === DUPLICATE;
  return (
    <article
      aria-label={title}
      data-testid="generation-card"
      data-state="failed"
      className="border border-accent bg-paper-raised px-5 py-4"
    >
      <h3 className="text-[15px] font-semibold">{title}</h3>
      <p role="alert" className="mt-2 text-[13px] text-accent">
        {isDuplicate ? error?.message : `Generation failed: ${error?.message ?? "Unknown error"}`}
      </p>
      {isDuplicate ? null : (
        <div className="mt-3">
          <Button variant="secondary" disabled={retrying} onClick={() => onRetry(generation)}>
            Retry
          </Button>
        </div>
      )}
    </article>
  );
}
