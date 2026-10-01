import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";
import { Button } from "@/components/ui/Button";

export const metadata: Metadata = { title: "Matters" };

export default function MattersPage() {
  return (
    <>
      <PageHeader
        eyebrow="Workspace"
        title="Matters"
        description="Each matter groups the Slack export collections and the processing runs produced from them."
      />
      <EmptyState
        eyebrow="0 matters"
        title="No matters yet. Create one to start."
        action={<Button variant="primary">New matter</Button>}
      />
    </>
  );
}
