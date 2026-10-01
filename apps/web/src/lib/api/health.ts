import { apiClient } from "./client";

/** One `/health` probe with a hard timeout. Resolves `true` only for a 2xx answer. */
export async function probeHealth(timeoutMs = 3000): Promise<boolean> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  const timedOut = new Promise<false>((resolve) => {
    timer = setTimeout(() => resolve(false), timeoutMs);
  });
  const probe = apiClient.GET("/health").then(
    ({ response }) => response.ok,
    () => false,
  );
  try {
    return await Promise.race([probe, timedOut]);
  } finally {
    clearTimeout(timer);
  }
}
