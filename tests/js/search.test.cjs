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
    new Element({name: "sector", value: "Technology", checked: false}),
  ];
  const elements = Object.fromEntries(["search", "filters", "matches", "listings", "search-status", "clear-filters"]
    .map(id => ["#" + id, new Element()]));
  for (const name of ["exchange", "country", "sector"]) {
    elements["#count-" + name] = new Element();
    elements["#reset-" + name] = new Element();
  }
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
  for (const name of ["exchange", "country", "sector"]) {
    assert.equal(page.elements["#count-" + name].textContent, "0 selected");
    assert.equal(page.elements["#reset-" + name].disabled, true);
  }
});

test("briefing redirect preserves repeated filters and excludes listing key", async () => {
  const form = new Element({dataset: {key: "XETRA::SAP"}});
  const elements = {"#summary-form": form, "#generate": new Element(), "#summary-status": new Element(), "#summary-busy": new Element(), "#hours": {value: "48"}};
  let redirect;
  vm.runInNewContext(code, {
    URLSearchParams, setInterval: () => 1, clearInterval: () => {},
    document: {querySelector: selector => elements[selector] || null},
    window: {location: {
      search: "?key=XETRA%3A%3ASAP&q=SAP&exchange=NYSE&exchange=XETRA&country=Germany&sector=Technology",
      assign: url => { redirect = new URL(url, "http://localhost"); },
    }},
    fetch: async () => ({ok: true, json: async () => ({result_id: "briefing-snapshot"})}),
  });
  await form.listeners.submit({preventDefault() {}});
  assert.equal(redirect.pathname, "/result");
  assert.equal(redirect.searchParams.get("briefing"), "briefing-snapshot");
  assert.deepEqual(redirect.searchParams.getAll("exchange"), ["NYSE", "XETRA"]);
  assert.equal(redirect.searchParams.get("country"), "Germany");
  assert.equal(redirect.searchParams.get("sector"), "Technology");
  assert.equal(redirect.searchParams.has("key"), false);
});


test("counts update immediately on initialization and checkbox changes", async () => {
  const page = searchPage("q=SAP");
  await settle();
  assert.equal(page.elements["#count-exchange"].textContent, "2 selected");
  assert.equal(page.elements["#count-country"].textContent, "1 selected");
  assert.equal(page.elements["#count-sector"].textContent, "0 selected");
  assert.equal(page.elements["#reset-sector"].disabled, true);
  const requests = page.calls.length;
  page.checkboxes[3].checked = true;
  page.elements["#filters"].listeners.change();
  assert.equal(page.calls.length, requests); // Update controls before the debounced search.
  assert.equal(page.elements["#count-sector"].textContent, "1 selected");
  assert.equal(page.elements["#reset-sector"].disabled, false);
  page.checkboxes[3].checked = false;
  page.elements["#filters"].listeners.change();
  assert.equal(page.elements["#count-sector"].textContent, "0 selected");
  assert.equal(page.elements["#reset-sector"].disabled, true);
});

for (const name of ["exchange", "country", "sector"]) {
  test("reset only " + name + " while preserving the query and other groups", async () => {
    const page = searchPage("q=SAP+%26+alias");
    await settle();
    page.checkboxes[3].checked = true;
    page.elements["#filters"].listeners.change();
    await page.runScheduled();
    page.elements["#reset-" + name].listeners.click();
    assert.equal(page.elements["#count-" + name].textContent, "0 selected");
    assert.equal(page.elements["#reset-" + name].disabled, true);
    assert.ok(page.checkboxes.filter(c => c.name !== name).every(c => c.checked));
    await page.runScheduled();
    const params = page.context.window.location.searchParams;
    const submitted = new URL(page.calls.at(-1), "http://localhost").searchParams;
    assert.equal(params.get("q"), "SAP & alias");
    assert.equal(params.has(name), false);
    assert.equal(submitted.toString(), params.toString());
    for (const other of ["exchange", "country", "sector"].filter(group => group !== name)) {
      assert.equal(params.has(other), true);
    }
    const link = new URL(page.elements["#matches"].children[0].children[0].children[0].href, "http://localhost");
    assert.equal(link.searchParams.has(name), false);
    assert.equal(link.searchParams.get("q"), "SAP & alias");
  });
}
