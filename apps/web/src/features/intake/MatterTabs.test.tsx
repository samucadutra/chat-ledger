import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { renderWithProviders } from "../../../tests/utils";
import { MatterTabs } from "./MatterTabs";

describe("MatterTabs", () => {
  it("collections_enabled_others_disabled_with_tooltip", async () => {
    renderWithProviders(<MatterTabs matterId="abc" />);
    const collections = screen.getByRole("tab", { name: "Collections" });
    expect(collections).toHaveAttribute("aria-selected", "true");
    expect(collections).toHaveAttribute("href", "/matters/abc/collections");
    for (const name of ["Runs", "Conversations", "Search", "Exports"]) {
      const tab = screen.getByRole("tab", { name });
      expect(tab).toHaveAttribute("aria-disabled", "true");
      expect(tab).toHaveAttribute("aria-selected", "false");
    }
    await userEvent.hover(screen.getByRole("tab", { name: "Runs" }));
    expect(await screen.findAllByText("Available after a completed processing run")).not.toHaveLength(0);
  });
});
