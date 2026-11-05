const search = document.querySelector("#search");
if (search) {
  let timer, sequence = 0;
  const updateMatches = async () => {
    const current = ++sequence;
    const query = search.value;
    const url = new URL(window.location.href);
    if (query) url.searchParams.set("q", query);
    else url.searchParams.delete("q");
    window.history.replaceState(null, "", url);
    try {
      const response = await fetch("/api/listings?q=" + encodeURIComponent(query));
      if (!response.ok) throw new Error("Search failed. Please retry.");
      const listings = await response.json();
      if (current !== sequence) return;
      const matches = document.querySelector("#matches");
      matches.replaceChildren();
      document.querySelector("#listings").hidden = listings.length === 0;
      for (const row of listings) {
        const tr = document.createElement("tr");
        const company = document.createElement("td");
        const link = document.createElement("a");
        link.href = "/listing?" + new URLSearchParams({key: row.listing_key, q: query});
        link.textContent = row.name;
        company.append(link);
        tr.append(company);
        for (const value of [row.ticker, row.exchange, row.country, row.sector]) {
          const cell = document.createElement("td");
          cell.textContent = value || "Not available";
          tr.append(cell);
        }
        matches.append(tr);
      }
      document.querySelector("#search-status").textContent = listings.length
        ? "Select a listing to continue." : "No matches. Try another query.";
    } catch (error) {
      if (current !== sequence) return;
      document.querySelector("#search-status").textContent = error.message;
    }
  };
  search.addEventListener("input", () => {
    clearTimeout(timer);
    ++sequence;
    timer = setTimeout(updateMatches, 180);
  });
  search.value = new URLSearchParams(window.location.search).get("q") || "";
  if (search.value) updateMatches();
}
const form = document.querySelector("#summary-form");
if (form) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = document.querySelector("#generate");
    const status = document.querySelector("#summary-status");
    button.disabled = true;
    form.setAttribute("aria-busy", "true");
    status.textContent = "Searching for news…";
    const poll = setInterval(async () => {
      try {
        const response = await fetch("/api/status");
        const data = await response.json();
        if (data.phase === "retrieving") status.textContent = "Retrieving article text…";
        if (data.phase === "summarizing") status.textContent = "Evaluating relevance and writing your briefing…";
      } catch { /* The main request reports connection errors. */ }
    }, 1500);
    try {
      const response = await fetch("/api/summary?key=" + encodeURIComponent(form.dataset.key)
        + "&hours=" + document.querySelector("#hours").value, {method: "POST"});
      if (!response.ok) {
        const data = await response.json();
        throw new Error(typeof data.detail === "string" ? data.detail : "Request failed. Please retry.");
      }
      const query = new URLSearchParams(window.location.search).get("q");
      window.location.assign(query ? "/result?" + new URLSearchParams({q: query}) : "/result");
    } catch (error) {
      status.textContent = error.message;
      button.disabled = false;
      form.setAttribute("aria-busy", "false");
    } finally {
      clearInterval(poll);
    }
  });
}
