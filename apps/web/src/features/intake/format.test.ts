import { describe, expect, it } from "vitest";
import { abbreviateSha, formatBytes, formatDate, formatDateTime, formatMegabytes, formatSpeed } from "./format";

describe("intake formatters", () => {
  it("formats_bytes_with_one_decimal", () => {
    expect(formatBytes(12)).toBe("12 B");
    expect(formatBytes(1536)).toBe("1.5 KB");
    expect(formatBytes(5 * 1024 * 1024)).toBe("5.0 MB");
    expect(formatBytes(1_610_612_736)).toBe("1.5 GB");
    expect(formatBytes(2_147_483_649)).toBe("2.0 GB");
  });

  it("formats_megabytes_and_speed", () => {
    expect(formatMegabytes(1_610_612_736)).toBe("1536.0 MB");
    expect(formatSpeed(52_428_800)).toBe("50.0 MB/s");
  });

  it("formats_dates_in_utc", () => {
    expect(formatDate("2026-10-01T23:59:59Z")).toBe("2026-10-01");
    expect(formatDate("2024-01-03")).toBe("2024-01-03");
    expect(formatDateTime("2026-10-01T19:05:44.120Z")).toBe("2026-10-01 19:05");
  });

  it("abbreviates_digests", () => {
    const sha = "a".repeat(32) + "b".repeat(32);
    expect(abbreviateSha(sha)).toBe("aaaaaaaa…bbbbbbbb");
    expect(abbreviateSha("abc")).toBe("abc");
  });
});
