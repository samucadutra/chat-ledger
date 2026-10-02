import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, type RenderResult } from "@testing-library/react";
import type { ReactElement, ReactNode } from "react";
import { CurrentMatterProvider } from "@/components/shell/CurrentMatter";
import { TooltipProvider } from "@/components/ui/Tooltip";
import { API_URL } from "./mocks/handlers";
import type { Collection, Matter } from "@/features/intake/api";

export function renderWithProviders(ui: ReactElement): RenderResult {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  function Wrapper({ children }: { children: ReactNode }) {
    return (
      <QueryClientProvider client={client}>
        <TooltipProvider>
          <CurrentMatterProvider>{children}</CurrentMatterProvider>
        </TooltipProvider>
      </QueryClientProvider>
    );
  }
  return render(ui, { wrapper: Wrapper });
}

export const ACME_ID = "7f3c1d52-0a6e-4f3b-9a51-2f7d1c9e8b10";

export function makeMatter(overrides: Partial<Matter> = {}): Matter {
  return {
    id: ACME_ID,
    name: "Acme v. Beta",
    description: null,
    created_at: "2026-10-01T19:02:11.481Z",
    collection_count: 0,
    total_size_bytes: 0,
    ...overrides,
  };
}

export function makeCollection(overrides: Partial<Collection> = {}): Collection {
  return {
    id: "c0a8012e-5b1f-4c7e-8d2a-6f9b3e1d4a77",
    matter_id: ACME_ID,
    sha256: "9b1f0c5e3d7a2b6c8e4f1a0d9c7b5e3f2a1d0c9b8e7f6a5d4c3b2a1f0e9d8c7b",
    original_filename: "export-50conv-90d.zip",
    size_bytes: 35518,
    source: "upload",
    entry_count: 152,
    conversation_count: 50,
    export_date_from: "2024-01-03",
    export_date_to: "2024-04-01",
    root_prefix: "",
    added_at: "2026-10-01T19:05:44.120Z",
    ...overrides,
  };
}

export const matterUrl = (id = ACME_ID) => `${API_URL}/api/v1/matters/${id}`;
