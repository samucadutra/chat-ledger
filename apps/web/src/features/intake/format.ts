const KIB = 1024;
const MIB = KIB * 1024;
const GIB = MIB * 1024;

/** Human size with one decimal: `B`, `KB`, `MB` or `GB` (binary units). */
export function formatBytes(bytes: number): string {
  if (bytes < KIB) return `${bytes} B`;
  if (bytes < MIB) return `${(bytes / KIB).toFixed(1)} KB`;
  if (bytes < GIB) return `${(bytes / MIB).toFixed(1)} MB`;
  return `${(bytes / GIB).toFixed(1)} GB`;
}

/** Megabytes with one decimal, regardless of magnitude (for transferred / total). */
export function formatMegabytes(bytes: number): string {
  return `${(bytes / MIB).toFixed(1)} MB`;
}

export function formatSpeed(bytesPerSecond: number): string {
  return `${(bytesPerSecond / MIB).toFixed(1)} MB/s`;
}

/** UTC calendar date `YYYY-MM-DD` from an ISO timestamp or date string. */
export function formatDate(value: string): string {
  return new Date(value).toISOString().slice(0, 10);
}

/** UTC `YYYY-MM-DD HH:MM` from an ISO timestamp. */
export function formatDateTime(value: string): string {
  return new Date(value).toISOString().slice(0, 16).replace("T", " ");
}

/** `abcdef12…89abcdef` abbreviation of a hex digest. */
export function abbreviateSha(sha: string): string {
  return sha.length <= 20 ? sha : `${sha.slice(0, 8)}…${sha.slice(-8)}`;
}
