import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { API_URL } from "../../../tests/mocks/handlers";
import { server } from "../../../tests/mocks/server";
import { makeMatter, renderWithProviders } from "../../../tests/utils";
import MattersPage from "./page";

vi.mock("next/navigation", () => ({ useRouter: () => ({ push: vi.fn() }) }));

function mockMatters(items: unknown[]) {
  server.use(http.get(`${API_URL}/api/v1/matters`, () => HttpResponse.json({ items })));
}

describe("Matters page", () => {
  it("renders_empty_state_when_no_matters", async () => {
    mockMatters([]);
    renderWithProviders(<MattersPage />);
    expect(await screen.findByText("No matters yet. Create one to start.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Matters" })).toBeInTheDocument();
    const button = screen.getByRole("button", { name: "New matter" });
    expect(button).toHaveAttribute("data-variant", "primary");
  });

  it("renders_ledger_rows_newest_first", async () => {
    mockMatters([
      makeMatter({ id: "b", name: "Beta Internal", created_at: "2026-10-02T08:00:00Z" }),
      makeMatter({ id: "a", name: "Acme v. Beta", collection_count: 1, total_size_bytes: 1769 }),
    ]);
    renderWithProviders(<MattersPage />);
    expect(await screen.findByRole("link", { name: "Beta Internal" })).toHaveAttribute(
      "href",
      "/matters/b/collections",
    );
    const rows = screen.getAllByRole("row").slice(1);
    expect(within(rows[0]!).getByText("Beta Internal")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("Acme v. Beta")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("1")).toBeInTheDocument();
    expect(within(rows[1]!).getByText("1.7 KB")).toBeInTheDocument();
    expect(within(rows[0]!).getByText("2026-10-02")).toBeInTheDocument();
    expect(screen.queryByText("No matters yet. Create one to start.")).not.toBeInTheDocument();
    expect(screen.getAllByRole("button", { name: "New matter" })).toHaveLength(1);
  });

  it("opens_the_new_matter_dialog", async () => {
    mockMatters([]);
    renderWithProviders(<MattersPage />);
    await userEvent.click(await screen.findByRole("button", { name: "New matter" }));
    expect(await screen.findByRole("dialog")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toBeInTheDocument();
  });

  it("shows_an_error_banner_when_the_api_fails", async () => {
    server.use(http.get(`${API_URL}/api/v1/matters`, () => HttpResponse.error()));
    renderWithProviders(<MattersPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/API unavailable/);
  });
});
