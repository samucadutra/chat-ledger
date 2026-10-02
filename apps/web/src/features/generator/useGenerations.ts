"use client";

import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef } from "react";
import { matterKeys } from "@/features/intake/api";
import { generationKeys, isActive, listGenerations, type Generation } from "./api";

export const POLL_MS = 2_000;

/** Generations of a matter, refreshed every 2 s while any is queued or running. */
export function useGenerations(matterId: string) {
  const queryClient = useQueryClient();
  const query = useQuery({
    queryKey: generationKeys.list(matterId),
    queryFn: () => listGenerations(matterId),
    refetchInterval: (q) => (q.state.data?.some(isActive) ? POLL_MS : false),
  });
  const wasActive = useRef<Set<string>>(new Set());

  useEffect(() => {
    const items: Generation[] = query.data ?? [];
    const finished = [...wasActive.current].some((id) => items.find((g) => g.id === id && g.state === "done"));
    wasActive.current = new Set(items.filter(isActive).map((g) => g.id));
    if (finished) void queryClient.invalidateQueries({ queryKey: matterKeys.collections(matterId) });
  }, [query.data, matterId, queryClient]);

  return query;
}
