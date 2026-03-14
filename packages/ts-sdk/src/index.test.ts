import assert from "node:assert/strict";
import test from "node:test";

import { CaliperClient } from "./index.js";

test("CaliperClient sends bearer auth and parses response", async () => {
  const calls: Array<{ url: string; method: string; auth?: string }> = [];

  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({
      url: String(input),
      method: init?.method ?? "GET",
      auth: (init?.headers as Record<string, string>)?.Authorization,
    });
    return new Response(JSON.stringify({ status: "ok" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;

  const client = new CaliperClient({ baseUrl: "http://127.0.0.1:8000", apiToken: "token-123" });
  const health = await client.healthz();

  assert.equal(health.status, "ok");
  assert.equal(calls[0]?.url, "http://127.0.0.1:8000/healthz");
  assert.equal(calls[0]?.method, "GET");
  assert.equal(calls[0]?.auth, "Bearer token-123");
});
