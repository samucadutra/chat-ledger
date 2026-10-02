"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useParams } from "next/navigation";
import { EmptyState } from "@/components/state/EmptyState";
import { ErrorBanner } from "@/components/state/ErrorBanner";
import { Skeleton } from "@/components/state/Skeleton";
import { listCollections, matterKeys } from "@/features/intake/api";
import { CollectionCard } from "@/features/intake/CollectionCard";
import { DropZone } from "@/features/intake/DropZone";
import { UploadRow } from "@/features/intake/UploadRow";
import { useCollectionUpload } from "@/features/intake/useCollectionUpload";
import { Button } from "@/components/ui/Button";
import { generationKeys, retryGeneration } from "@/features/generator/api";
import { GenerateDialog } from "@/features/generator/GenerateDialog";
import { GenerationCard } from "@/features/generator/GenerationCard";
import { useGenerations } from "@/features/generator/useGenerations";

export default function CollectionsPage() {
  const { matterId } = useParams<{ matterId: string }>();
  const { data, isPending, error } = useQuery({
    queryKey: matterKeys.collections(matterId),
    queryFn: () => listCollections(matterId),
  });
  const upload = useCollectionUpload(matterId);
  const queryClient = useQueryClient();
  const generations = useGenerations(matterId);
  const [generateOpen, setGenerateOpen] = useState(false);
  const retry = useMutation({
    mutationFn: (generationId: string) => retryGeneration(matterId, generationId),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: generationKeys.list(matterId) }),
  });
  const visibleGenerations = (generations.data ?? []).filter((g) => g.state !== "done");
  const baseOptions = (data ?? []).filter((c) => c.generation);

  return (
    <section aria-labelledby="collections-heading" className="flex flex-col gap-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 id="collections-heading" className="text-[18px] font-semibold">
            Collections
          </h2>
          <p className="text-[13px] text-ink-muted">
            Every collection in this matter is included in each processing run.
          </p>
        </div>
        <div data-slot="collection-actions" className="flex items-center gap-2">
          <Button variant="secondary" onClick={() => setGenerateOpen(true)}>
            Generate synthetic export
          </Button>
        </div>
        <GenerateDialog
          matterId={matterId}
          open={generateOpen}
          onOpenChange={setGenerateOpen}
          baseOptions={baseOptions}
        />
      </div>

      <DropZone disabled={upload.busy} onFile={(file) => void upload.start(file)} />

      {upload.state.kind !== "idle" ? (
        <UploadRow
          state={upload.state}
          onRetry={upload.retry}
          onDismiss={upload.dismiss}
          onCancel={upload.state.kind === "uploading" ? upload.cancel : undefined}
        />
      ) : null}

      {visibleGenerations.length > 0 ? (
        <div className="flex flex-col gap-4">
          {visibleGenerations.map((generation) => (
            <GenerationCard
              key={generation.id}
              generation={generation}
              retrying={retry.isPending}
              onRetry={(g) => retry.mutate(g.id)}
            />
          ))}
        </div>
      ) : null}

      {isPending ? <Skeleton rows={2} label="Loading collections" /> : null}
      {error ? <ErrorBanner>{error.message}</ErrorBanner> : null}
      {data && data.length === 0 && upload.state.kind === "idle" && visibleGenerations.length === 0 ? (
        <EmptyState eyebrow="0 collections" title="No collections yet. Drop a Slack export ZIP to add one." />
      ) : null}
      {data && data.length > 0 ? (
        <div className="flex flex-col gap-4">
          {data.map((collection) => (
            <CollectionCard key={collection.id} collection={collection} />
          ))}
        </div>
      ) : null}
    </section>
  );
}
