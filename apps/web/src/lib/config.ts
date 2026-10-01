/** Base URL of the ChatLedger API (inlined at build time by Next.js). */
export const API_URL: string = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").replace(
  /\/+$/,
  "",
);
