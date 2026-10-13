// node --test tests/preview_gate_middleware.test.mjs — the preview gate (CN Webify ADR-022).
import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { onRequest } from "../functions/_middleware.js";

globalThis.crypto ??= webcrypto;

const SECRET = "g".repeat(64);
const served = new Response("site");
const call = (url, { header, secret } = {}) => {
  const headers = new Headers();
  if (header !== undefined) headers.set("x-cnw-preview-gate", header);
  let nextCalled = false;
  const next = async () => { nextCalled = true; return served; };
  return onRequest({ request: new Request(url, { headers }), next, env: secret ? { PREVIEW_GATE_SECRET: secret } : {} })
    .then((response) => ({ response, nextCalled }));
};

test("a preview host without the secret configured is refused", async () => {
  for (const url of ["https://dev.romania-reforms-x1y.pages.dev/romania-reforms/", "https://8bd308ff.romania-reforms-x1y.pages.dev/"]) {
    const { response, nextCalled } = await call(url, { header: "anything" });
    assert.equal(response.status, 403);
    assert.equal(response.headers.get("x-robots-tag"), "noindex, nofollow");
    assert.equal(nextCalled, false);
  }
});

test("with the secret set, a missing or wrong header is refused", async () => {
  for (const header of [undefined, "wrong", "g".repeat(63)]) {
    const { response, nextCalled } = await call("https://dev.romania-reforms-x1y.pages.dev/", { header, secret: SECRET });
    assert.equal(response.status, 403);
    assert.equal(nextCalled, false);
  }
});

test("the gate's header is served", async () => {
  const { response, nextCalled } = await call("https://dev.romania-reforms-x1y.pages.dev/", { header: SECRET, secret: SECRET });
  assert.equal(response, served);
  assert.equal(nextCalled, true);
});

test("the production pages.dev host is served without a secret", async () => {
  const { response, nextCalled } = await call("https://romania-reforms-x1y.pages.dev/romania-reforms/");
  assert.equal(response, served);
  assert.equal(nextCalled, true);
});
