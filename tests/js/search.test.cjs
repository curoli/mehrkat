const assert = require("node:assert/strict");
const fs = require("node:fs");
const vm = require("node:vm");
const {test} = require("node:test");
const code = fs.readFileSync("src/mehrkat/static/app.js", "utf8");

class Element {
  constructor(properties = {}) {
    Object.assign(this, {children: [], listeners: {}}, properties);
  }
  append(child) { this.children.push(child); }
  replaceChildren() { this.children = []; }
  addEventListener(event, callback) { this.listeners[event] = callback; }
  setAttribute() {}
}
const settle = () => new Promise(resolve => setImmediate(resolve));

function searchPage(queryString) {
  const checkboxes = [
    new Element({name: "exchange", value: "NYSE", checked: true}),
    new Element({name: "exchange", value: "XETRA", checked: true}),
    new Element({name: "country", value: "Germany", checked: true}),
  ];
  const elements = Object.fromEntries(["search", "filters", "matches", "listings", "search-status", "clear-filters"]
    .map(id => ["#" + id, new Element()]));
  elements["#filters"].querySelectorAll = () => checkboxes;
  let scheduled;
  const calls = [];
  const context = {
    URL, URLSearchParams,
    setTimeout: callback => { scheduled = callback; return 1; },
    clearTimeout: () => { scheduled = null; },
    document: {querySelector: selector => elements[selector] || null, createElement: () => new Element()},
    window: {
      location: new URL("http://localhost/?" + queryString),
      history: {replaceState: (_, __, url) => { context.window.location = new URL(url, "http://localhost"); }},
    },
    fetch: async url => {
      calls.push(url);
      return {ok: true, json: async () => [
        {listing_key: "XETRA::SAP", name: "SAP SE", ticker: "SAP", exchange: "XETRA", country: "Germany", sector: "Technology"},
      ]};
    },
  };
  vm.runInNewContext(code, context);
  return {elements, calls, context, checkboxes, runScheduled: () => scheduled()};
}

test("filters alone trigger local search and survive selection links", async () => {
  const page = searchPage("exchange=NYSE&exchange=XETRA&country=Germany");
  await settle();
  const params = new URL(page.calls[0], "http://localhost").searchParams;
  assert.deepEqual(params.getAll("exchange"), ["NYSE", "XETRA"]);
  assert.equal(params.get("country"), "Germany");
  const cells = page.elements["#matches"].children[0].children;
  assert.equal(cells.length, 5);
  const link = new URL(cells[0].children[0].href, "http://localhost");
  assert.deepEqual(link.searchParams.getAll("exchange"), ["NYSE", "XETRA"]);
  assert.equal(link.searchParams.get("key"), "XETRA::SAP");
});

test("changing and clearing filters refreshes results and URL without losing query", async () => {
  const page = searchPage("q=SAP+%26+alias");
  await settle();
  assert.equal(page.elements["#search"].value, "SAP & alias");
  page.checkboxes[0].checked = false;
  page.elements["#filters"].listeners.change();
  await page.runScheduled();
  assert.deepEqual(page.context.window.location.searchParams.getAll("exchange"), ["XETRA"]);
  page.elements["#clear-filters"].listeners.click();
  await page.runScheduled();
  assert.equal(page.context.window.location.searchParams.get("q"), "SAP & alias");
  assert.equal(page.context.window.location.searchParams.has("exchange"), false);
  assert.equal(page.context.window.location.searchParams.has("country"), false);
});

test("briefing redirect preserves repeated filters and excludes listing key", async () => {
  const form = new Element({dataset: {key: "XETRA::SAP"}});
  const elements = {"#summary-form": form, "#generate": new Element(), "#summary-status": new Element(), "#hours": {value: "48"}};
  let redirect;
  vm.runInNewContext(code, {
    URLSearchParams, setInterval: () => 1, clearInterval: () => {},
    document: {querySelector: selector => elements[selector] || null},
    window: {location: {
      search: "?key=XETRA%3A%3ASAP&q=SAP&exchange=NYSE&exchange=XETRA&country=Germany&sector=Technology",
      assign: url => { redirect = new URL(url, "http://localhost"); },
    }},
    fetch: async () => ({ok: true}),
  });
  await form.listeners.submit({preventDefault() {}});
  assert.equal(redirect.pathname, "/result");
  assert.deepEqual(redirect.searchParams.getAll("exchange"), ["NYSE", "XETRA"]);
  assert.equal(redirect.searchParams.get("country"), "Germany");
  assert.equal(redirect.searchParams.get("sector"), "Technology");
  assert.equal(redirect.searchParams.has("key"), false);
});
