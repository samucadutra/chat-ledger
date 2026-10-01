import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Button } from "@/components/ui/Button";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import { EmptyState } from "./EmptyState";
import { ErrorBanner } from "./ErrorBanner";
import { Skeleton } from "./Skeleton";

describe("shared state components", () => {
  it("renders EmptyState title, description and action", () => {
    render(<EmptyState title="Nothing" description="Add one" action={<Button>Go</Button>} eyebrow="0" />);
    expect(screen.getByText("Nothing")).toBeInTheDocument();
    expect(screen.getByText("Add one")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Go" })).toBeInTheDocument();
  });

  it("renders Skeleton rows as a status region", () => {
    render(<Skeleton rows={4} label="Loading runs" />);
    expect(screen.getByRole("status", { name: "Loading runs" })).toBeInTheDocument();
  });

  it("dismisses a dismissible ErrorBanner", async () => {
    const onDismiss = vi.fn();
    render(
      <ErrorBanner dismissible onDismiss={onDismiss}>
        Broken
      </ErrorBanner>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(onDismiss).toHaveBeenCalledOnce();
  });

  it("shows a toast via useToast", async () => {
    function Trigger() {
      const { toast } = useToast();
      return <Button onClick={() => toast({ title: "Saved", description: "Matter created" })}>Fire</Button>;
    }
    render(
      <ToastProvider>
        <Trigger />
      </ToastProvider>,
    );
    await userEvent.click(screen.getByRole("button", { name: "Fire" }));
    expect(await screen.findByText("Saved")).toBeInTheDocument();
    expect(screen.getByText("Matter created")).toBeInTheDocument();
  });

  it("throws when useToast is used outside the provider", () => {
    function Bad() {
      useToast();
      return null;
    }
    vi.spyOn(console, "error").mockImplementation(() => {});
    expect(() => render(<Bad />)).toThrow(/ToastProvider/);
  });
});
