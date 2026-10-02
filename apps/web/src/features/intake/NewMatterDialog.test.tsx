import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { API_URL } from "../../../tests/mocks/handlers";
import { server } from "../../../tests/mocks/server";
import { makeMatter, renderWithProviders } from "../../../tests/utils";
import { NewMatterDialog } from "./NewMatterDialog";

const push = vi.hoisted(() => vi.fn());
vi.mock("next/navigation", () => ({ useRouter: () => ({ push }) }));

function open() {
  const onOpenChange = vi.fn();
  renderWithProviders(<NewMatterDialog open onOpenChange={onOpenChange} />);
  return onOpenChange;
}

describe("NewMatterDialog", () => {
  beforeEach(() => push.mockClear());

  it("shows_length_error_inline", async () => {
    const onOpenChange = open();
    await userEvent.type(screen.getByLabelText("Name"), "Ab");
    await userEvent.click(screen.getByRole("button", { name: "Create matter" }));
    expect(await screen.findByText("Name must be 3–80 characters")).toBeInTheDocument();
    expect(onOpenChange).not.toHaveBeenCalledWith(false);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
  });

  it("shows_name_taken_error_from_api", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/matters`, () =>
        HttpResponse.json(
          { error: { code: "MATTER_NAME_TAKEN", message: "A matter with this name already exists", details: {} } },
          { status: 409 },
        ),
      ),
    );
    open();
    await userEvent.type(screen.getByLabelText("Name"), "acme v. beta");
    await userEvent.click(screen.getByRole("button", { name: "Create matter" }));
    expect(await screen.findByText("A matter with this name already exists")).toBeInTheDocument();
    expect(screen.getByLabelText("Name")).toHaveAttribute("aria-invalid", "true");
    expect(push).not.toHaveBeenCalled();
  });

  it("navigates_to_collections_on_success", async () => {
    let body: unknown;
    server.use(
      http.post(`${API_URL}/api/v1/matters`, async ({ request }) => {
        body = await request.json();
        return HttpResponse.json(makeMatter(), { status: 201 });
      }),
      http.get(`${API_URL}/api/v1/matters`, () => HttpResponse.json({ items: [makeMatter()] })),
    );
    const onOpenChange = open();
    await userEvent.type(screen.getByLabelText("Name"), "  Acme v. Beta ");
    await userEvent.click(screen.getByRole("button", { name: "Create matter" }));
    await waitFor(() => expect(push).toHaveBeenCalledWith(`/matters/${makeMatter().id}/collections`));
    expect(body).toEqual({ name: "Acme v. Beta", description: null });
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });

  it("validates_description_length_client_side", async () => {
    open();
    await userEvent.type(screen.getByLabelText("Name"), "Acme");
    await userEvent.click(screen.getByLabelText(/Description/));
    await userEvent.paste("d".repeat(501));
    await userEvent.click(screen.getByRole("button", { name: "Create matter" }));
    expect(await screen.findByText("Description must be at most 500 characters")).toBeInTheDocument();
  });

  it("maps_unexpected_api_errors_to_a_form_message", async () => {
    server.use(
      http.post(`${API_URL}/api/v1/matters`, () =>
        HttpResponse.json({ error: { code: "INTERNAL_ERROR", message: "Unexpected server error.", details: {} } }, { status: 500 }),
      ),
    );
    open();
    await userEvent.type(screen.getByLabelText("Name"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Create matter" }));
    expect(await screen.findByText("Unexpected server error.")).toBeInTheDocument();
  });

  it("reports_an_unreachable_api", async () => {
    server.use(http.post(`${API_URL}/api/v1/matters`, () => HttpResponse.error()));
    open();
    await userEvent.type(screen.getByLabelText("Name"), "Acme");
    await userEvent.click(screen.getByRole("button", { name: "Create matter" }));
    expect(await screen.findByText("Could not reach the API. Try again.")).toBeInTheDocument();
  });

  it("cancel_closes_the_dialog", async () => {
    const onOpenChange = open();
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onOpenChange).toHaveBeenCalledWith(false);
  });
});
