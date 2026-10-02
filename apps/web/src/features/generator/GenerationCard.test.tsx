import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeGeneration } from "../../../tests/utils";
import { GenerationCard } from "./GenerationCard";

describe("GenerationCard", () => {
  it("shows_progress_while_running", () => {
    render(<GenerationCard generation={makeGeneration()} onRetry={vi.fn()} />);
    expect(screen.getByText("Generating… 2500 / 10000 messages")).toBeInTheDocument();
    expect(screen.getByRole("progressbar")).toHaveAttribute("aria-valuenow", "2500");
  });

  it("shows_error_and_retry_when_failed", async () => {
    const onRetry = vi.fn();
    const generation = makeGeneration({
      state: "failed",
      error: { code: "GENERATION_FAILED", message: "boom" },
    });
    render(<GenerationCard generation={generation} onRetry={onRetry} />);
    expect(screen.getByRole("alert")).toHaveTextContent("Generation failed: boom");
    await userEvent.click(screen.getByRole("button", { name: "Retry" }));
    expect(onRetry).toHaveBeenCalledWith(generation);
  });

  it("duplicate_has_message_and_no_retry", () => {
    const message = "Identical synthetic export already in this matter (same seed and parameters).";
    render(
      <GenerationCard
        generation={makeGeneration({ state: "failed", error: { code: "COLLECTION_DUPLICATE", message } })}
        onRetry={vi.fn()}
      />,
    );
    expect(screen.getByRole("alert")).toHaveTextContent(message);
    expect(screen.queryByRole("button", { name: "Retry" })).not.toBeInTheDocument();
  });
});
