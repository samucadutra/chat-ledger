import { screen } from "@testing-library/react";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { HeaderBar } from "@/components/shell/HeaderBar";
import { API_URL } from "../../../../tests/mocks/handlers";
import { server } from "../../../../tests/mocks/server";
import { ACME_ID, makeMatter, matterUrl, renderWithProviders } from "../../../../tests/utils";
import MatterLayout from "./layout";

const nav = vi.hoisted(() => ({ id: "" }));
vi.mock("next/navigation", () => ({ useParams: () => ({ matterId: nav.id }) }));

function renderLayout() {
  return renderWithProviders(
    <>
      <HeaderBar />
      <MatterLayout>
        <p>tab content</p>
      </MatterLayout>
    </>,
  );
}

describe("Matter layout", () => {
  it("renders_heading_tabs_children_and_header_context", async () => {
    nav.id = ACME_ID;
    server.use(
      http.get(matterUrl(), () => HttpResponse.json(makeMatter({ description: "Beta dispute" }))),
    );
    renderLayout();
    expect(await screen.findByRole("heading", { level: 1, name: "Acme v. Beta" })).toBeInTheDocument();
    expect(screen.getByText("Beta dispute")).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: "Collections", selected: true })).toBeInTheDocument();
    expect(screen.getByText("tab content")).toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("Acme v. Beta");
  });

  it("shows_not_found_state_with_link_back", async () => {
    nav.id = "00000000-0000-4000-8000-000000000000";
    server.use(
      http.get(matterUrl(nav.id), () =>
        HttpResponse.json(
          { error: { code: "MATTER_NOT_FOUND", message: "Matter not found.", details: {} } },
          { status: 404 },
        ),
      ),
    );
    renderLayout();
    expect(await screen.findByText("Matter not found")).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to matters" })).toHaveAttribute("href", "/matters");
    expect(screen.queryByText("tab content")).not.toBeInTheDocument();
    expect(screen.getByRole("banner")).toHaveTextContent("None selected");
  });

  it("shows_an_error_banner_for_other_failures", async () => {
    nav.id = ACME_ID;
    server.use(http.get(`${API_URL}/api/v1/matters/${ACME_ID}`, () => HttpResponse.error()));
    renderLayout();
    // The layout retries once (1 s back-off) before surfacing a non-404 failure.
    expect(await screen.findByRole("alert", undefined, { timeout: 4000 })).toHaveTextContent(/API unavailable/);
  });

  it("shows_a_loading_skeleton_first", () => {
    nav.id = ACME_ID;
    server.use(http.get(matterUrl(), () => new Promise(() => {})));
    renderLayout();
    expect(screen.getByRole("status", { name: "Loading matter" })).toBeInTheDocument();
  });
});
