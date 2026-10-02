import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { makeCollection } from "../../../tests/utils";
import { CollectionCard } from "./CollectionCard";

describe("CollectionCard", () => {
  it("renders_hash_with_copy_button", async () => {
    const collection = makeCollection();
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { value: { writeText }, configurable: true });
    render(<CollectionCard collection={collection} />);
    expect(screen.getByTestId("collection-sha256")).toHaveTextContent(collection.sha256);
    expect(collection.sha256).toHaveLength(64);
    await userEvent.click(screen.getByRole("button", { name: "Copy SHA-256" }));
    expect(writeText).toHaveBeenCalledWith(collection.sha256);
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });

  it("renders_conversation_count_and_date_range", () => {
    render(<CollectionCard collection={makeCollection()} />);
    expect(screen.getByText("50 conversations")).toBeInTheDocument();
    expect(screen.getByText("2024-01-03 → 2024-04-01")).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "export-50conv-90d.zip" })).toBeInTheDocument();
    expect(screen.getByText("Uploaded")).toBeInTheDocument();
    expect(screen.getByText("2026-10-01 19:05 UTC")).toBeInTheDocument();
  });

  it("renders_generator_badge_and_missing_dates", () => {
    render(
      <CollectionCard
        collection={makeCollection({ source: "generator", export_date_from: null, export_date_to: null })}
      />,
    );
    expect(screen.getByText("Generated")).toBeInTheDocument();
    expect(screen.getByText("No dated messages")).toBeInTheDocument();
  });

  it("copy_failure_does_not_crash", async () => {
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockRejectedValue(new Error("denied")) },
      configurable: true,
    });
    render(<CollectionCard collection={makeCollection()} />);
    await userEvent.click(screen.getByRole("button", { name: "Copy SHA-256" }));
    expect(screen.getByRole("button", { name: "Copy SHA-256" })).toHaveTextContent("Copy");
  });
});
