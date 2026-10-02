import { describe, expect, it, vi } from "vitest";
import { ApiError } from "@/lib/api/client";
import {
  UploadAbortedError,
  UploadInterruptedError,
  uploadCollection,
  type UploadProgress,
} from "./uploadCollection";

class FakeXhr {
  status = 0;
  responseText = "";
  headers: Record<string, string> = {};
  method = "";
  url = "";
  sent: unknown = null;
  upload: Record<string, ((e: unknown) => void) | null> = { onprogress: null, onload: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  open(method: string, url: string) {
    this.method = method;
    this.url = url;
  }
  setRequestHeader(name: string, value: string) {
    this.headers[name] = value;
  }
  send(body: unknown) {
    this.sent = body;
  }
  abort() {
    this.onabort?.();
  }
  progress(loaded: number, total: number) {
    this.upload.onprogress?.({ lengthComputable: true, loaded, total });
  }
  respond(status: number, body: unknown) {
    this.status = status;
    this.responseText = typeof body === "string" ? body : JSON.stringify(body);
    this.onload?.();
  }
}

function start(options: { now?: () => number; onProgress?: (p: UploadProgress) => void; onUploaded?: () => void } = {}) {
  const xhr = new FakeXhr();
  const file = new File(["zip"], "my export.zip");
  const handle = uploadCollection("m-1", file, {
    baseUrl: "http://api",
    createXhr: () => xhr as unknown as XMLHttpRequest,
    ...options,
  });
  return { xhr, file, handle };
}

describe("uploadCollection", () => {
  it("posts_the_raw_file_with_headers", () => {
    const { xhr, file } = start();
    expect(xhr.method).toBe("POST");
    expect(xhr.url).toBe("http://api/api/v1/matters/m-1/collections");
    expect(xhr.headers).toEqual({ "Content-Type": "application/zip", "X-Filename": "my%20export.zip" });
    expect(xhr.sent).toBe(file);
  });

  it("reports_progress_and_speed", () => {
    let t = 0;
    const seen: UploadProgress[] = [];
    const { xhr } = start({ now: () => t, onProgress: (p) => seen.push(p) });
    t = 0;
    xhr.progress(0, 1000);
    t = 1000;
    xhr.progress(500, 1000);
    t = 2000;
    xhr.progress(1000, 1000);
    expect(seen[1]).toEqual({ loaded: 500, total: 1000, percent: 50, bytesPerSecond: 500 });
    expect(seen[2]?.percent).toBe(100);
    expect(seen[2]?.bytesPerSecond).toBe(500);
  });

  it("speed_uses_a_three_second_window", () => {
    let t = 0;
    const seen: UploadProgress[] = [];
    const { xhr } = start({ now: () => t, onProgress: (p) => seen.push(p) });
    xhr.progress(0, 10_000);
    t = 1000;
    xhr.progress(1000, 10_000);
    t = 5000;
    xhr.progress(1500, 10_000);
    t = 6000;
    xhr.progress(2500, 10_000);
    // Window now only holds samples from t >= 3000: (2500 - 1500) / 1s... oldest kept is t=5000.
    expect(seen.at(-1)?.bytesPerSecond).toBe(1000);
  });

  it("ignores_non_computable_progress", () => {
    const onProgress = vi.fn();
    const { xhr } = start({ onProgress });
    xhr.upload.onprogress?.({ lengthComputable: false, loaded: 1, total: 0 });
    expect(onProgress).not.toHaveBeenCalled();
  });

  it("signals_when_all_bytes_are_sent", () => {
    const onUploaded = vi.fn();
    const { xhr } = start({ onUploaded });
    xhr.upload.onload?.({});
    expect(onUploaded).toHaveBeenCalledOnce();
  });

  it("resolves_with_the_collection_on_201", async () => {
    const { xhr, handle } = start();
    xhr.respond(201, { id: "c-1", sha256: "ab" });
    await expect(handle.promise).resolves.toEqual({ id: "c-1", sha256: "ab" });
  });

  it("maps_error_envelope", async () => {
    const { xhr, handle } = start();
    xhr.respond(409, {
      error: { code: "COLLECTION_DUPLICATE", message: "dup", details: { existing_collection_id: "x" } },
    });
    const err = await handle.promise.catch((e: unknown) => e);
    expect(err).toBeInstanceOf(ApiError);
    expect(err).toMatchObject({ status: 409, code: "COLLECTION_DUPLICATE", message: "dup" });
  });

  it("maps_non_json_error_bodies", async () => {
    const { xhr, handle } = start();
    xhr.respond(502, "<html>bad gateway</html>");
    await expect(handle.promise).rejects.toMatchObject({ status: 502, code: "HTTP_502" });
  });

  it("network_error_raises_interrupted_with_percent", async () => {
    const { xhr, handle } = start();
    xhr.progress(370, 1000);
    xhr.onerror?.();
    const err = await handle.promise.catch((e: unknown) => e);
    expect(err).toBeInstanceOf(UploadInterruptedError);
    expect((err as UploadInterruptedError).percent).toBe(37);
  });

  it("timeout_is_also_an_interruption", async () => {
    const { xhr, handle } = start();
    xhr.ontimeout?.();
    await expect(handle.promise).rejects.toBeInstanceOf(UploadInterruptedError);
  });

  it("abort_rejects_with_UploadAbortedError", async () => {
    const { handle } = start();
    handle.abort();
    await expect(handle.promise).rejects.toBeInstanceOf(UploadAbortedError);
  });
});
