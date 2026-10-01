import { render, screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { AppShell } from "./AppShell";

const nav = vi.hoisted(() => ({ pathname: "/matters" }));
vi.mock("next/navigation", () => ({ usePathname: () => nav.pathname }));

describe("AppShell", () => {
  beforeEach(() => {
    nav.pathname = "/matters";
  });

  it("renders_nav_items_matters_and_reason_codes", () => {
    render(<AppShell>content</AppShell>);
    const primary = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primary).getByRole("link", { name: /Matters/ })).toHaveAttribute("href", "/matters");
    expect(within(primary).getByRole("link", { name: /Reason Codes/ })).toHaveAttribute(
      "href",
      "/reason-codes",
    );
    expect(screen.getByRole("main")).toHaveTextContent("content");
  });

  it("marks_active_route", () => {
    nav.pathname = "/reason-codes";
    render(<AppShell>x</AppShell>);
    const primary = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primary).getByRole("link", { name: /Reason Codes/ })).toHaveAttribute(
      "aria-current",
      "page",
    );
    expect(within(primary).getByRole("link", { name: /Matters/ })).not.toHaveAttribute("aria-current");
  });

  it("marks_nested_routes_active", () => {
    nav.pathname = "/matters/123";
    render(<AppShell>x</AppShell>);
    const primary = screen.getByRole("navigation", { name: "Primary" });
    expect(within(primary).getByRole("link", { name: /Matters/ })).toHaveAttribute("aria-current", "page");
  });

  it("header_slot_renders_children", () => {
    render(<AppShell currentMatter={<span>Acme v. Widget</span>}>x</AppShell>);
    expect(screen.getByRole("banner")).toHaveTextContent("Acme v. Widget");
  });

  it("header_slot_shows_placeholder_when_empty", () => {
    render(<AppShell>x</AppShell>);
    expect(screen.getByRole("banner")).toHaveTextContent("None selected");
  });
});
