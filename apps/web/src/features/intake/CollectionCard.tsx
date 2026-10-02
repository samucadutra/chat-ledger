"use client";

import { useState } from "react";
import { Button } from "@/components/ui/Button";
import type { Collection } from "./api";
import { groundTruthUrl } from "@/features/generator/api";
import { formatBytes, formatDate, formatDateTime } from "./format";

export function CollectionCard({ collection }: { collection: Collection }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(collection.sha256);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1500);
    } catch {
      setCopied(false);
    }
  }

  const range =
    collection.export_date_from && collection.export_date_to
      ? `${formatDate(collection.export_date_from)} → ${formatDate(collection.export_date_to)}`
      : "No dated messages";

  return (
    <article
      aria-label={`Collection ${collection.original_filename}`}
      data-testid="collection-card"
      className="border border-rule-strong bg-paper-raised px-5 py-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="min-w-0 truncate text-[15px] font-semibold">{collection.original_filename}</h3>
        <span className="cl-label border border-rule px-1.5 py-0.5">
          {collection.generation
            ? `Synthetic · seed ${collection.generation.seed} · ${collection.generation.profile}`
            : collection.source === "generator"
              ? "Generated"
              : "Uploaded"}
        </span>
      </header>
      <dl className="mt-3 grid grid-cols-1 gap-x-8 gap-y-2 text-[13px] sm:grid-cols-3">
        <div>
          <dt className="cl-label">Size</dt>
          <dd className="font-mono">{formatBytes(collection.size_bytes)}</dd>
        </div>
        <div>
          <dt className="cl-label">Conversations</dt>
          <dd className="font-mono">{collection.conversation_count} conversations</dd>
        </div>
        <div>
          <dt className="cl-label">Date range</dt>
          <dd className="font-mono">{range}</dd>
        </div>
        <div>
          <dt className="cl-label">Added</dt>
          <dd className="font-mono">{formatDateTime(collection.added_at)} UTC</dd>
        </div>
        <div>
          <dt className="cl-label">Entries</dt>
          <dd className="font-mono">{collection.entry_count}</dd>
        </div>
      </dl>
      <div className="mt-3 flex items-center gap-3 border-t border-rule pt-3">
        <span className="cl-label shrink-0">SHA-256</span>
        <code data-testid="collection-sha256" className="min-w-0 flex-1 break-all text-[12px]">
          {collection.sha256}
        </code>
        <Button variant="ghost" aria-label="Copy SHA-256" onClick={copy}>
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      {collection.generation?.has_ground_truth ? (
        <div className="mt-3 border-t border-rule pt-3 text-[13px]">
          <a
            href={groundTruthUrl(collection.matter_id, collection.id)}
            download={`ground-truth-${collection.generation.seed}.json`}
            className="font-medium text-accent underline"
          >
            Download ground truth
          </a>
        </div>
      ) : null}
    </article>
  );
}
