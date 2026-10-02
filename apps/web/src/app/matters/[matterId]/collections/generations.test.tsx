import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { API_URL } from "../../../../../tests/mocks/handlers";
import { server } from "../../../../../tests/mocks/server";
import { ACME_ID, makeCollection, makeGeneration, renderWithProviders } from "../../../../../tests/utils";
import CollectionsPage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ matterId: ACME_ID }) }));

const base = `${API_URL}/api/v1/matters/${ACME_ID}`;

describe("Collections tab generations", () => {
  it("opens_the_generate_dialog_from_the_actions_slot", async () => {
    server.use(http.get(`${base}/collections`, () => HttpResponse.json({ items: [] })));
    renderWithProviders(<CollectionsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Generate synthetic export" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
  });

  it("renders_pending_card_above_collections_and_hides_done_ones", async () => {
    server.use(
      http.get(`${base}/collections`, () => HttpResponse.json({ items: [makeCollection()] })),
      http.get(`${base}/generations`, () =>
        HttpResponse.json({
          items: [makeGeneration(), makeGeneration({ id: "done-1", state: "done", seed: 7 })],
        }),
      ),
    );
    renderWithProviders(<CollectionsPage />);
    expect(await screen.findByText("Generating… 2500 / 10000 messages")).toBeInTheDocument();
    expect(screen.getAllByTestId("generation-card")).toHaveLength(1);
    expect(await screen.findAllByTestId("collection-card")).toHaveLength(1);
  });

  it("retries_a_failed_generation", async () => {
    const retried = vi.fn();
    server.use(
      http.get(`${base}/collections`, () => HttpResponse.json({ items: [] })),
      http.get(`${base}/generations`, () =>
        HttpResponse.json({
          items: [makeGeneration({ state: "failed", error: { code: "GENERATION_FAILED", message: "boom" } })],
        }),
      ),
      http.post(`${base}/generations/:id/retry`, () => {
        retried();
        return HttpResponse.json(makeGeneration({ state: "queued" }), { status: 202 });
      }),
    );
    renderWithProviders(<CollectionsPage />);
    await userEvent.click(await screen.findByRole("button", { name: "Retry" }));
    expect(retried).toHaveBeenCalled();
  });
});
