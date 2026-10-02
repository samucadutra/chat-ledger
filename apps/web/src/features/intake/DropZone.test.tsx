import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { DropZone, MAX_UPLOAD_BYTES, validateFile } from "./DropZone";

function file(name: string, size = 10): File {
  const f = new File(["x"], name, { type: "application/zip" });
  Object.defineProperty(f, "size", { value: size });
  return f;
}

describe("DropZone", () => {
  it("rejects_file_over_2gb_before_upload", async () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    await userEvent.upload(screen.getByLabelText("Slack export ZIP file"), file("big.zip", MAX_UPLOAD_BYTES + 1));
    expect(await screen.findByRole("alert")).toHaveTextContent(/^File exceeds the 2 GB limit/);
    expect(onFile).not.toHaveBeenCalled();
  });

  it("accepts_a_file_of_exactly_2gb", () => {
    expect(validateFile(file("ok.zip", MAX_UPLOAD_BYTES))).toBeNull();
  });

  it("rejects_non_zip_extension", async () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    const input = screen.getByLabelText("Slack export ZIP file");
    fireEvent.change(input, { target: { files: [file("notes.txt")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("File must be a .zip archive.");
    expect(onFile).not.toHaveBeenCalled();
  });

  it("accepts_a_zip_via_the_picker_case_insensitively", async () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    fireEvent.change(screen.getByLabelText("Slack export ZIP file"), { target: { files: [file("A.ZIP")] } });
    expect(onFile).toHaveBeenCalledOnce();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("accepts_a_dropped_file", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    const zone = screen.getByTestId("drop-zone");
    fireEvent.dragOver(zone);
    fireEvent.drop(zone, { dataTransfer: { files: [file("export.zip")] } });
    expect(onFile).toHaveBeenCalledOnce();
  });

  it("rejects_multiple_dropped_files", async () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    fireEvent.drop(screen.getByTestId("drop-zone"), { dataTransfer: { files: [file("a.zip"), file("b.zip")] } });
    expect(await screen.findByRole("alert")).toHaveTextContent("Upload one ZIP at a time.");
    expect(onFile).not.toHaveBeenCalled();
  });

  it("disabled_while_uploading", () => {
    const onFile = vi.fn();
    render(<DropZone disabled onFile={onFile} />);
    expect(screen.getByLabelText("Slack export ZIP file")).toBeDisabled();
    expect(screen.getByRole("button", { name: "Choose ZIP file" })).toBeDisabled();
    fireEvent.drop(screen.getByTestId("drop-zone"), { dataTransfer: { files: [file("a.zip")] } });
    expect(onFile).not.toHaveBeenCalled();
  });

  it("choose_button_opens_the_file_picker", async () => {
    render(<DropZone onFile={() => {}} />);
    const input = screen.getByLabelText("Slack export ZIP file");
    const click = vi.spyOn(input, "click");
    await userEvent.click(screen.getByRole("button", { name: "Choose ZIP file" }));
    expect(click).toHaveBeenCalled();
  });
});
