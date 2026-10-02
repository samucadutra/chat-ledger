import { API_URL } from "@/lib/config";
import { toApiError } from "@/lib/api/client";
import type { Collection } from "./api";

export interface UploadProgress {
  loaded: number;
  total: number;
  percent: number;
  bytesPerSecond: number;
}

/** The network dropped (or the server vanished) before the upload completed. */
export class UploadInterruptedError extends Error {
  constructor(readonly percent: number) {
    super(`Upload interrupted at ${percent}%.`);
    this.name = "UploadInterruptedError";
  }
}

/** The caller aborted the upload. */
export class UploadAbortedError extends Error {
  constructor() {
    super("Upload aborted.");
    this.name = "UploadAbortedError";
  }
}

export interface UploadOptions {
  onProgress?: (progress: UploadProgress) => void;
  /** Fires once every byte has been sent (the server is now validating). */
  onUploaded?: () => void;
  baseUrl?: string;
  /** Test seams. */
  createXhr?: () => XMLHttpRequest;
  now?: () => number;
}

export interface UploadHandle {
  promise: Promise<Collection>;
  abort: () => void;
}

/** Rolling window used to smooth the transfer speed. */
export const SPEED_WINDOW_MS = 3000;

export function uploadCollection(matterId: string, file: File, options: UploadOptions = {}): UploadHandle {
  const { onProgress, onUploaded, baseUrl = API_URL, createXhr = () => new XMLHttpRequest(), now = () => Date.now() } =
    options;
  const xhr = createXhr();
  const samples: Array<{ t: number; loaded: number }> = [];
  let lastPercent = 0;

  const promise = new Promise<Collection>((resolve, reject) => {
    xhr.open("POST", `${baseUrl}/api/v1/matters/${encodeURIComponent(matterId)}/collections`);
    xhr.setRequestHeader("Content-Type", "application/zip");
    xhr.setRequestHeader("X-Filename", encodeURIComponent(file.name));

    xhr.upload.onprogress = (event: ProgressEvent) => {
      if (!event.lengthComputable) return;
      const t = now();
      samples.push({ t, loaded: event.loaded });
      while (samples.length > 2 && t - (samples[0]?.t ?? t) > SPEED_WINDOW_MS) samples.shift();
      const first = samples[0];
      const elapsed = first ? t - first.t : 0;
      const bytesPerSecond = first && elapsed > 0 ? ((event.loaded - first.loaded) / elapsed) * 1000 : 0;
      lastPercent = event.total > 0 ? Math.min(100, Math.floor((event.loaded / event.total) * 100)) : 0;
      onProgress?.({ loaded: event.loaded, total: event.total, percent: lastPercent, bytesPerSecond });
    };
    xhr.upload.onload = () => onUploaded?.();

    xhr.onload = () => {
      let body: unknown;
      try {
        body = JSON.parse(xhr.responseText);
      } catch {
        body = undefined;
      }
      if (xhr.status >= 200 && xhr.status < 300) resolve(body as Collection);
      else reject(toApiError(xhr.status, body));
    };
    xhr.onerror = () => reject(new UploadInterruptedError(lastPercent));
    xhr.ontimeout = () => reject(new UploadInterruptedError(lastPercent));
    xhr.onabort = () => reject(new UploadAbortedError());

    xhr.send(file);
  });

  return { promise, abort: () => xhr.abort() };
}
