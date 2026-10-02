import { redirect } from "next/navigation";

export default async function MatterIndexPage({ params }: { params: Promise<{ matterId: string }> }) {
  const { matterId } = await params;
  redirect(`/matters/${matterId}/collections`);
}
