import { act, render, screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { API_URL } from "../../../tests/mocks/handlers";
import { server } from "../../../tests/mocks/server";
import { ApiStatusBanner } from "./ApiStatusBanner";

const BANNER = "API unavailable at http://localhost:8000. Check `docker compose ps`.";

async function flush(ms = 0) {
  await act(async () => {
    await vi.advanceTimersByTimeAsync(ms);
  });
}

describe("ApiStatusBanner", () => {
  beforeEach(() => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
  });
  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders_nothing_when_health_ok", async () => {
    render(<ApiStatusBanner />);
    await flush(10);
    await flush(5000);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("shows_banner_after_failed_poll", async () => {
    render(<ApiStatusBanner />);
    await flush(10);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    server.use(http.get(`${API_URL}/health`, () => HttpResponse.error()));
    await flush(5000);
    const banner = await screen.findByRole("alert");
    expect(banner).toHaveTextContent(BANNER);
  });

  it("treats_non_2xx_health_as_unavailable", async () => {
    server.use(http.get(`${API_URL}/health`, () => HttpResponse.json({}, { status: 503 })));
    render(<ApiStatusBanner />);
    expect(await screen.findByRole("alert")).toHaveTextContent("API unavailable");
  });

  it("clears_banner_when_health_recovers", async () => {
    server.use(http.get(`${API_URL}/health`, () => HttpResponse.error()));
    render(<ApiStatusBanner />);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    server.resetHandlers();
    await flush(5000);
    await flush(10);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("times_out_slow_health_after_3s", async () => {
    server.use(
      http.get(`${API_URL}/health`, async () => {
        await new Promise((resolve) => setTimeout(resolve, 10_000));
        return HttpResponse.json({});
      }),
    );
    render(<ApiStatusBanner />);
    await flush(3100);
    expect(await screen.findByRole("alert")).toBeInTheDocument();
  });
});
