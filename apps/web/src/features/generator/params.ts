/** Mirrors the server-side generator rules and messages (spec A4-A6, A22). */

export type Preset = "small" | "medium" | "large" | "custom";
export type Profile = "clean" | "default" | "stress";

export const PRESETS: readonly Preset[] = ["small", "medium", "large", "custom"];
export const PROFILES: readonly Profile[] = ["clean", "default", "stress"];

export const PROFILE_DESCRIPTIONS: Record<Profile, string> = {
  clean: "No injected anomalies",
  default: "Realistic mix of edits, deletions and rare defects",
  stress: "High defect rates to exercise every gate",
};

export const SEED_MAX = 2_147_483_647;
export const SEED_ERROR = "Seed must be an integer between 0 and 2,147,483,647";
export const MESSAGES_ERROR = "Messages must be between 1,000 and 1,000,000";
export const CONVERSATIONS_ERROR = "Conversations must be between 1 and 5,000";
export const CONVERSATIONS_CAP_ERROR = "Conversations must not exceed messages / 2";

export interface GenerateInput {
  seed: string;
  preset: Preset;
  messages: string;
  conversations: string;
}

export interface GenerateErrors {
  seed?: string;
  messages?: string;
  conversations?: string;
}

const INTEGER = /^\d+$/;

export function randomSeed(): number {
  return Math.floor(100_000 + Math.random() * 900_000);
}

export function validateGenerate(input: GenerateInput): GenerateErrors {
  const errors: GenerateErrors = {};
  const seed = input.seed.trim();
  if (!INTEGER.test(seed) || Number(seed) > SEED_MAX) errors.seed = SEED_ERROR;
  if (input.preset !== "custom") return errors;
  const messages = input.messages.trim();
  const conversations = input.conversations.trim();
  const messagesOk = INTEGER.test(messages) && Number(messages) >= 1_000 && Number(messages) <= 1_000_000;
  if (!messagesOk) {
    errors.messages = MESSAGES_ERROR;
  }
  if (!INTEGER.test(conversations) || Number(conversations) < 1 || Number(conversations) > 5_000) {
    errors.conversations = CONVERSATIONS_ERROR;
  } else if (messagesOk && Number(conversations) * 2 > Number(messages)) {
    errors.conversations = CONVERSATIONS_CAP_ERROR;
  }
  return errors;
}
