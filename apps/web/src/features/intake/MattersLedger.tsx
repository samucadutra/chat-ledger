"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useState } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorBanner } from "@/components/state/ErrorBanner";
import { Skeleton } from "@/components/state/Skeleton";
import { Button } from "@/components/ui/Button";
import { listMatters, matterKeys } from "./api";
import { formatBytes, formatDate } from "./format";
import { NewMatterDialog } from "./NewMatterDialog";

/** The matters ledger: a table of matters, newest first, with an empty state. */
export function MattersLedger() {
  const [dialogOpen, setDialogOpen] = useState(false);
  const { data, isPending, isError, error } = useQuery({ queryKey: matterKeys.all, queryFn: listMatters });
  const empty = data !== undefined && data.length === 0;
  const newMatter = (
    <Button variant="primary" onClick={() => setDialogOpen(true)}>
      New matter
    </Button>
  );

  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Matters"
        description="Each matter groups the Slack export collections and the processing runs produced from them."
        actions={data !== undefined && !empty ? newMatter : undefined}
      />
      {isPending ? <Skeleton rows={4} label="Loading matters" /> : null}
      {isError ? (
        <ErrorBanner>{error instanceof Error ? error.message : "Could not load matters."}</ErrorBanner>
      ) : null}
      {empty ? (
        <EmptyState eyebrow="0 matters" title="No matters yet. Create one to start." action={newMatter} />
      ) : null}
      {data && data.length > 0 ? (
        <table className="w-full border-collapse text-left text-[14px]">
          <thead>
            <tr className="border-b border-rule-strong">
              <th scope="col" className="cl-label py-2 pr-4 font-normal">
                Name
              </th>
              <th scope="col" className="cl-label py-2 pr-4 text-right font-normal">
                Collections
              </th>
              <th scope="col" className="cl-label py-2 pr-4 text-right font-normal">
                Size
              </th>
              <th scope="col" className="cl-label py-2 font-normal">
                Created
              </th>
            </tr>
          </thead>
          <tbody>
            {data.map((matter) => (
              <tr key={matter.id} className="border-b border-rule hover:bg-paper-raised">
                <td className="py-3 pr-4">
                  <Link href={`/matters/${matter.id}/collections`} className="font-medium hover:underline">
                    {matter.name}
                  </Link>
                  {matter.description ? (
                    <p className="max-w-md truncate text-[12px] text-ink-faint">{matter.description}</p>
                  ) : null}
                </td>
                <td className="py-3 pr-4 text-right font-mono text-[13px]">{matter.collection_count}</td>
                <td className="py-3 pr-4 text-right font-mono text-[13px]">
                  {formatBytes(matter.total_size_bytes)}
                </td>
                <td className="py-3 font-mono text-[13px]">{formatDate(matter.created_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      ) : null}
      <NewMatterDialog open={dialogOpen} onOpenChange={setDialogOpen} />
    </>
  );
}
