import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import MattersPage from "./page";

describe("Matters page", () => {
  it("shows_empty_state_copy", () => {
    render(<MattersPage />);
    expect(screen.getByText("No matters yet. Create one to start.")).toBeInTheDocument();
    expect(screen.getByRole("heading", { level: 1, name: "Matters" })).toBeInTheDocument();
  });

  it("shows_new_matter_primary_button", () => {
    render(<MattersPage />);
    const button = screen.getByRole("button", { name: "New matter" });
    expect(button).toHaveAttribute("data-variant", "primary");
  });
});
