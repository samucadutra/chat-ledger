import type { Metadata } from "next";
import { MattersLedger } from "@/features/intake/MattersLedger";

export const metadata: Metadata = { title: "Matters" };

export default function MattersPage() {
  return <MattersLedger />;
}
