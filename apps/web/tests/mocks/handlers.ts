import { http, HttpResponse } from "msw";

export const API_URL = "http://localhost:8000";

export const healthyBody = {
  status: "ok",
  checks: { database: "ok", migrations: "ok", blob_store: "ok" },
  migration_revision: "0003_generation",
  git_sha: "0123456789abcdef0123456789abcdef01234567",
  active_workers: 2,
  version: "0.1.0",
};

/** Default handlers: a healthy API. Tests override per case with `server.use(...)`. */
export const handlers = [
  http.get(`${API_URL}/health`, () => HttpResponse.json(healthyBody)),
  http.get(`${API_URL}/api/v1/matters/:matterId/generations`, () => HttpResponse.json({ items: [] })),
];
