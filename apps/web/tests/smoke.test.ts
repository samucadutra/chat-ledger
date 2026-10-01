import { describe, expect, it } from "vitest";
import { API_URL } from "./mocks/handlers";

describe("test harness", () => {
  it("serves the default healthy /health handler", async () => {
    const res = await fetch(`${API_URL}/health`);
    expect(res.status).toBe(200);
    expect(await res.json()).toMatchObject({ status: "ok" });
  });
});
