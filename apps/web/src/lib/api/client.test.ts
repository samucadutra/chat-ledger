import { http, HttpResponse } from "msw";
import { describe, expect, it } from "vitest";
import { API_URL, healthyBody } from "../../../tests/mocks/handlers";
import { server } from "../../../tests/mocks/server";
import { ApiError, ApiUnavailableError, apiClient, toApiError, unwrap } from "./client";

describe("apiClient", () => {
  it("returns typed data on success", async () => {
    const data = await unwrap(apiClient.GET("/health"));
    expect(data).toEqual(healthyBody);
  });

  it("parses_error_envelope_into_ApiError", async () => {
    server.use(
      http.get(`${API_URL}/health`, () =>
        HttpResponse.json(
          { error: { code: "NOT_FOUND", message: "Route GET /x not found.", details: { a: 1 } } },
          { status: 404 },
        ),
      ),
    );
    const err = await unwrap(apiClient.GET("/health")).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({
      status: 404,
      code: "NOT_FOUND",
      message: "Route GET /x not found.",
      details: { a: 1 },
    });
  });

  it("network_failure_raises_ApiUnavailableError", async () => {
    server.use(http.get(`${API_URL}/health`, () => HttpResponse.error()));
    const err = await unwrap(apiClient.GET("/health")).catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiUnavailableError);
    expect((err as Error).message).toBe(`API unavailable at ${API_URL}.`);
  });

  it("falls back to an HTTP_<status> code for non-envelope bodies", () => {
    const err = toApiError(502, "<html>bad gateway</html>");
    expect(err.code).toBe("HTTP_502");
    expect(err.status).toBe(502);
  });
});
