const search = document.querySelector("#search");
if (search) {
  let timer, sequence = 0;
  search.addEventListener("input", () => {
    clearTimeout(timer);
    const current = ++sequence;
    timer = setTimeout(async () => {
      try {
        const response = await fetch("/api/listings?q=" + encodeURIComponent(search.value));
        if (!response.ok) throw new Error("Search failed. Please retry.");
        const listings = await response.json();
        if (current !== sequence) return;
        const matches = document.querySelector("#matches");
        matches.replaceChildren();
        for (const row of listings) {
          const li = document.createElement("li");
          const link = document.createElement("a");
          link.href = "/listing?key=" + encodeURIComponent(row.listing_key);
          link.textContent = row.name + " · " + row.ticker + " · " + row.exchange + " · " + row.country;
          li.append(link);
          matches.append(li);
        }
        document.querySelector("#search-status").textContent = listings.length
          ? "Select a listing to continue." : "No matches. Try another query.";
      } catch (error) {
        document.querySelector("#search-status").textContent = error.message;
      }
    }, 180);
  });
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
      window.location.assign("/result");
    } catch (error) {
      status.textContent = error.message;
      button.disabled = false;
      form.setAttribute("aria-busy", "false");
    } finally {
      clearInterval(poll);
    }
  });
}
