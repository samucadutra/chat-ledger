import { apiClient, unwrap, type components } from "@/lib/api/client";

export type Matter = components["schemas"]["MatterOut"];
export type Collection = components["schemas"]["CollectionOut"];

export async function listMatters(): Promise<Matter[]> {
  const data = await unwrap(apiClient.GET("/api/v1/matters"));
  return data.items;
}

export function createMatter(input: { name: string; description?: string | null }): Promise<Matter> {
  return unwrap(apiClient.POST("/api/v1/matters", { body: input }));
}

export function getMatter(matterId: string): Promise<Matter> {
  return unwrap(apiClient.GET("/api/v1/matters/{matter_id}", { params: { path: { matter_id: matterId } } }));
}

export async function listCollections(matterId: string): Promise<Collection[]> {
  const data = await unwrap(
    apiClient.GET("/api/v1/matters/{matter_id}/collections", {
      params: { path: { matter_id: matterId } },
    }),
  );
  return data.items;
}

export const matterKeys = {
  all: ["matters"] as const,
  detail: (id: string) => ["matters", id] as const,
  collections: (id: string) => ["matters", id, "collections"] as const,
};
