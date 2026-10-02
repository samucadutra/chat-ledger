"use client";

import { useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useRef, useState } from "react";
import { ApiError } from "@/lib/api/client";
import { matterKeys } from "./api";
import type { UploadState } from "./UploadRow";
import {
  UploadAbortedError,
  UploadInterruptedError,
  uploadCollection,
  type UploadHandle,
} from "./uploadCollection";

/** Drives one upload at a time for a matter and mirrors it as an `UploadState`. */
export function useCollectionUpload(matterId: string) {
  const queryClient = useQueryClient();
  const [state, setState] = useState<UploadState>({ kind: "idle" });
  const handle = useRef<UploadHandle | null>(null);
  const lastFile = useRef<File | null>(null);
  const lastPercent = useRef(0);

  useEffect(() => () => handle.current?.abort(), []);

  // A dropped connection is reported by the browser immediately; do not wait for the socket to time out.
  useEffect(() => {
    function onOffline() {
      const file = lastFile.current;
      if (!handle.current || !file) return;
      setState({ kind: "interrupted", filename: file.name, percent: lastPercent.current });
      handle.current.abort();
    }
    window.addEventListener("offline", onOffline);
    return () => window.removeEventListener("offline", onOffline);
  }, []);

  const start = useCallback(
    async (file: File) => {
      lastFile.current = file;
      lastPercent.current = 0;
      setState({
        kind: "uploading",
        filename: file.name,
        progress: { loaded: 0, total: file.size, percent: 0, bytesPerSecond: 0 },
      });
      const upload = uploadCollection(matterId, file, {
        onProgress: (progress) => {
          lastPercent.current = progress.percent;
          setState({ kind: "uploading", filename: file.name, progress });
        },
        onUploaded: () => setState({ kind: "verifying", filename: file.name }),
      });
      handle.current = upload;
      try {
        await upload.promise;
        await queryClient.invalidateQueries({ queryKey: matterKeys.collections(matterId) });
        await queryClient.invalidateQueries({ queryKey: matterKeys.all });
        setState({ kind: "idle" });
      } catch (error) {
        if (error instanceof UploadAbortedError)
          setState((prev) => (prev.kind === "interrupted" ? prev : { kind: "idle" }));
        else if (error instanceof UploadInterruptedError)
          setState({ kind: "interrupted", filename: file.name, percent: error.percent });
        else
          setState({
            kind: "error",
            filename: file.name,
            message: error instanceof ApiError ? error.message : "Upload failed. Try again.",
          });
      } finally {
        handle.current = null;
      }
    },
    [matterId, queryClient],
  );

  const retry = useCallback(() => {
    if (lastFile.current) void start(lastFile.current);
  }, [start]);
  const dismiss = useCallback(() => setState({ kind: "idle" }), []);
  const cancel = useCallback(() => handle.current?.abort(), []);

  return { state, start, retry, dismiss, cancel, busy: state.kind === "uploading" || state.kind === "verifying" };
}
