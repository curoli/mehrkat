const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");
const code = fs.readFileSync("src/mehrkat/static/app.js", "utf8");

function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return {promise, resolve, reject};
}

function progressPage() {
  let submit, poll, cleared = false, redirect;
  const request = deferred();
  const elements = {
    "#summary-form": {
      dataset: {key: "NASDAQ:AAPL"}, attributes: {},
      addEventListener: (_, callback) => { submit = callback; },
      setAttribute(name, value) { this.attributes[name] = value; },
    },
    "#generate": {disabled: false}, "#summary-status": {textContent: "Ready"},
    "#summary-busy": {hidden: true}, "#hours": {value: "48"},
  };
  let statusResponse = async () => ({ok: true, json: async () => ({phase: "retrieving"})});
  vm.runInNewContext(code, {
    URLSearchParams,
    document: {querySelector: selector => elements[selector] || null},
    window: {location: {search: "", assign: url => { redirect = url; }}},
    setInterval: callback => { poll = callback; return 7; },
    clearInterval: id => { assert.equal(id, 7); cleared = true; },
    fetch: url => url.startsWith("/api/status") ? statusResponse() : request.promise,
  });
  return {
    elements, request, submit: () => submit({preventDefault() {}}), poll: () => poll(),
    statusResponse: callback => { statusResponse = callback; },
    cleared: () => cleared, redirect: () => redirect,
  };
}

test("indicator remains active across progress phases and stops on success", async () => {
  const page = progressPage();
  const completed = page.submit();
  assert.equal(page.elements["#summary-busy"].hidden, false);
  assert.equal(page.elements["#generate"].disabled, true);
  assert.equal(page.elements["#summary-form"].attributes["aria-busy"], "true");
  assert.equal(page.elements["#summary-status"].textContent, "Searching for news…");
  await page.poll();
  assert.equal(page.elements["#summary-status"].textContent, "Retrieving article text…");
  page.statusResponse(async () => ({json: async () => ({phase: "summarizing"})}));
  await page.poll();
  assert.equal(page.elements["#summary-status"].textContent, "Evaluating relevance and writing your briefing…");
  assert.equal(page.elements["#summary-busy"].hidden, false);
  page.request.resolve({ok: true, json: async () => ({result_id: "snapshot"})});
  await completed;
  assert.equal(page.elements["#summary-busy"].hidden, true);
  assert.equal(page.elements["#summary-form"].attributes["aria-busy"], "false");
  assert.equal(page.elements["#summary-status"].textContent, "Briefing ready. Opening results…");
  assert.equal(page.cleared(), true);
  assert.equal(page.redirect(), "/result?briefing=snapshot");
});

for (const failure of ["http", "network"]) {
  test("failure stops animation and permits retry: " + failure, async () => {
    const page = progressPage();
    const completed = page.submit();
    if (failure === "http") page.request.resolve({ok: false, json: async () => ({detail: "API unavailable"})});
    else page.request.reject(new Error("Network unavailable"));
    await completed;
    assert.equal(page.elements["#summary-busy"].hidden, true);
    assert.equal(page.elements["#generate"].disabled, false);
    assert.equal(page.elements["#summary-form"].attributes["aria-busy"], "false");
    assert.match(page.elements["#summary-status"].textContent, /unavailable/);
    assert.equal(page.cleared(), true);
    assert.equal(page.redirect(), undefined);
  });
}

test("a late status response cannot overwrite the final error", async () => {
  const page = progressPage();
  const completed = page.submit();
  const lateStatus = deferred();
  page.statusResponse(() => lateStatus.promise);
  const polling = page.poll();
  page.request.resolve({ok: false, json: async () => ({detail: "Quota reached"})});
  await completed;
  lateStatus.resolve({json: async () => ({phase: "summarizing"})});
  await polling;
  assert.equal(page.elements["#summary-status"].textContent, "Quota reached");
  assert.equal(page.elements["#summary-busy"].hidden, true);
});
