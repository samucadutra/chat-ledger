"use client";

import { useEffect, useRef, useState } from "react";
import { ErrorBanner } from "@/components/state/ErrorBanner";
import { probeHealth } from "@/lib/api/health";
import { API_URL } from "@/lib/config";

export interface ApiStatusBannerProps {
  intervalMs?: number;
  timeoutMs?: number;
  apiUrl?: string;
}

/**
 * Polls `GET /health` every 5 s (3 s timeout). After a failed poll it shows a
 * persistent banner at the top of the page; the next successful poll clears it.
 */
export function ApiStatusBanner({ intervalMs = 5000, timeoutMs = 3000, apiUrl = API_URL }: ApiStatusBannerProps) {
  const [down, setDown] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let cancelled = false;
    const tick = async () => {
      const ok = await probeHealth(timeoutMs);
      if (cancelled) return;
      setDown(!ok);
      timer.current = setTimeout(tick, intervalMs);
    };
    void tick();
    return () => {
      cancelled = true;
      if (timer.current) clearTimeout(timer.current);
    };
  }, [intervalMs, timeoutMs]);

  if (!down) return null;
  return (
    <ErrorBanner className="shrink-0">
      API unavailable at {apiUrl}. Check{" "}
      <code className="rounded-sm bg-accent-hover px-1 py-px">`docker compose ps`</code>.
    </ErrorBanner>
  );
}
