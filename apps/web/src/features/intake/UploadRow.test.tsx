import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { UploadRow } from "./UploadRow";

const noop = () => {};

describe("UploadRow", () => {
  it("uploading_state_shows_filename_percent_mb_speed", async () => {
    const onCancel = vi.fn();
    render(
      <UploadRow
        state={{
          kind: "uploading",
          filename: "big.zip",
          progress: { loaded: 536_870_912, total: 1_610_612_736, percent: 33, bytesPerSecond: 52_428_800 },
        }}
        onRetry={noop}
        onDismiss={noop}
        onCancel={onCancel}
      />,
    );
    expect(screen.getByText("big.zip")).toBeInTheDocument();
    expect(screen.getByText("33%")).toBeInTheDocument();
    expect(screen.getByText("512.0 MB / 1536.0 MB")).toBeInTheDocument();
    expect(screen.getByText("50.0 MB/s")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "33");
    await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(onCancel).toHaveBeenCalledOnce();
  });

  it("verifying_state_text", () => {
    render(<UploadRow state={{ kind: "verifying", filename: "a.zip" }} onRetry={noop} onDismiss={noop} />);
    expect(screen.getByText("Verifying export structure…")).toBeInTheDocument();
  });

  it("interrupted_state_offers_retry", async () => {
    const onRetry = vi.fn();
    const onDismiss = vi.fn();
    render(
      <UploadRow state={{ kind: "interrupted", filename: "a.zip", percent: 41 }} onRetry={onRetry} onDismiss={onDismiss} />,
    );
    expect(screen.getByText("Upload interrupted at 41%. Retry?")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onRetry).toHaveBeenCalledOnce();
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("error_state_shows_message_with_dismiss_and_retry", async () => {
    const onDismiss = vi.fn();
    render(
      <UploadRow
        state={{ kind: "error", filename: "a.zip", message: "Not a Slack workspace export: users.json and channels.json not found." }}
        onRetry={noop}
        onDismiss={onDismiss}
      />,
    );
    expect(
      screen.getByText("Not a Slack workspace export: users.json and channels.json not found."),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Retry" })).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(onDismiss).toHaveBeenCalledOnce();
  });
});
