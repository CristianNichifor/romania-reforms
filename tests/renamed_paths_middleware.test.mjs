// node --test tests/renamed_paths_middleware.test.mjs — old simulator paths redirect (RR-1).
import test from "node:test";
import assert from "node:assert/strict";
import { webcrypto } from "node:crypto";
import { onRequest } from "../functions/_middleware.js";
import { RENAMED_PATHS } from "../functions/renamed-paths.js";

globalThis.crypto ??= webcrypto;

const served = new Response("site");
const call = (url) => {
  let nextCalled = false;
  const next = async () => { nextCalled = true; return served; };
  return onRequest({ request: new Request(url), next, env: {} }).then((response) => ({ response, nextCalled }));
};
const HOST = "https://projects.cristian-nichifor.com";

test("both renames are declared", () => {
  assert.deepEqual(RENAMED_PATHS, { administrativ: "administrative-reform", salarizare: "public-pay" });
});

test("an old path answers 301 to the new one, keeping the rest of the path and the query", async () => {
  const cases = [
    ["/romania-reforms/administrativ/", "/romania-reforms/administrative-reform/"],
    ["/romania-reforms/administrativ", "/romania-reforms/administrative-reform/"],
    ["/romania-reforms/administrativ/index.html?s=1", "/romania-reforms/administrative-reform/index.html?s=1"],
    ["/romania-reforms/salarizare/", "/romania-reforms/public-pay/"],
    ["/romania-reforms/salarizare/data/x.json?a=b&c", "/romania-reforms/public-pay/data/x.json?a=b&c"],
  ];
  for (const [from, to] of cases) {
    const { response, nextCalled } = await call(HOST + from);
    assert.equal(response.status, 301, from);
    assert.equal(response.headers.get("location"), to, from);
    assert.equal(nextCalled, false);
  }
});

test("new and unrelated paths are served", async () => {
  for (const path of ["/romania-reforms/", "/romania-reforms/public-pay/", "/romania-reforms/administrativ-x/", "/administrativ/"]) {
    const { response, nextCalled } = await call(HOST + path);
    assert.equal(response, served, path);
    assert.equal(nextCalled, true);
  }
});

test("a preview host is still gated before any redirect", async () => {
  const { response } = await call("https://dev.romania-reforms-x1y.pages.dev/romania-reforms/salarizare/");
  assert.equal(response.status, 403);
});
