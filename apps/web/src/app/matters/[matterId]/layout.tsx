"use client";

import { useQuery } from "@tanstack/react-query";
import Link from "next/link";
import { useParams } from "next/navigation";
import type { ReactNode } from "react";
import { PageHeader } from "@/components/shell/PageHeader";
import { usePublishCurrentMatter } from "@/components/shell/CurrentMatter";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorBanner } from "@/components/state/ErrorBanner";
import { Skeleton } from "@/components/state/Skeleton";
import { ApiError } from "@/lib/api/client";
import { getMatter, matterKeys } from "@/features/intake/api";
import { MatterTabs } from "@/features/intake/MatterTabs";

export default function MatterLayout({ children }: { children: ReactNode }) {
  const { matterId } = useParams<{ matterId: string }>();
  const { data: matter, isPending, error } = useQuery({
    queryKey: matterKeys.detail(matterId),
    queryFn: () => getMatter(matterId),
    retry: (count, err) => !(err instanceof ApiError && err.status === 404) && count < 1,
  });
  usePublishCurrentMatter(matter?.name ?? null);

  if (isPending) return <Skeleton rows={3} label="Loading matter" />;

  if (error) {
    if (error instanceof ApiError && error.status === 404) {
      return (
        <EmptyState
          eyebrow="404"
          title="Matter not found"
          description="This matter does not exist."
          action={
            <Link href="/matters" className="text-[13px] font-medium text-accent underline">
              Back to matters
            </Link>
          }
        />
      );
    }
    return <ErrorBanner>{error.message}</ErrorBanner>;
  }

  return (
    <>
      <PageHeader eyebrow="Matter" title={matter.name} description={matter.description ?? undefined} />
      <MatterTabs matterId={matter.id} />
      {children}
    </>
  );
}
