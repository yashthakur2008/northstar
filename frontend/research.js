const gate = document.querySelector("#portfolio-gate");
const workspace = document.querySelector("#portfolio-workspace");
const form = document.querySelector("#portfolio-form");
const emptyState = document.querySelector("#portfolio-empty");
const dashboard = document.querySelector("#portfolio-dashboard");
const stats = document.querySelector("#portfolio-stats");
const chart = document.querySelector("#portfolio-chart");
const allocation = document.querySelector("#portfolio-allocation");
const table = document.querySelector("#portfolio-table");
const refreshLabel = document.querySelector("#portfolio-refresh");
const money = new Intl.NumberFormat("en-US", {style:"currency", currency:"USD", maximumFractionDigits:2});
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character]));
const signedMoney = value => `${Number(value) >= 0 ? "+" : "−"}${money.format(Math.abs(Number(value) || 0))}`;

function portfolioChartMarkup(points) {
  if (!points || points.length < 2) return `<div class="portfolio-chart-missing">More market history is needed to draw this chart.</div>`;
  const width = 1080, height = 430, pad = {left:82,right:24,top:24,bottom:48};
  const values = points.map(point => point.value);
  const low = Math.min(...values), high = Math.max(...values);
  const margin = Math.max((high - low) * .12, high * .005);
  const min = Math.max(0, low - margin), max = high + margin;
  const x = index => pad.left + index / (points.length - 1) * (width - pad.left - pad.right);
  const y = value => pad.top + (max - value) / Math.max(max - min, .01) * (height - pad.top - pad.bottom);
  const line = points.map((point,index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.value).toFixed(1)}`).join(" ");
  const area = `${line}L${x(points.length-1)},${height-pad.bottom}L${x(0)},${height-pad.bottom}Z`;
  const yTicks = Array.from({length:6},(_,index) => max - (max-min)*index/5);
  const dateIndexes = [0,.25,.5,.75,1].map(ratio => Math.round((points.length-1)*ratio));
  return `<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Recent portfolio market value">
    <defs><linearGradient id="portfolio-area" x1="0" y1="0" x2="0" y2="1"><stop stop-color="#21a77b" stop-opacity=".28"/><stop offset="1" stop-color="#21a77b" stop-opacity="0"/></linearGradient></defs>
    ${yTicks.map(value => `<line class="portfolio-grid" x1="${pad.left}" x2="${width-pad.right}" y1="${y(value)}" y2="${y(value)}"/><text class="portfolio-axis" x="${pad.left-12}" y="${y(value)+4}" text-anchor="end">${money.format(value)}</text>`).join("")}
    ${dateIndexes.map(index => `<line class="portfolio-grid vertical" x1="${x(index)}" x2="${x(index)}" y1="${pad.top}" y2="${height-pad.bottom}"/>`).join("")}
    <path class="portfolio-area" d="${area}"/><path class="portfolio-line" d="${line}"/>
    ${dateIndexes.map((index,tick) => `<text class="portfolio-axis" x="${x(index)}" y="${height-14}" text-anchor="${tick===0?"start":tick===4?"end":"middle"}">${new Date(points[index].timestamp).toLocaleDateString([], {month:"short",day:"numeric"})}</text>`).join("")}
  </svg>`;
}

function render(data) {
  const rows = data.holdings || [];
  refreshLabel.textContent = `${data.source_status === "live" ? "Live provider refresh" : "Partial data"} · ${new Date(data.generated_at).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"})}`;
  emptyState.hidden = Boolean(rows.length);
  dashboard.hidden = !rows.length;
  if (!rows.length) return;
  stats.innerHTML = [
    ["Market value", money.format(data.total_value)],
    ["Latest session", signedMoney(data.day_change_value), data.day_change_value >= 0 ? "positive" : "negative"],
    ["Return vs. cost", data.total_return_pct == null ? "Add cost basis" : `${data.total_return_pct >= 0 ? "+" : ""}${data.total_return_pct.toFixed(2)}%`, data.total_return_pct >= 0 ? "positive" : "negative"],
    ["Realized volatility", data.volatility == null ? "Building history" : `${data.volatility.toFixed(1)}%`],
    ["Best contributor", data.best_contributor || "—"],
    ["Holdings", String(rows.length)],
  ].map(([label,value,tone=""]) => `<article><span>${label}</span><strong class="${tone}">${value}</strong></article>`).join("");
  document.querySelector("#portfolio-chart-value").textContent = money.format(data.total_value);
  const history = data.history || [];
  document.querySelector("#portfolio-chart-range").textContent = history.length ? `${new Date(history[0].timestamp).toLocaleDateString()}–${new Date(history.at(-1).timestamp).toLocaleDateString()}` : "";
  chart.innerHTML = portfolioChartMarkup(history);
  allocation.innerHTML = rows.map((row,index) => {
    const weight = data.total_value ? row.market_value / data.total_value * 100 : 0;
    return `<div><span><i style="--allocation-index:${index}"></i><strong>${escapeHtml(row.symbol)}</strong><small>${weight.toFixed(1)}%</small></span><b><i style="width:${weight.toFixed(2)}%"></i></b><em>${money.format(row.market_value)}</em></div>`;
  }).join("");
  table.innerHTML = `<div class="portfolio-table-head"><span>Holding</span><span>Shares</span><span>Latest</span><span>Market value</span><span>Session</span><span></span></div>${rows.map(row => `<article><strong>${escapeHtml(row.symbol)}</strong><span>${row.shares.toLocaleString()}</span><span>${money.format(row.last_price)}</span><span>${money.format(row.market_value)}</span><span class="${row.day_change_value>=0?"positive":"negative"}">${signedMoney(row.day_change_value)} (${row.day_change_pct>=0?"+":""}${row.day_change_pct.toFixed(2)}%)</span><button data-remove="${escapeHtml(row.symbol)}" type="button">Remove</button></article>`).join("")}`;
  table.querySelectorAll("[data-remove]").forEach(button => button.addEventListener("click", async () => {
    button.disabled = true;
    const response = await fetch(`/api/portfolio/holdings/${encodeURIComponent(button.dataset.remove)}`, {method:"DELETE"});
    if (response.ok) render(await response.json());
  }));
}

async function loadPortfolio() {
  const response = await fetch("/api/portfolio");
  if (response.status === 401) { gate.hidden = false; workspace.hidden = true; return; }
  if (!response.ok) return;
  gate.hidden = true; workspace.hidden = false; render(await response.json());
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const button = form.querySelector("button");
  button.disabled = true;
  const payload = {
    symbol: document.querySelector("#portfolio-symbol").value.trim().toUpperCase(),
    shares: Number(document.querySelector("#portfolio-shares").value),
    average_cost: Number(document.querySelector("#portfolio-cost").value) || null,
  };
  try {
    const response = await fetch("/api/portfolio/holdings", {method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload)});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "Unable to save this holding.");
    form.reset(); render(result);
  } catch (error) {
    emptyState.hidden = false; emptyState.textContent = error.message;
  } finally { button.disabled = false; }
});

loadPortfolio();
setInterval(loadPortfolio, 60000);
