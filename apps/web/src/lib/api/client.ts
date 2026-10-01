import createClient from "openapi-fetch";
import { API_URL } from "@/lib/config";
import type { components, paths } from "./schema";

export type HealthResponse = components["schemas"]["HealthResponse"];

/** The uniform API error envelope: `{ error: { code, message, details } }`. */
export interface ErrorEnvelope {
  error: { code: string; message: string; details: Record<string, unknown> };
}

/** An HTTP error returned by the API, parsed from the error envelope. */
export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly details: Record<string, unknown>;

  constructor(status: number, code: string, message: string, details: Record<string, unknown> = {}) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.details = details;
  }
}

/** The API could not be reached at all (network failure, timeout, CORS). */
export class ApiUnavailableError extends Error {
  constructor(
    readonly baseUrl: string,
    options?: { cause?: unknown },
  ) {
    super(`API unavailable at ${baseUrl}.`, options);
    this.name = "ApiUnavailableError";
  }
}

function isEnvelope(body: unknown): body is ErrorEnvelope {
  if (typeof body !== "object" || body === null || !("error" in body)) return false;
  const error = (body as { error: unknown }).error;
  return (
    typeof error === "object" &&
    error !== null &&
    typeof (error as { code?: unknown }).code === "string" &&
    typeof (error as { message?: unknown }).message === "string"
  );
}

/** Convert any non-2xx response body into an `ApiError`. */
export function toApiError(status: number, body: unknown): ApiError {
  if (isEnvelope(body)) {
    const { code, message, details } = body.error;
    return new ApiError(status, code, message, details ?? {});
  }
  return new ApiError(status, `HTTP_${status}`, `Request failed with status ${status}.`);
}

export function createApiClient(baseUrl: string = API_URL) {
  // Resolve fetch lazily so test interceptors (MSW) and polyfills are honoured.
  return createClient<paths>({ baseUrl, fetch: (request) => globalThis.fetch(request) });
}

/** Typed API client shared by every feature. */
export const apiClient = createApiClient();

type FetchResult<T> = { data?: T; error?: unknown; response: Response };

/**
 * Await an `openapi-fetch` call and return its data, throwing `ApiError` for
 * error envelopes and `ApiUnavailableError` when the API cannot be reached.
 */
export async function unwrap<T>(call: Promise<FetchResult<T>>, baseUrl: string = API_URL): Promise<T> {
  let result: FetchResult<T>;
  try {
    result = await call;
  } catch (cause) {
    throw new ApiUnavailableError(baseUrl, { cause });
  }
  if (!result.response.ok) {
    throw toApiError(result.response.status, result.error);
  }
  return result.data as T;
}
