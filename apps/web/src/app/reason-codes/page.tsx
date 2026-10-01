import type { Metadata } from "next";
import { PageHeader } from "@/components/shell/PageHeader";
import { EmptyState } from "@/components/state/EmptyState";

export const metadata: Metadata = { title: "Reason Codes" };

export default function ReasonCodesPage() {
  return (
    <>
      <PageHeader
        eyebrow="Reference"
        title="Reason Codes"
        description="Every message that does not reach an export is accounted for by exactly one reason code."
      />
      <EmptyState
        eyebrow="Catalogue pending"
        title="Reason codes will be listed here once quality gates are available."
      />
    </>
  );
}
