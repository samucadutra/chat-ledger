import { screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { describe, expect, it, vi } from "vitest";
import { API_URL } from "../../../tests/mocks/handlers";
import { server } from "../../../tests/mocks/server";
import { ACME_ID, makeCollection, makeGeneration, renderWithProviders } from "../../../tests/utils";
import { GenerateDialog } from "./GenerateDialog";

const url = `${API_URL}/api/v1/matters/${ACME_ID}/generations`;

function open(baseOptions = [] as ReturnType<typeof makeCollection>[]) {
  const onOpenChange = vi.fn();
  renderWithProviders(
    <GenerateDialog matterId={ACME_ID} open onOpenChange={onOpenChange} baseOptions={baseOptions} />,
  );
  return onOpenChange;
}

function recordPosts() {
  const bodies: unknown[] = [];
  server.use(
    http.post(url, async ({ request }) => {
      bodies.push(await request.json());
      return HttpResponse.json(makeGeneration({ state: "queued" }), { status: 202 });
    }),
  );
  return bodies;
}

describe("GenerateDialog", () => {
  it("opens_with_defaults", () => {
    open();
    expect((screen.getByLabelText("Seed") as HTMLInputElement).value).toMatch(/^\d{6}$/);
    expect(screen.getByLabelText("Preset")).toHaveValue("small");
    expect(screen.getByLabelText("Anomaly profile")).toHaveValue("default");
    expect(screen.getByRole("option", { name: /clean — No injected anomalies/ })).toBeInTheDocument();
    expect(screen.queryByLabelText(/Messages/)).not.toBeInTheDocument();
    expect(screen.getByLabelText("Generate as re-delivery of")).toBeDisabled();
  });

  it("custom_reveals_size_fields_with_ranges", async () => {
    open();
    await userEvent.selectOptions(screen.getByLabelText("Preset"), "custom");
    expect(screen.getByLabelText("Messages (1,000–1,000,000)")).toBeInTheDocument();
    expect(screen.getByLabelText("Conversations (1–5,000)")).toBeInTheDocument();
  });

  it("blocks_invalid_input_without_a_request", async () => {
    const bodies = recordPosts();
    open();
    await userEvent.selectOptions(screen.getByLabelText("Preset"), "custom");
    await userEvent.type(screen.getByLabelText("Messages (1,000–1,000,000)"), "2000000");
    await userEvent.type(screen.getByLabelText("Conversations (1–5,000)"), "10");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByText("Messages must be between 1,000 and 1,000,000")).toBeInTheDocument();
    await userEvent.clear(screen.getByLabelText("Messages (1,000–1,000,000)"));
    await userEvent.type(screen.getByLabelText("Messages (1,000–1,000,000)"), "2000");
    await userEvent.clear(screen.getByLabelText("Conversations (1–5,000)"));
    await userEvent.type(screen.getByLabelText("Conversations (1–5,000)"), "1001");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByText("Conversations must not exceed messages / 2")).toBeInTheDocument();
    expect(bodies).toEqual([]);
  });

  it("submits_and_closes", async () => {
    const bodies = recordPosts();
    const onOpenChange = open();
    await userEvent.clear(screen.getByLabelText("Seed"));
    await userEvent.type(screen.getByLabelText("Seed"), "4821");
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(onOpenChange).toHaveBeenCalledWith(false));
    expect(bodies).toEqual([
      { seed: 4821, preset: "small", profile: "default", messages: null, conversations: null, overlap_of_collection_id: null },
    ]);
  });

  it("shows_server_validation_errors", async () => {
    server.use(
      http.post(url, () =>
        HttpResponse.json(
          { error: { code: "GENERATION_PARAMS_INVALID", message: "Seed must be an integer between 0 and 2,147,483,647", details: { field: "seed" } } },
          { status: 422 },
        ),
      ),
    );
    open();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    expect(await screen.findByText(/Seed must be an integer/)).toBeInTheDocument();
  });

  it("re_delivery_base_locks_inherited_parameters", async () => {
    const bodies = recordPosts();
    const base = makeCollection({
      id: "c1",
      original_filename: "slack-export-42-small-default.zip",
      source: "generator",
      generation: { id: "g1", seed: 42, preset: "small", profile: "default", has_ground_truth: true },
    });
    open([base]);
    expect(screen.getByRole("option", { name: /seed 42/ })).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Generate as re-delivery of"), "c1");
    expect(screen.getByLabelText("Preset")).toBeDisabled();
    expect(screen.getByLabelText("Preset")).toHaveValue("small");
    expect(screen.getByLabelText("Anomaly profile")).toBeDisabled();
    expect(screen.getByLabelText("Seed")).toBeEnabled();
    await userEvent.click(screen.getByRole("button", { name: "Generate" }));
    await waitFor(() => expect(bodies).toHaveLength(1));
    expect(bodies[0]).toMatchObject({ preset: "small", profile: "default", overlap_of_collection_id: "c1" });
  });
});
