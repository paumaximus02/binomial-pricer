function formatDate(d) {
  return d.toISOString().slice(0, 10);
}

function addDays(date, days) {
  const d = new Date(date);
  d.setDate(d.getDate() + days);
  return d;
}

function initDates() {
  const today = new Date();
  const expiry = addDays(today, 30);

  for (const id of ["valuation_date", "iv-valuation_date"]) {
    document.getElementById(id).value = formatDate(today);
  }
  for (const id of ["expiry", "iv-expiry"]) {
    document.getElementById(id).value = formatDate(expiry);
  }
}

function setupSpotMode(prefix = "") {
  const modeName = prefix ? `${prefix}-spot-mode` : "spot-mode";
  const symbolId = prefix ? `${prefix}-symbol-field` : "symbol-field";
  const spotId = prefix ? `${prefix}-spot-field` : "spot-field";

  document.querySelectorAll(`input[name="${modeName}"]`).forEach((radio) => {
    radio.addEventListener("change", () => {
      const manual = document.querySelector(`input[name="${modeName}"]:checked`).value === "manual";
      document.getElementById(symbolId).classList.toggle("hidden", manual);
      document.getElementById(spotId).classList.toggle("hidden", !manual);
    });
  });
}

function showToast(message, type = "error") {
  const toast = document.getElementById("toast");
  toast.textContent = message;
  toast.className = `toast ${type === "success" ? "success" : ""}`;
  toast.classList.remove("hidden");
  clearTimeout(showToast._timer);
  showToast._timer = setTimeout(() => toast.classList.add("hidden"), 5000);
}

async function api(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = typeof detail === "string" ? detail : JSON.stringify(detail);
    throw new Error(msg || `Request failed (${res.status})`);
  }
  return data;
}

async function fetchSpot(symbol) {
  const res = await fetch(`/market/spot/${encodeURIComponent(symbol.trim())}`);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `Could not fetch spot (${res.status})`);
  }
  return data;
}

function fmt(n, digits = 4) {
  if (n == null || Number.isNaN(n)) return "—";
  return Number(n).toFixed(digits);
}

function fmtPct(n) {
  return `${(Number(n) * 100).toFixed(2)}%`;
}

function renderMetrics(container, items) {
  container.innerHTML = items
    .map(
      ({ label, value, highlight }) => `
    <div class="metric">
      <div class="metric-label">${label}</div>
      <div class="metric-value${highlight ? " highlight" : ""}">${value}</div>
    </div>`
    )
    .join("");
}

function buildSpotPayload(modeName, symbolId, spotId) {
  const manual = document.querySelector(`input[name="${modeName}"]:checked`).value === "manual";
  const payload = {};
  if (manual) {
    const spot = parseFloat(document.getElementById(spotId).value);
    if (!spot || spot <= 0) throw new Error("Enter a valid spot price.");
    payload.spot = spot;
  } else {
    const symbol = document.getElementById(symbolId).value.trim();
    if (!symbol) throw new Error("Enter a stock symbol or switch to manual spot.");
    payload.symbol = symbol.toUpperCase();
  }
  return payload;
}

function optionalRate(inputId) {
  const raw = document.getElementById(inputId).value.trim();
  if (!raw) return undefined;
  return parseFloat(raw);
}

// Tabs
document.querySelectorAll(".tab").forEach((tab) => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach((t) => {
      t.classList.remove("active");
      t.setAttribute("aria-selected", "false");
    });
    tab.classList.add("active");
    tab.setAttribute("aria-selected", "true");

    document.querySelectorAll(".panel").forEach((p) => {
      p.classList.remove("active");
      p.hidden = true;
    });
    const panel = document.getElementById(`panel-${tab.dataset.tab}`);
    panel.classList.add("active");
    panel.hidden = false;
  });
});

