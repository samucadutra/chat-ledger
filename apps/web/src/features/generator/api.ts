import { apiClient, unwrap, type components } from "@/lib/api/client";
import { API_URL } from "@/lib/config";

export type Generation = components["schemas"]["GenerationOut"];

export interface CreateGenerationInput {
  seed: number;
  preset: string;
  profile: string;
  messages?: number | null;
  conversations?: number | null;
  overlap_of_collection_id?: string | null;
}

export const generationKeys = {
  list: (matterId: string) => ["matters", matterId, "generations"] as const,
};

export async function listGenerations(matterId: string): Promise<Generation[]> {
  const data = await unwrap(
    apiClient.GET("/api/v1/matters/{matter_id}/generations", {
      params: { path: { matter_id: matterId } },
    }),
  );
  return data.items;
}

export function createGeneration(matterId: string, body: CreateGenerationInput): Promise<Generation> {
  return unwrap(
    apiClient.POST("/api/v1/matters/{matter_id}/generations", {
      params: { path: { matter_id: matterId } },
      body,
    }),
  );
}

export function retryGeneration(matterId: string, generationId: string): Promise<Generation> {
  return unwrap(
    apiClient.POST("/api/v1/matters/{matter_id}/generations/{generation_id}/retry", {
      params: { path: { matter_id: matterId, generation_id: generationId } },
    }),
  );
}

export function groundTruthUrl(matterId: string, collectionId: string): string {
  return `${API_URL}/api/v1/matters/${matterId}/collections/${collectionId}/ground-truth`;
}

export const isActive = (g: Generation) => g.state === "queued" || g.state === "running";
