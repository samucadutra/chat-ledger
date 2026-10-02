"use client";

import { Button } from "@/components/ui/Button";
import { formatMegabytes, formatSpeed } from "./format";
import type { UploadProgress } from "./uploadCollection";

export type UploadState =
  | { kind: "idle" }
  | { kind: "uploading"; filename: string; progress: UploadProgress }
  | { kind: "verifying"; filename: string }
  | { kind: "error"; filename: string; message: string }
  | { kind: "interrupted"; filename: string; percent: number };

export interface UploadRowProps {
  state: Exclude<UploadState, { kind: "idle" }>;
  onRetry: () => void;
  onDismiss: () => void;
  onCancel?: () => void;
}

const rowClass = "flex flex-wrap items-center gap-x-4 gap-y-2 border border-rule-strong bg-paper-raised px-4 py-3";

export function UploadRow({ state, onRetry, onDismiss, onCancel }: UploadRowProps) {
  if (state.kind === "uploading") {
    const { progress } = state;
    return (
      <div data-testid="upload-row" data-state="uploading" className={rowClass}>
        <span className="min-w-0 flex-1 truncate font-medium">{state.filename}</span>
        <span className="font-mono text-[13px]">{progress.percent}%</span>
        <span className="font-mono text-[12px] text-ink-muted">
          {formatMegabytes(progress.loaded)} / {formatMegabytes(progress.total)}
        </span>
        <span className="font-mono text-[12px] text-ink-muted">{formatSpeed(progress.bytesPerSecond)}</span>
        {onCancel ? (
          <Button variant="ghost" onClick={onCancel}>
            Cancel
          </Button>
        ) : null}
        <div
          role="progressbar"
          aria-label={`Uploading ${state.filename}`}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-valuenow={progress.percent}
          className="h-1 w-full bg-paper-sunken"
        >
          <div className="h-full bg-accent" style={{ width: `${progress.percent}%` }} />
        </div>
      </div>
    );
  }

  if (state.kind === "verifying") {
    return (
      <div data-testid="upload-row" data-state="verifying" role="status" className={rowClass}>
        <span className="min-w-0 flex-1 truncate font-medium">{state.filename}</span>
        <span className="text-[13px] text-ink-muted">Verifying export structure…</span>
      </div>
    );
  }

  if (state.kind === "interrupted") {
    return (
      <div data-testid="upload-row" data-state="interrupted" role="alert" className={rowClass}>
        <span className="min-w-0 flex-1 truncate font-medium">{state.filename}</span>
        <span className="text-[13px] text-accent">Upload interrupted at {state.percent}%. Retry?</span>
        <Button variant="secondary" onClick={onRetry}>
          Retry
        </Button>
        <Button variant="ghost" onClick={onDismiss}>
          Dismiss
        </Button>
      </div>
    );
  }

  return (
    <div data-testid="upload-row" data-state="error" role="alert" className={rowClass}>
      <span className="min-w-0 flex-1 truncate font-medium">{state.filename}</span>
      <span className="basis-full text-[13px] text-accent">{state.message}</span>
      <Button variant="secondary" onClick={onRetry}>
        Retry
      </Button>
      <Button variant="ghost" onClick={onDismiss}>
        Dismiss
      </Button>
    </div>
  );
}