// Fetch spot preview
document.getElementById("fetch-spot-btn").addEventListener("click", async () => {
  const symbol = document.getElementById("symbol").value.trim();
  if (!symbol) {
    showToast("Enter a symbol first.");
    return;
  }
  const btn = document.getElementById("fetch-spot-btn");
  btn.disabled = true;
  try {
    const data = await fetchSpot(symbol);
    const preview = document.getElementById("spot-preview");
    preview.textContent = `${data.symbol}: $${fmt(data.price, 2)} (as of ${data.as_of})`;
    preview.classList.remove("hidden");
    showToast(`Fetched ${data.symbol} spot: $${fmt(data.price, 2)}`, "success");
  } catch (err) {
    showToast(err.message);
  } finally {
    btn.disabled = false;
  }
});

// Price form
document.getElementById("price-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;

  try {
    const body = {
      ...buildSpotPayload("spot-mode", "symbol", "spot"),
      strike: parseFloat(document.getElementById("strike").value),
      vol: parseFloat(document.getElementById("vol").value),
      expiry: document.getElementById("expiry").value,
      valuation_date: document.getElementById("valuation_date").value,
      option_type: document.getElementById("option_type").value,
      style: document.getElementById("style").value,
    };
    const rate = optionalRate("rate");
    if (rate != null) body.rate = rate;

    const data = await api("/price", body);

    document.getElementById("price-meta").innerHTML = [
      data.symbol ? `<strong>${data.symbol}</strong> · ` : "",
      `Spot $${fmt(data.spot, 2)} · Strike $${fmt(data.strike, 2)} · `,
      `Vol ${fmtPct(data.vol)} · Rate ${fmtPct(data.rate)} · `,
      `T = ${fmt(data.time_to_expiry, 4)} yrs · `,
      `${data.option_type} (${data.style})`,
    ].join("");

    renderMetrics(document.getElementById("price-grid"), [
      { label: "Price", value: `$${fmt(data.price, 4)}`, highlight: true },
      { label: "Delta", value: fmt(data.delta, 4) },
      { label: "Gamma", value: fmt(data.gamma, 6) },
      { label: "Theta", value: fmt(data.theta, 4) },
      { label: "Vega", value: fmt(data.vega, 4) },
    ]);

    document.getElementById("price-results").classList.remove("hidden");
  } catch (err) {
    showToast(err.message);
  } finally {
    btn.disabled = false;
  }
});

// IV form
document.getElementById("iv-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const btn = e.target.querySelector('button[type="submit"]');
  btn.disabled = true;

  try {
    const body = {
      market_price: parseFloat(document.getElementById("iv-market-price").value),
      ...buildSpotPayload("iv-spot-mode", "iv-symbol", "iv-spot"),
      strike: parseFloat(document.getElementById("iv-strike").value),
      expiry: document.getElementById("iv-expiry").value,
      valuation_date: document.getElementById("iv-valuation_date").value,
      option_type: document.getElementById("iv-option_type").value,
      style: document.getElementById("iv-style").value,
    };
    const rate = optionalRate("iv-rate");
    if (rate != null) body.rate = rate;

    const data = await api("/iv", body);

    document.getElementById("iv-meta").innerHTML = [
      `Spot $${fmt(data.spot, 2)} · Strike $${fmt(data.strike, 2)} · `,
      `Market $${fmt(data.market_price, 4)} · T = ${fmt(data.time_to_expiry, 4)} yrs · `,
      `${data.option_type} (${data.style})`,
    ].join("");

    renderMetrics(document.getElementById("iv-grid"), [
      { label: "Implied vol", value: fmtPct(data.implied_volatility), highlight: true },
      { label: "Market price", value: `$${fmt(data.market_price, 4)}` },
      { label: "Spot", value: `$${fmt(data.spot, 2)}` },
      { label: "Strike", value: `$${fmt(data.strike, 2)}` },
      { label: "Time (yrs)", value: fmt(data.time_to_expiry, 4) },
    ]);

    document.getElementById("iv-results").classList.remove("hidden");
  } catch (err) {
    showToast(err.message);
  } finally {
    btn.disabled = false;
  }
});

initDates();
setupSpotMode();
setupSpotMode("iv");
