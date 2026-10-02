import { describe, expect, it } from "vitest";
import {
  CONVERSATIONS_CAP_ERROR,
  MESSAGES_ERROR,
  SEED_ERROR,
  randomSeed,
  validateGenerate,
} from "./params";

const base = { seed: "42", preset: "custom" as const, messages: "2000", conversations: "20" };

describe("validateGenerate", () => {
  it("accepts_valid_custom_input", () => {
    expect(validateGenerate(base)).toEqual({});
  });
  it("rejects_messages_above_limit", () => {
    expect(validateGenerate({ ...base, messages: "2000000" }).messages).toBe(MESSAGES_ERROR);
    expect(validateGenerate({ ...base, messages: "999" }).messages).toBe(MESSAGES_ERROR);
  });
  it("rejects_too_many_conversations", () => {
    expect(validateGenerate({ ...base, conversations: "1001" }).conversations).toBe(CONVERSATIONS_CAP_ERROR);
    expect(validateGenerate({ ...base, conversations: "0" }).conversations).toBe(
      "Conversations must be between 1 and 5,000",
    );
  });
  it("ignores_sizes_for_presets_and_checks_seed", () => {
    expect(validateGenerate({ ...base, preset: "small", messages: "" })).toEqual({});
    expect(validateGenerate({ ...base, seed: "-1" }).seed).toBe(SEED_ERROR);
    expect(validateGenerate({ ...base, seed: "2147483648" }).seed).toBe(SEED_ERROR);
  });
  it("random_seed_has_six_digits", () => {
    expect(String(randomSeed())).toMatch(/^\d{6}$/);
  });
});
