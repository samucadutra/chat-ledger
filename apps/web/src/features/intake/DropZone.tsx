"use client";

import { useRef, useState, type DragEvent } from "react";
import { Button } from "@/components/ui/Button";
import { cn } from "@/lib/cn";
import { formatBytes } from "./format";

export const MAX_UPLOAD_BYTES = 2_147_483_648;

/** Client-side pre-checks mirroring the API rules; returns an error message or `null`. */
export function validateFile(file: File): string | null {
  if (!file.name.toLowerCase().endsWith(".zip")) return "File must be a .zip archive.";
  if (file.size > MAX_UPLOAD_BYTES) return `File exceeds the 2 GB limit (${formatBytes(file.size)}).`;
  return null;
}

export interface DropZoneProps {
  disabled?: boolean;
  onFile: (file: File) => void;
}

export function DropZone({ disabled = false, onFile }: DropZoneProps) {
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragging, setDragging] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function accept(files: FileList | File[]) {
    if (disabled) return;
    const list = Array.from(files);
    const first = list[0];
    if (!first) return;
    if (list.length > 1) {
      setError("Upload one ZIP at a time.");
      return;
    }
    const problem = validateFile(first);
    setError(problem);
    if (!problem) onFile(first);
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    accept(event.dataTransfer.files);
  }

  return (
    <div className="flex flex-col gap-2">
      <div
        data-testid="drop-zone"
        aria-disabled={disabled}
        onDragOver={(e) => {
          e.preventDefault();
          if (!disabled) setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          "flex flex-col items-center gap-3 border border-dashed px-6 py-10 text-center transition-colors",
          dragging ? "border-accent bg-accent-wash" : "border-rule-strong bg-paper-raised",
          disabled ? "opacity-60" : null,
        )}
      >
        <p className="text-[14px] font-medium">Drop a Slack export ZIP here</p>
        <p className="text-[12px] text-ink-muted">Up to 2 GB. The file is hashed and validated on arrival.</p>
        <Button variant="secondary" disabled={disabled} onClick={() => inputRef.current?.click()}>
          Choose ZIP file
        </Button>
        <input
          ref={inputRef}
          type="file"
          accept=".zip"
          aria-label="Slack export ZIP file"
          disabled={disabled}
          className="sr-only"
          onChange={(e) => {
            if (e.target.files) accept(e.target.files);
            e.target.value = "";
          }}
        />
      </div>
      {error ? (
        <p role="alert" data-testid="drop-zone-error" className="text-[13px] text-accent">
          {error}
        </p>
      ) : null}
    </div>
  );
}
