import { act, fireEvent, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { http, HttpResponse } from "msw";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import { UploadInterruptedError, type UploadOptions } from "@/features/intake/uploadCollection";
import { API_URL } from "../../../../../tests/mocks/handlers";
import { server } from "../../../../../tests/mocks/server";
import { ACME_ID, makeCollection, renderWithProviders } from "../../../../../tests/utils";
import CollectionsPage from "./page";

vi.mock("next/navigation", () => ({ useParams: () => ({ matterId: ACME_ID }) }));

const upload = vi.hoisted(() => ({
  options: undefined as UploadOptions | undefined,
  resolve: (() => {}) as (value: unknown) => void,
  reject: (() => {}) as (reason: unknown) => void,
  abort: vi.fn(),
  calls: 0,
}));

vi.mock("@/features/intake/uploadCollection", async (importOriginal) => {
  const actual = await importOriginal<typeof import("@/features/intake/uploadCollection")>();
  return {
    ...actual,
    uploadCollection: (_id: string, _file: File, options: UploadOptions) => {
      upload.calls += 1;
      upload.options = options;
      const promise = new Promise((resolve, reject) => {
        upload.resolve = resolve;
        upload.reject = reject;
      });
      return { promise, abort: upload.abort };
    },
  };
});

const listUrl = `${API_URL}/api/v1/matters/${ACME_ID}/collections`;

function zip(name = "export.zip") {
  return new File(["zip"], name, { type: "application/zip" });
}

function choose(file: File) {
  fireEvent.change(screen.getByLabelText("Slack export ZIP file"), { target: { files: [file] } });
}

describe("Collections tab", () => {
  beforeEach(() => {
    upload.calls = 0;
    upload.abort.mockClear();
  });

  it("shows_empty_state_and_actions_slot", async () => {
    server.use(http.get(listUrl, () => HttpResponse.json({ items: [] })));
    const { container } = renderWithProviders(<CollectionsPage />);
    expect(await screen.findByText(/No collections yet/)).toBeInTheDocument();
    expect(container.querySelector("[data-slot=collection-actions]")).not.toBeNull();
    expect(screen.getByText(/included in each processing run/)).toBeInTheDocument();
  });

  it("lists_collection_cards_oldest_first_as_returned", async () => {
    server.use(
      http.get(listUrl, () =>
        HttpResponse.json({
          items: [makeCollection({ id: "1", original_filename: "first.zip" }), makeCollection({ id: "2", original_filename: "second.zip" })],
        }),
      ),
    );
    renderWithProviders(<CollectionsPage />);
    const cards = await screen.findAllByTestId("collection-card");
    expect(cards.map((c) => c.getAttribute("aria-label"))).toEqual([
      "Collection first.zip",
      "Collection second.zip",
    ]);
  });

  it("walks_through_uploading_verifying_and_shows_the_new_card", async () => {
    let items: unknown[] = [];
    server.use(http.get(listUrl, () => HttpResponse.json({ items })));
    renderWithProviders(<CollectionsPage />);
    await screen.findByText(/No collections yet/);
    choose(zip("big.zip"));
    expect(await screen.findByText("big.zip")).toBeInTheDocument();
    act(() => upload.options?.onProgress?.({ loaded: 512 * 1024 * 1024, total: 1024 * 1024 * 1024, percent: 50, bytesPerSecond: 10 * 1024 * 1024 }));
    expect(screen.getByText("50%")).toBeInTheDocument();
    expect(screen.getByText("512.0 MB / 1024.0 MB")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Choose ZIP file" })).toBeDisabled();
    act(() => upload.options?.onUploaded?.());
    expect(screen.getByText("Verifying export structure…")).toBeInTheDocument();
    items = [makeCollection({ original_filename: "big.zip" })];
    await act(async () => upload.resolve(makeCollection()));
    expect(await screen.findByTestId("collection-card")).toBeInTheDocument();
    await waitFor(() => expect(screen.queryByTestId("upload-row")).not.toBeInTheDocument());
  });

  it("shows_the_server_error_message_and_dismisses", async () => {
    server.use(http.get(listUrl, () => HttpResponse.json({ items: [] })));
    renderWithProviders(<CollectionsPage />);
    await screen.findByText(/No collections yet/);
    choose(zip("missing-users.zip"));
    await act(async () =>
      upload.reject(
        new ApiError(422, "NOT_A_SLACK_EXPORT", "Not a Slack workspace export: users.json and channels.json not found."),
      ),
    );
    expect(
      await screen.findByText("Not a Slack workspace export: users.json and channels.json not found."),
    ).toBeInTheDocument();
    expect(screen.queryByTestId("collection-card")).not.toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByTestId("upload-row")).not.toBeInTheDocument();
  });

  it("interrupted_upload_offers_retry_which_restarts_the_upload", async () => {
    server.use(http.get(listUrl, () => HttpResponse.json({ items: [] })));
    renderWithProviders(<CollectionsPage />);
    await screen.findByText(/No collections yet/);
    choose(zip("big.zip"));
    await act(async () => upload.reject(new UploadInterruptedError(37)));
    expect(await screen.findByText("Upload interrupted at 37%. Retry?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(upload.calls).toBe(2);
    expect(await screen.findByRole("progressbar")).toBeInTheDocument();
  });

  it("falls_back_to_a_generic_message_for_unknown_errors", async () => {
    server.use(http.get(listUrl, () => HttpResponse.json({ items: [] })));
    renderWithProviders(<CollectionsPage />);
    await screen.findByText(/No collections yet/);
    choose(zip());
    await act(async () => upload.reject(new Error("boom")));
    expect(await screen.findByText("Upload failed. Try again.")).toBeInTheDocument();
  });

  it("cancel_aborts_the_upload", async () => {
    server.use(http.get(listUrl, () => HttpResponse.json({ items: [] })));
    renderWithProviders(<CollectionsPage />);
    await screen.findByText(/No collections yet/);
    choose(zip());
    await userEvent.click(await screen.findByRole("button", { name: "Cancel" }));
    expect(upload.abort).toHaveBeenCalledOnce();
  });

  it("shows_an_error_banner_when_listing_fails", async () => {
    server.use(http.get(listUrl, () => HttpResponse.error()));
    renderWithProviders(<CollectionsPage />);
    expect(await screen.findByRole("alert")).toHaveTextContent(/API unavailable/);
  });
});
