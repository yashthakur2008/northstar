const form = document.querySelector("#analyze-form");
const runButton = document.querySelector("#run-button");
const statusEl = document.querySelector("#status");
const workspace = document.querySelector("#workspace");
const debateEl = document.querySelector("#debate");
const resultsEl = document.querySelector("#results");
const eventCount = document.querySelector("#event-count");
const sourceBadge = document.querySelector("#source-badge");
const runMeta = document.querySelector("#run-meta");
const methodology = document.querySelector("#methodology");
const themeToggle = document.querySelector("#theme-toggle");
const analysisProgress = document.querySelector("#analysis-progress");
const progressStage = document.querySelector("#progress-stage");
const progressPercent = document.querySelector("#progress-percent");
const progressFill = document.querySelector("#progress-fill");
const pulseViewport = document.querySelector("#pulse-viewport");
const pulseTrack = document.querySelector("#pulse-track");
const pulseStatus = document.querySelector("#pulse-status");
const newsGrid = document.querySelector("#news-grid");
const pulseFormat = document.querySelector("#pulse-format");
const stockDetail = document.querySelector("#stock-detail");
const detailContent = document.querySelector("#detail-content");
const analyzerForm = document.querySelector("#analyzer-form");
const analyzerOutput = document.querySelector("#analyzer-output");
let pulseIndex = 0;
let pulseStocks = [];
let pulseNews = [];
let pulseFrame = null;
let pulseLastFrame = 0;
let pulseResumeAt = 0;
let pulseSetWidth = 0;
let pulsePosition = 0;
let pulseDragging = false;
let pulseDragMoved = false;
let pulseDragStartX = 0;
let pulseDragStartScroll = 0;

const agentInitial = {"Market Data":"M","Technical":"T","Bull":"B+","Bear":"B−","Risk":"R","Portfolio Manager":"PM"};
const money = new Intl.NumberFormat("en-US", {style:"currency", currency:"USD", maximumFractionDigits:2});

function applyTheme(theme, persist = true) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  themeToggle.setAttribute("aria-pressed", String(dark));
  themeToggle.setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} mode`);
  themeToggle.querySelector(".theme-icon").textContent = dark ? "☀" : "☾";
  themeToggle.querySelector(".theme-label").textContent = dark ? "Light" : "Dark";
  if (persist) {
    try {
      localStorage.setItem("northstar-theme", dark ? "dark" : "light");
    } catch (_) {}
  }
}

applyTheme(document.documentElement.dataset.theme || "light", false);
themeToggle.addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

function parseTickers(value) {
  return [...new Set(value.split(",").map(value => value.trim().toUpperCase()).filter(Boolean))];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character]));
}

function safeExternalUrl(value) {
  try {
    const url = new URL(value);
    return ["https:", "http:"].includes(url.protocol) ? url.href : "#";
  } catch (_) {
    return "#";
  }
}

function pulseGraphic(points, positive, format = "line") {
  if (!points || points.length < 2) return "";
  const width = 260;
  const height = 74;
  const values = points.map(point => point.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const x = index => (index / (points.length - 1)) * width;
  const y = value => 4 + ((max - value) / Math.max(max - min, .01)) * (height - 8);
  if (format === "box") {
    const selected = points.slice(-16);
    return `<div class="pulse-boxes" role="img" aria-label="Daily price range boxes">${selected.map((point, index) => {
      const previous = selected[Math.max(0, index - 1)].close;
      const heightPct = 28 + ((point.close - min) / Math.max(max - min, .01)) * 72;
      return `<i class="${point.close >= previous ? "up" : "down"}" style="height:${heightPct.toFixed(1)}%" title="${money.format(point.close)}"></i>`;
    }).join("")}</div>`;
  }
  const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.close).toFixed(1)}`).join(" ");
  return `<svg class="pulse-chart ${positive ? "positive-chart" : "negative-chart"}" viewBox="0 0 ${width} ${height}" role="img" aria-label="Recent closing-price trend"><path d="${path}"/></svg>`;
}

function updatePulseFocus() {
  const cards = [...pulseTrack.querySelectorAll(".pulse-card")];
  if (!cards.length) return;
  const center = pulseViewport.scrollLeft + pulseViewport.clientWidth / 2;
  let nearest = cards[0];
  let distance = Infinity;
  cards.forEach(card => {
    const cardDistance = Math.abs(card.offsetLeft + card.offsetWidth / 2 - center);
    if (cardDistance < distance) {
      distance = cardDistance;
      nearest = card;
    }
  });
  cards.forEach(card => card.classList.toggle("is-active", card === nearest));
  pulseIndex = Number(nearest.dataset.index);
}

function setPulseIndex(index, behavior = "smooth") {
  const cards = [...pulseTrack.querySelectorAll('.pulse-card[data-copy="1"]')];
  if (!cards.length) return;
  pulseIndex = (index + cards.length) % cards.length;
  const card = cards[pulseIndex];
  pulsePosition = card.offsetLeft - (pulseViewport.clientWidth - card.offsetWidth) / 2;
  pulseViewport.scrollTo({
    left: pulsePosition,
    behavior,
  });
  updatePulseFocus();
}

function pausePulseForManual() {
  pulseResumeAt = performance.now() + 5000;
}

function normalizePulsePosition() {
  const middle = pulseTrack.querySelector('.pulse-card[data-copy="1"]');
  const final = pulseTrack.querySelector('.pulse-card[data-copy="2"]');
  if (!middle || !final || !pulseSetWidth) return;
  if (pulsePosition >= final.offsetLeft) pulsePosition -= pulseSetWidth;
  if (pulsePosition < middle.offsetLeft - pulseSetWidth * .15) pulsePosition += pulseSetWidth;
  pulseViewport.scrollLeft = pulsePosition;
}

function animatePulse(timestamp) {
  const elapsed = Math.min(40, timestamp - (pulseLastFrame || timestamp));
  pulseLastFrame = timestamp;
  if (!matchMedia("(prefers-reduced-motion: reduce)").matches && timestamp >= pulseResumeAt && pulseSetWidth) {
    const ramp = Math.min(1, (timestamp - pulseResumeAt) / 700);
    pulsePosition += .085 * ramp * elapsed;
    normalizePulsePosition();
    updatePulseFocus();
  }
  pulseFrame = requestAnimationFrame(animatePulse);
}

function openStockDetail(stock) {
  const points = stock.history || [];
  const positive = stock.change_pct >= 0;
  const firstDate = new Date(points[0].timestamp);
  const lastDate = new Date(points.at(-1).timestamp);
  detailContent.innerHTML = `
    <p class="kicker">Market snapshot</p>
    <div class="detail-title"><div><h2>${escapeHtml(stock.symbol)}</h2><span>${firstDate.toLocaleDateString()}–${lastDate.toLocaleDateString()}</span></div><strong class="${positive ? "positive" : "negative"}">${positive ? "+" : ""}${stock.change_pct.toFixed(2)}%</strong></div>
    <div class="detail-price">${money.format(stock.last_price)}</div>
    <div class="detail-chart">${pulseGraphic(points, positive, "line")}</div>
    <div class="detail-meta"><span>Latest close <strong>${lastDate.toLocaleDateString()}</strong></span><span>Data source <strong>${escapeHtml(stock.source)}</strong></span></div>
    <button id="detail-analyze" type="button">Open in Stock Analyzer →</button>`;
  stockDetail.showModal();
  document.querySelector("#detail-analyze").addEventListener("click", () => {
    document.querySelector("#analyzer-symbol").value = stock.symbol;
    document.querySelector("#analyzer-period").value = "3mo";
    stockDetail.close();
    document.querySelector("#stock-analyzer").scrollIntoView({behavior:"smooth", block:"start"});
    analyzerForm.requestSubmit();
  });
}

function analyzeFromPulse(stock) {
  pausePulseForManual();
  document.querySelector("#analyzer-symbol").value = stock.symbol;
  document.querySelector("#analyzer-period").value = "3mo";
  document.querySelector("#stock-analyzer").scrollIntoView({behavior:"smooth", block:"start"});
  analyzerForm.requestSubmit();
}

function pulseCardMarkup(stock, index, copy) {
  const positive = stock.change_pct >= 0;
  const firstDate = new Date(stock.history[0].timestamp);
  const lastDate = new Date(stock.history.at(-1).timestamp);
  const dateRange = `${firstDate.toLocaleDateString([], {month:"short", day:"numeric"})}–${lastDate.toLocaleDateString([], {month:"short", day:"numeric", year:"numeric"})}`;
  return `<button class="pulse-card" type="button" data-symbol="${escapeHtml(stock.symbol)}" data-index="${index}" data-copy="${copy}" aria-label="Open ${escapeHtml(stock.symbol)} detailed chart">
    <div class="pulse-card-head"><strong>${escapeHtml(stock.symbol)}</strong><span class="${positive ? "positive" : "negative"}">${positive ? "+" : ""}${stock.change_pct.toFixed(2)}%</span></div>
    <div class="pulse-price">${money.format(stock.last_price)}</div>
    ${pulseGraphic(stock.history, positive, pulseFormat.value)}
    <div class="pulse-card-foot"><span>${dateRange}</span><span>Analyze ${escapeHtml(stock.symbol)} →</span></div>
  </button>`;
}

function renderMarketPulse(payload) {
  const stocks = payload.stocks || [];
  if (stocks.length) {
    pulseStocks = stocks;
    pulseTrack.innerHTML = [0, 1, 2].map(copy => stocks.map((stock, index) => pulseCardMarkup(stock, index, copy)).join("")).join("");
    pulseTrack.querySelectorAll(".pulse-card").forEach(card => card.addEventListener("click", () => {
      if (!pulseDragMoved) analyzeFromPulse(pulseStocks[Number(card.dataset.index)]);
    }));
    requestAnimationFrame(() => {
      const first = pulseTrack.querySelector('.pulse-card[data-copy="1"]');
      const next = pulseTrack.querySelector('.pulse-card[data-copy="2"]');
      pulseSetWidth = next.offsetLeft - first.offsetLeft;
      setPulseIndex(0, "auto");
      pulseResumeAt = performance.now();
      if (!pulseFrame) pulseFrame = requestAnimationFrame(animatePulse);
    });
    pulseStatus.textContent = `${stocks.length} current snapshots · Updated ${new Date(payload.generated_at).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})} · Continuous live tape · Drag or scroll manually`;
  } else {
    pulseTrack.innerHTML = `<div class="pulse-loading">Market snapshots are temporarily unavailable.</div>`;
    pulseStatus.textContent = "The research desk remains available; this non-critical market rail will retry on the next load.";
  }

  const news = payload.news || [];
  pulseNews = news;
  newsGrid.innerHTML = news.length ? news.map((item, index) => `
    <a class="news-card${index === 0 ? " lead-news" : ""}${item.is_trending ? " is-trending" : ""}" href="${escapeHtml(safeExternalUrl(item.url))}" target="_blank" rel="noopener noreferrer">
      <div class="news-visual${item.image_url ? "" : " is-fallback"}">
        ${item.image_url ? `<img src="${escapeHtml(safeExternalUrl(item.image_url))}" alt="" loading="lazy">` : ""}
        <span class="news-visual-label">${escapeHtml(item.publisher)}</span>
        <svg viewBox="0 0 240 90" aria-hidden="true"><path d="M0 72 L30 61 L58 66 L87 35 L115 49 L145 21 L174 39 L206 14 L240 27"/></svg>
      </div>
      <div class="news-body">
        <div class="news-byline">${item.is_trending ? `<span class="trending-badge">Trending</span>` : ""}<span class="news-meta">${escapeHtml(item.publisher)} · ${new Date(item.published_at).toLocaleString([], {month:"short", day:"numeric", hour:"numeric", minute:"2-digit"})}</span></div>
        <strong>${escapeHtml(item.title)}</strong>
        <span class="news-link">Read coverage <span aria-hidden="true">↗</span></span>
      </div>
    </a>`).join("") : `<div class="news-loading">Headlines are temporarily unavailable. Stock updates remain live.</div>`;
  newsGrid.querySelectorAll(".news-visual img").forEach(image => image.addEventListener("error", () => {
    image.hidden = true;
    image.parentElement.classList.add("is-fallback");
  }, {once:true}));
}

async function loadMarketPulse(symbols = []) {
  try {
    const query = symbols.length ? `?symbols=${encodeURIComponent(symbols.join(","))}` : "";
    const response = await fetch(`/api/market-pulse${query}`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    renderMarketPulse(await response.json());
  } catch (_) {
    renderMarketPulse({stocks:[], news:[]});
  }
}

pulseFormat.addEventListener("change", () => {
  if (pulseStocks.length) renderMarketPulse({stocks:pulseStocks, news:pulseNews, generated_at:new Date().toISOString()});
});
pulseViewport.addEventListener("wheel", () => {
  pausePulseForManual();
  requestAnimationFrame(() => { pulsePosition = pulseViewport.scrollLeft; updatePulseFocus(); });
}, {passive:true});
pulseViewport.addEventListener("touchstart", pausePulseForManual, {passive:true});
pulseViewport.addEventListener("scroll", () => {
  if (performance.now() < pulseResumeAt) {
    pulsePosition = pulseViewport.scrollLeft;
    updatePulseFocus();
  }
}, {passive:true});
pulseViewport.addEventListener("keydown", event => {
  if (event.key === "ArrowLeft") setPulseIndex(pulseIndex - 1);
  if (event.key === "ArrowRight") setPulseIndex(pulseIndex + 1);
  if (["ArrowLeft", "ArrowRight"].includes(event.key)) pausePulseForManual();
});
pulseViewport.addEventListener("pointerdown", event => {
  pulseDragging = true;
  pulseDragMoved = false;
  pulseDragStartX = event.clientX;
  pulseDragStartScroll = pulseViewport.scrollLeft;
  pulseViewport.setPointerCapture(event.pointerId);
  pausePulseForManual();
});
pulseViewport.addEventListener("pointermove", event => {
  if (!pulseDragging) return;
  const distance = event.clientX - pulseDragStartX;
  pulseDragMoved = pulseDragMoved || Math.abs(distance) > 5;
  pulseViewport.scrollLeft = pulseDragStartScroll - distance;
  pulsePosition = pulseViewport.scrollLeft;
  normalizePulsePosition();
  updatePulseFocus();
});
pulseViewport.addEventListener("pointerup", () => {
  pulseDragging = false;
  setTimeout(() => { pulseDragMoved = false; }, 0);
});
document.querySelector("#detail-close").addEventListener("click", () => stockDetail.close());
stockDetail.addEventListener("click", event => {
  if (event.target === stockDetail) stockDetail.close();
});
loadMarketPulse();

function compactNumber(value) {
  return new Intl.NumberFormat("en-US", {notation:"compact", maximumFractionDigits:1}).format(value);
}

function analyzerChartMarkup(data, type) {
  const source = data.history || [];
  const step = Math.max(1, Math.ceil(source.length / 110));
  const points = source.filter((_, index) => index % step === 0 || index === source.length - 1);
  const width = 900;
  const height = 330;
  const pad = {top:20, right:20, bottom:42, left:66};
  const low = Math.min(...points.map(point => point.low));
  const high = Math.max(...points.map(point => point.high));
  const margin = Math.max((high - low) * .08, high * .002);
  const min = low - margin;
  const max = high + margin;
  const x = index => pad.left + (index / Math.max(points.length - 1, 1)) * (width - pad.left - pad.right);
  const y = value => pad.top + ((max - value) / Math.max(max - min, .01)) * (height - pad.top - pad.bottom);
  const gridValues = [max, (max + min) / 2, min];
  let marks = "";
  if (type === "candle") {
    const candleWidth = Math.max(2, Math.min(9, (width - pad.left - pad.right) / points.length * .6));
    marks = points.map((point, index) => {
      const up = point.close >= point.open;
      const bodyTop = y(Math.max(point.open, point.close));
      const bodyHeight = Math.max(1.5, Math.abs(y(point.open) - y(point.close)));
      return `<g class="candle ${up ? "up" : "down"}"><line x1="${x(index)}" x2="${x(index)}" y1="${y(point.high)}" y2="${y(point.low)}"/><rect x="${x(index) - candleWidth / 2}" y="${bodyTop}" width="${candleWidth}" height="${bodyHeight}"/></g>`;
    }).join("");
  } else {
    const path = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(2)},${y(point.close).toFixed(2)}`).join(" ");
    marks = `<path class="analyzer-line" d="${path}"/>`;
  }
  const dates = [points[0], points[Math.floor(points.length / 2)], points.at(-1)];
  return `<div class="analyzer-stage">
    <svg class="analyzer-svg" viewBox="0 0 ${width} ${height}" tabindex="0" role="img" aria-label="${escapeHtml(data.symbol)} ${type === "candle" ? "candlestick" : "closing price"} chart from ${new Date(points[0].timestamp).toLocaleDateString()} to ${new Date(points.at(-1).timestamp).toLocaleDateString()}">
      ${gridValues.map(value => `<line class="analyzer-grid" x1="${pad.left}" x2="${width-pad.right}" y1="${y(value)}" y2="${y(value)}"/><text class="analyzer-axis" x="${pad.left-10}" y="${y(value)+4}" text-anchor="end">${money.format(value)}</text>`).join("")}
      ${marks}
      ${dates.map((point, index) => `<text class="analyzer-axis" x="${[pad.left,(width+pad.left-pad.right)/2,width-pad.right][index]}" y="${height-12}" text-anchor="${["start","middle","end"][index]}">${new Date(point.timestamp).toLocaleDateString([], {month:"short", day:"numeric", year:"2-digit"})}</text>`).join("")}
      <line class="analyzer-cursor" x1="0" x2="0" y1="${pad.top}" y2="${height-pad.bottom}" hidden/>
      <circle class="analyzer-point" cx="0" cy="0" r="4" hidden/>
      <rect class="analyzer-hit" x="${pad.left}" y="${pad.top}" width="${width-pad.left-pad.right}" height="${height-pad.top-pad.bottom}"/>
    </svg>
    <div class="analyzer-tooltip" hidden><strong></strong><span></span><small></small></div>
  </div>`;
}

function bindAnalyzerChart(container, data) {
  const svg = container.querySelector(".analyzer-svg");
  const tooltip = container.querySelector(".analyzer-tooltip");
  const cursor = container.querySelector(".analyzer-cursor");
  const point = container.querySelector(".analyzer-point");
  const source = data.history;
  const width = 900;
  const padLeft = 66;
  const padRight = 20;
  const lows = source.map(row => row.low);
  const highs = source.map(row => row.high);
  const min = Math.min(...lows) - (Math.max(...highs) - Math.min(...lows)) * .08;
  const max = Math.max(...highs) + (Math.max(...highs) - Math.min(...lows)) * .08;
  const show = index => {
    const safe = Math.max(0, Math.min(source.length - 1, index));
    const row = source[safe];
    const x = padLeft + safe / Math.max(source.length - 1, 1) * (width - padLeft - padRight);
    const y = 20 + (max - row.close) / Math.max(max - min, .01) * (330 - 20 - 42);
    cursor.setAttribute("x1", x); cursor.setAttribute("x2", x); cursor.hidden = false;
    point.setAttribute("cx", x); point.setAttribute("cy", y); point.hidden = false;
    tooltip.querySelector("strong").textContent = money.format(row.close);
    tooltip.querySelector("span").textContent = `O ${money.format(row.open)} · H ${money.format(row.high)} · L ${money.format(row.low)}`;
    tooltip.querySelector("small").textContent = `${new Date(row.timestamp).toLocaleDateString()} · Vol ${compactNumber(row.volume)}`;
    tooltip.style.left = `${x / width * 100}%`; tooltip.style.top = `${y / 330 * 100}%`; tooltip.hidden = false;
    svg.dataset.index = safe;
  };
  svg.addEventListener("pointermove", event => {
    const bounds = svg.getBoundingClientRect();
    const x = (event.clientX - bounds.left) / bounds.width * width;
    show(Math.round(Math.max(0, Math.min(1, (x - padLeft) / (width - padLeft - padRight))) * (source.length - 1)));
  });
  svg.addEventListener("pointerleave", () => { tooltip.hidden = true; cursor.hidden = true; point.hidden = true; });
  svg.addEventListener("keydown", event => {
    if (!["ArrowLeft","ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    show(Number(svg.dataset.index ?? source.length - 1) + (event.key === "ArrowRight" ? 1 : -1));
  });
}

function renderStockAnalysis(data) {
  const chartType = document.querySelector("#analyzer-chart-type").value;
  const positive = data.period_return >= 0;
  analyzerOutput.innerHTML = `
    <div class="analyzer-summary">
      <div><span>${escapeHtml(data.symbol)} · ${escapeHtml(data.currency)}</span><strong>${money.format(data.last_price)}</strong><small>As of ${new Date(data.as_of).toLocaleString([], {month:"short",day:"numeric",year:"numeric",hour:"numeric",minute:"2-digit"})}</small></div>
      <div class="${positive ? "positive" : "negative"}"><strong>${positive ? "+" : ""}${data.period_return.toFixed(2)}%</strong><span>period return</span></div>
    </div>
    <div class="analyzer-metrics">
      <div><span>Latest move</span><strong class="${data.change_pct >= 0 ? "positive" : "negative"}">${data.change_pct >= 0 ? "+" : ""}${data.change_pct.toFixed(2)}%</strong></div>
      <div><span>Period high</span><strong>${money.format(data.period_high)}</strong></div>
      <div><span>Period low</span><strong>${money.format(data.period_low)}</strong></div>
      <div><span>Realized volatility</span><strong>${data.volatility.toFixed(1)}%</strong></div>
      <div><span>Average volume</span><strong>${compactNumber(data.average_volume)}</strong></div>
    </div>
    ${analyzerChartMarkup(data, chartType)}
    <p class="analyzer-source">${escapeHtml(data.source)} · ${data.interval === "1wk" ? "Weekly" : "Daily"} OHLCV history · ${new Date(data.history[0].timestamp).toLocaleDateString()}–${new Date(data.history.at(-1).timestamp).toLocaleDateString()}</p>`;
  bindAnalyzerChart(analyzerOutput, data);
}

analyzerForm.addEventListener("submit", async event => {
  event.preventDefault();
  const symbol = document.querySelector("#analyzer-symbol").value.trim().toUpperCase();
  if (!/^[A-Z][A-Z0-9.-]{0,9}$/.test(symbol)) {
    analyzerOutput.innerHTML = `<div class="analyzer-empty">Enter a valid ticker symbol.</div>`;
    return;
  }
  const period = document.querySelector("#analyzer-period").value;
  const interval = document.querySelector("#analyzer-interval").value;
  document.querySelector("#analyzer-submit").disabled = true;
  analyzerOutput.innerHTML = `<div class="analyzer-empty">Loading validated OHLCV history for ${escapeHtml(symbol)}…</div>`;
  try {
    const response = await fetch(`/api/stock-analyzer?symbol=${encodeURIComponent(symbol)}&period=${encodeURIComponent(period)}&interval=${encodeURIComponent(interval)}`);
    if (!response.ok) {
      const error = await response.json().catch(() => ({}));
      throw new Error(error.detail || `HTTP ${response.status}`);
    }
    renderStockAnalysis(await response.json());
  } catch (error) {
    analyzerOutput.innerHTML = `<div class="analyzer-empty">Stock analysis unavailable: ${escapeHtml(error.message)}</div>`;
  } finally {
    document.querySelector("#analyzer-submit").disabled = false;
  }
});
document.querySelector("#analyzer-chart-type").addEventListener("change", () => {
  if (analyzerOutput.querySelector(".analyzer-svg")) analyzerForm.requestSubmit();
});

function addDebate(message) {
  const item = document.createElement("article");
  item.className = "message";
  item.dataset.stance = message.stance;
  item.innerHTML = `
    <div class="avatar">${escapeHtml(agentInitial[message.agent] || "A")}</div>
    <div><div class="message-head"><strong>${escapeHtml(message.agent)}</strong><span>${escapeHtml(message.symbol)}${message.round ? ` · R${message.round}` : ""}</span></div>
    <p>${escapeHtml(message.message)}</p></div>`;
  debateEl.appendChild(item);
  debateEl.scrollTop = debateEl.scrollHeight;
  eventCount.textContent = `${debateEl.children.length} events`;
}

function updateProgress(progress) {
  const percent = Math.max(0, Math.min(100, Number(progress.percent) || 0));
  analysisProgress.setAttribute("aria-valuenow", String(percent));
  analysisProgress.dataset.complete = String(percent === 100);
  progressStage.textContent = progress.stage || "Researching";
  progressPercent.textContent = `${percent}%`;
  progressFill.style.width = `${percent}%`;
}

function chartGeometry(points) {
  const width = 600;
  const height = 180;
  const pad = {top:16, right:14, bottom:28, left:54};
  const values = points.map(point => point.close);
  const rawMin = Math.min(...values);
  const rawMax = Math.max(...values);
  const margin = Math.max((rawMax - rawMin) * 0.12, rawMax * 0.005);
  const min = rawMin - margin;
  const max = rawMax + margin;
  const x = index => pad.left + (index / Math.max(points.length - 1, 1)) * (width - pad.left - pad.right);
  const y = value => pad.top + ((max - value) / Math.max(max - min, 0.01)) * (height - pad.top - pad.bottom);
  return {width, height, pad, min, max, x, y};
}

function renderPriceChart(container, trade, requestedRange = "3M") {
  const allPoints = trade.price_history || [];
  const points = requestedRange === "1M" ? allPoints.slice(-22) : allPoints;
  if (points.length < 2) {
    container.innerHTML = `<p class="chart-empty">Price history is unavailable for this security.</p>`;
    return;
  }
  const geometry = chartGeometry(points);
  const {width, height, pad, min, max, x, y} = geometry;
  const line = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(2)},${y(point.close).toFixed(2)}`).join(" ");
  const area = `${line} L${x(points.length - 1)},${height - pad.bottom} L${x(0)},${height - pad.bottom} Z`;
  const change = ((points.at(-1).close / points[0].close) - 1) * 100;
  const tone = change >= 0 ? "positive" : "negative";
  const startDate = new Date(points[0].timestamp);
  const endDate = new Date(points.at(-1).timestamp);
  const ticks = [max, (max + min) / 2, min];

  container.innerHTML = `
    <div class="chart-head">
      <div>
        <span class="chart-label">Price history</span>
        <strong class="${tone}">${change >= 0 ? "+" : ""}${change.toFixed(1)}%</strong>
        <small>${startDate.toLocaleDateString([], {month:"short", day:"numeric"})}–${endDate.toLocaleDateString([], {month:"short", day:"numeric"})}</small>
      </div>
      <div class="range-control" aria-label="Chart range">
        <button type="button" data-range="1M" aria-pressed="${requestedRange === "1M"}">1M</button>
        <button type="button" data-range="3M" aria-pressed="${requestedRange === "3M"}">3M</button>
      </div>
    </div>
    <div class="chart-stage">
      <svg class="price-chart" viewBox="0 0 ${width} ${height}" role="img" tabindex="0"
        aria-label="${escapeHtml(trade.symbol)} closing price chart from ${startDate.toLocaleDateString()} to ${endDate.toLocaleDateString()}">
        <defs><linearGradient id="fill-${escapeHtml(trade.symbol)}" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stop-color="#17805f" stop-opacity=".22"/><stop offset="100%" stop-color="#17805f" stop-opacity=".02"/></linearGradient></defs>
        ${ticks.map(value => `<line class="chart-grid" x1="${pad.left}" x2="${width - pad.right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis-label" x="${pad.left - 8}" y="${y(value) + 3}" text-anchor="end">${money.format(value)}</text>`).join("")}
        <path class="chart-area" d="${area}" fill="url(#fill-${escapeHtml(trade.symbol)})"/>
        <path class="chart-line" d="${line}"/>
        <line class="chart-cursor" x1="0" x2="0" y1="${pad.top}" y2="${height - pad.bottom}" hidden/>
        <circle class="chart-point" r="4" cx="0" cy="0" hidden/>
        <rect class="chart-hit" x="${pad.left}" y="${pad.top}" width="${width - pad.left - pad.right}" height="${height - pad.top - pad.bottom}"/>
      </svg>
      <div class="chart-tooltip" hidden><strong></strong><span></span></div>
    </div>
    <p class="chart-source">Daily closing prices · ${escapeHtml(trade.evidence?.[0]?.source || "Market data provider")}</p>`;

  const svg = container.querySelector(".price-chart");
  const tooltip = container.querySelector(".chart-tooltip");
  const cursor = container.querySelector(".chart-cursor");
  const point = container.querySelector(".chart-point");

  function showPoint(index) {
    const selected = points[Math.max(0, Math.min(points.length - 1, index))];
    const pointX = x(index);
    const pointY = y(selected.close);
    cursor.setAttribute("x1", pointX);
    cursor.setAttribute("x2", pointX);
    cursor.hidden = false;
    point.setAttribute("cx", pointX);
    point.setAttribute("cy", pointY);
    point.hidden = false;
    tooltip.querySelector("strong").textContent = money.format(selected.close);
    tooltip.querySelector("span").textContent = new Date(selected.timestamp).toLocaleDateString([], {month:"short", day:"numeric", year:"numeric"});
    tooltip.style.left = `${(pointX / width) * 100}%`;
    tooltip.style.top = `${(pointY / height) * 100}%`;
    tooltip.hidden = false;
    svg.dataset.activeIndex = String(index);
  }

  svg.addEventListener("pointermove", event => {
    const bounds = svg.getBoundingClientRect();
    const relativeX = ((event.clientX - bounds.left) / bounds.width) * width;
    const ratio = (relativeX - pad.left) / (width - pad.left - pad.right);
    showPoint(Math.round(Math.max(0, Math.min(1, ratio)) * (points.length - 1)));
  });
  svg.addEventListener("pointerleave", () => {
    cursor.hidden = true;
    point.hidden = true;
    tooltip.hidden = true;
  });
  svg.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const current = Number(svg.dataset.activeIndex ?? points.length - 1);
    showPoint(current + (event.key === "ArrowRight" ? 1 : -1));
  });
  container.querySelectorAll("[data-range]").forEach(button => {
    button.addEventListener("click", () => renderPriceChart(container, trade, button.dataset.range));
  });
}

function renderDebateChart(container, trade) {
  const points = trade.debate_scores || [];
  if (!points.length) {
    container.hidden = true;
    return;
  }
  const width = 600;
  const height = 180;
  const pad = {top:22, right:18, bottom:34, left:42};
  const x = index => pad.left + (index / Math.max(points.length - 1, 1)) * (width - pad.left - pad.right);
  const y = value => pad.top + ((100 - value) / 100) * (height - pad.top - pad.bottom);
  const bullLine = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(2)},${y(point.bull).toFixed(2)}`).join(" ");
  const bearLine = points.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(2)},${y(point.bear).toFixed(2)}`).join(" ");
  const latest = points.at(-1);

  container.innerHTML = `
    <div class="debate-chart-head">
      <div><span>Decision path</span><strong>Round-by-round evidence balance</strong></div>
      <div class="debate-legend"><span data-series="bull">Bull ${latest.bull.toFixed(0)}</span><span data-series="bear">Bear ${latest.bear.toFixed(0)}</span></div>
    </div>
    <div class="debate-chart-stage">
      <svg class="debate-chart" viewBox="0 0 ${width} ${height}" role="img" tabindex="0"
        aria-label="${escapeHtml(trade.symbol)} Bull and Bear evidence balance across ${points.length} rounds. Latest Bull ${latest.bull.toFixed(0)}, Bear ${latest.bear.toFixed(0)}.">
        ${[75, 50, 25].map(value => `<line class="debate-grid${value === 50 ? " midpoint" : ""}" x1="${pad.left}" x2="${width - pad.right}" y1="${y(value)}" y2="${y(value)}"/><text class="axis-label" x="${pad.left - 8}" y="${y(value) + 3}" text-anchor="end">${value}</text>`).join("")}
        <path class="debate-line bull-line" d="${bullLine}"/>
        <path class="debate-line bear-line" d="${bearLine}"/>
        ${points.map((point, index) => `<circle class="debate-node bull-node" cx="${x(index)}" cy="${y(point.bull)}" r="3" data-index="${index}"/><circle class="debate-node bear-node" cx="${x(index)}" cy="${y(point.bear)}" r="3" data-index="${index}"/>`).join("")}
        <rect class="debate-hit" x="${pad.left}" y="${pad.top}" width="${width - pad.left - pad.right}" height="${height - pad.top - pad.bottom}"/>
      </svg>
      <div class="debate-tooltip" hidden><strong></strong><span></span><small></small></div>
    </div>
    <p class="chart-source">Evidence balance (0–100) derived from return, breadth, trend, drawdown and volatility. It is not a probability or price forecast.</p>`;

  const svg = container.querySelector(".debate-chart");
  const tooltip = container.querySelector(".debate-tooltip");
  function showRound(index) {
    const safeIndex = Math.max(0, Math.min(points.length - 1, index));
    const point = points[safeIndex];
    tooltip.querySelector("strong").textContent = `Round ${point.round} · ${point.lens}`;
    tooltip.querySelector("span").textContent = `Bull ${point.bull.toFixed(1)} · Bear ${point.bear.toFixed(1)}`;
    tooltip.querySelector("small").textContent = `Net tilt ${point.net >= 0 ? "+" : ""}${point.net.toFixed(1)}`;
    tooltip.style.left = `${(x(safeIndex) / width) * 100}%`;
    tooltip.style.top = `${Math.max(7, (Math.min(y(point.bull), y(point.bear)) / height) * 100)}%`;
    tooltip.hidden = false;
    svg.dataset.activeIndex = String(safeIndex);
    svg.querySelectorAll(".debate-node").forEach(node => node.classList.toggle("active", Number(node.dataset.index) === safeIndex));
  }
  svg.addEventListener("pointermove", event => {
    const bounds = svg.getBoundingClientRect();
    const relativeX = ((event.clientX - bounds.left) / bounds.width) * width;
    const ratio = (relativeX - pad.left) / (width - pad.left - pad.right);
    showRound(Math.round(Math.max(0, Math.min(1, ratio)) * (points.length - 1)));
  });
  svg.addEventListener("pointerleave", () => {
    tooltip.hidden = true;
    svg.querySelectorAll(".debate-node").forEach(node => node.classList.remove("active"));
  });
  svg.addEventListener("keydown", event => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    event.preventDefault();
    const current = Number(svg.dataset.activeIndex ?? points.length - 1);
    showRound(current + (event.key === "ArrowRight" ? 1 : -1));
  });
}

function renderReport(report) {
  resultsEl.innerHTML = "";
  sourceBadge.textContent = report.source_status === "live" ? "Live data" : report.source_status;
  sourceBadge.dataset.status = report.source_status;
  runMeta.textContent = `${report.top_trades.length} ranked by conviction · ${new Date(report.generated_at).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}`;
  methodology.textContent = `${report.methodology} ${report.market_context}`;
  const system = document.querySelector(".system");
  if (system) {
    system.innerHTML = report.source_status === "unavailable"
      ? `<span class="pulse pulse-warn"></span> Market data unavailable`
      : `<span class="pulse"></span> Research systems operational`;
  }
  if (!report.top_trades.length) {
    resultsEl.innerHTML = `<div class="empty"><strong>No prediction issued</strong><p>Market data could not be validated. Try again shortly or verify the symbols.</p></div>`;
    return;
  }
  const hasMultiple = report.top_trades.length > 1;
  report.top_trades.forEach((trade, index) => {
    const card = document.createElement("article");
    card.className = "trade";
    card.dataset.rank = String(index + 1);
    const expanded = !hasMultiple || index === 0;
    card.innerHTML = `
      <div class="trade-top">
        <div><span class="rank" title="Conviction rank">#${index + 1}${index === 0 ? " · TOP" : ""}</span><h3>${escapeHtml(trade.symbol)}</h3>
          <span class="direction" data-direction="${trade.direction}">${escapeHtml(trade.direction)}</span></div>
        <div class="trade-actions">
          <div class="score"><strong>${trade.score > 0 ? "+" : ""}${trade.score.toFixed(1)}</strong><span>signal score</span></div>
          ${hasMultiple ? `<button class="trade-expand" type="button" aria-expanded="${expanded}">${expanded ? "Condense" : "View analysis"}</button>` : ""}
        </div>
      </div>
      <div class="metrics">
        <div><span>Last close</span><strong>${trade.last_price == null ? "—" : money.format(trade.last_price)}</strong></div>
        <div><span>Daily move</span><strong class="${trade.change_pct >= 0 ? "positive" : "negative"}">${trade.change_pct == null ? "—" : `${trade.change_pct > 0 ? "+" : ""}${trade.change_pct.toFixed(2)}%`}</strong></div>
        <div><span>Confidence</span><strong>${Math.round(trade.confidence * 100)}%</strong></div>
      </div>
      <div class="trade-body" ${expanded ? "" : "hidden"}>
        <p class="thesis">${escapeHtml(trade.thesis)}</p>
        <div class="confidence" aria-label="${Math.round(trade.confidence * 100)} percent confidence"><span style="width:${trade.confidence * 100}%"></span></div>
        <div class="debate-chart-widget" data-tour="debate-chart"></div>
        <div class="chart-widget" data-tour="chart"></div>
        <details><summary>Evidence & risks</summary>
          <div class="evidence">${trade.evidence.map(e => `<p><strong>${escapeHtml(e.label)}</strong><span>${escapeHtml(e.value)}</span><small>${escapeHtml(e.source)} · ${new Date(e.as_of).toLocaleDateString()}</small></p>`).join("")}</div>
          <ul>${trade.key_risks.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
        </details>
      </div>`;
    resultsEl.appendChild(card);
    renderDebateChart(card.querySelector(".debate-chart-widget"), trade);
    renderPriceChart(card.querySelector(".chart-widget"), trade);
    card.querySelector(".trade-expand")?.addEventListener("click", event => {
      const body = card.querySelector(".trade-body");
      const shouldExpand = body.hidden;
      body.hidden = !shouldExpand;
      event.currentTarget.setAttribute("aria-expanded", String(shouldExpand));
      event.currentTarget.textContent = shouldExpand ? "Condense" : "View analysis";
    });
  });
}

async function consumeSSE(response) {
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new Error(Array.isArray(body.detail) ? body.detail[0]?.msg : body.detail || `HTTP ${response.status}`);
  }
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  while (true) {
    const {value, done} = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, {stream:true});
    const packets = buffer.split("\n\n");
    buffer = packets.pop();
    for (const packet of packets) {
      const event = packet.match(/^event: (.+)$/m)?.[1];
      const data = packet.match(/^data: (.+)$/m)?.[1];
      if (!data) continue;
      const payload = JSON.parse(data);
      if (event === "progress") updateProgress(payload);
      if (event === "debate") addDebate(payload);
      if (event === "report") renderReport(payload);
    }
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const tickers = parseTickers(document.querySelector("#tickers").value);
  const rounds = Number(document.querySelector("#rounds").value);
  if (!tickers.length || tickers.length > 5 || tickers.some(ticker => !/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker))) {
    statusEl.textContent = "Enter 1–5 valid ticker symbols.";
    statusEl.dataset.tone = "error";
    return;
  }
  if (!Number.isInteger(rounds) || rounds < 1 || rounds > 30) {
    statusEl.textContent = "Choose between 1 and 30 whole research rounds.";
    statusEl.dataset.tone = "error";
    return;
  }
  delete statusEl.dataset.tone;
  loadMarketPulse(tickers);
  runButton.disabled = true;
  workspace.hidden = false;
  debateEl.innerHTML = "";
  resultsEl.innerHTML = `<div class="loader"><i></i><span>Agents are gathering and challenging evidence…</span></div>`;
  eventCount.textContent = "0 events";
  sourceBadge.textContent = "Running";
  delete sourceBadge.dataset.status;
  updateProgress({percent:0, stage:"Opening the research desk"});
  statusEl.textContent = "Desk in session. Follow the live room below.";
  workspace.scrollIntoView({behavior:"smooth", block:"start"});
  try {
    const response = await fetch("/api/analyze/stream", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({tickers, debate_rounds:rounds}),
    });
    await consumeSSE(response);
    statusEl.textContent = "Research run complete.";
  } catch (error) {
    statusEl.textContent = `Desk error: ${error.message}`;
    statusEl.dataset.tone = "error";
    resultsEl.innerHTML = `<div class="empty"><strong>Analysis interrupted</strong><p>${escapeHtml(error.message)}</p></div>`;
  } finally {
    runButton.disabled = false;
  }
});

const tour = document.querySelector("#tour");
const tourFocus = document.querySelector("#tour-focus");
const tourCard = document.querySelector("#tour-card");
const tourTitle = document.querySelector("#tour-title");
const tourCopy = document.querySelector("#tour-copy");
const tourKicker = document.querySelector("#tour-kicker");
const tourProgress = document.querySelector("#tour-progress");
const tourBack = document.querySelector("#tour-back");
const tourNext = document.querySelector("#tour-next");
let tourSteps = [];
let tourIndex = 0;
let returnFocus = null;

const allTourSteps = [
  {selector:"#analyze-form", kicker:"Start here", title:"Choose what to research", copy:"Enter up to five ticker symbols and choose 1–30 rounds. Each round tests a different time window and risk lens before the stocks are ranked."},
  {selector:".pulse-viewport", kicker:"Scan the market", title:"Continuous market pulse", copy:"The tape moves continuously and enlarges the security nearest the center. Drag or scroll it manually; after five idle seconds it accelerates smoothly back to cruising speed. Select any card for detail."},
  {selector:".stock-analyzer", kicker:"Inspect the history", title:"Stock Analyzer", copy:"Enter a ticker and choose the period, interval, and line or candlestick view. The chart exposes exact OHLCV observations, performance, volatility, range, and source dates."},
  {selector:".news-grid", kicker:"Track new information", title:"Latest market coverage", copy:"This separate feed shows timestamped headlines and publishers. Cached results and an independent RSS fallback keep coverage available when one news endpoint is offline."},
  {selector:".process-card", kicker:"Follow the reasoning", title:"Live agent room", copy:"This feed shows each step in order. Bull looks for upside, Bear challenges it, Risk applies safeguards, and the Portfolio Manager makes the final call."},
  {selector:".output-card", kicker:"Read the decision", title:"PM scorecard", copy:"This is the concise outcome. Direction shows the current signal, while the score measures strength—not a guaranteed return."},
  {selector:".metrics", kicker:"Understand the numbers", title:"Three useful reference points", copy:"Last close is the latest validated price. Daily move is the most recent change. Confidence is deliberately reduced when volatility or evidence risk is high."},
  {selector:"[data-tour='debate-chart']", kicker:"Quantify the discussion", title:"Bull versus Bear decision path", copy:"Each line scores the evidence used in that round from 0 to 100. Hover or use the arrow keys to see how momentum, drawdown and volatility shifted the balance. This is evidence strength, not a return probability."},
  {selector:"[data-tour='chart']", kicker:"Explore the evidence", title:"Interactive price history", copy:"Switch between one and three months. Hover or use the arrow keys to inspect exact daily closing prices. The source shown below matches the analysis data."},
  {selector:".trade details", kicker:"Challenge the result", title:"Evidence and risks", copy:"Open this section to see source dates and the limitations that could weaken or invalidate the signal."},
  {selector:".method", kicker:"Know the boundaries", title:"Methodology and limitations", copy:"This explains how the score is calculated and what the screen does not know. Northstar is research support, not investment advice."},
];

function availableTourSteps() {
  return allTourSteps.filter(step => {
    const target = document.querySelector(step.selector);
    return target && target.getClientRects().length;
  });
}

function positionTour() {
  const step = tourSteps[tourIndex];
  const target = document.querySelector(step.selector);
  if (!target) return;
  target.scrollIntoView({behavior:"auto", block:"center"});
  tourCard.style.inset = "auto";
  tourCard.style.left = "50%";
  tourCard.style.top = "50%";
  tourCard.style.right = "auto";
  tourCard.style.bottom = "auto";
  tourCard.style.transform = "translate(-50%, -50%)";
  requestAnimationFrame(() => {
    const rect = target.getBoundingClientRect();
    const gap = 8;
    tourFocus.style.left = `${Math.max(gap, rect.left - gap)}px`;
    tourFocus.style.top = `${Math.max(gap, rect.top - gap)}px`;
    tourFocus.style.width = `${Math.min(window.innerWidth - gap * 2, rect.width + gap * 2)}px`;
    tourFocus.style.height = `${Math.min(window.innerHeight - gap * 2, rect.height + gap * 2)}px`;
  });
}

function showTourStep() {
  const step = tourSteps[tourIndex];
  tourKicker.textContent = step.kicker;
  tourTitle.textContent = step.title;
  tourCopy.textContent = step.copy;
  tourProgress.textContent = `${tourIndex + 1} of ${tourSteps.length}`;
  tourBack.disabled = tourIndex === 0;
  tourNext.innerHTML = tourIndex === tourSteps.length - 1 ? "Finish" : `Next <span aria-hidden="true">→</span>`;
  positionTour();
  tourCard.focus({preventScroll:true});
}

function openTour() {
  tourSteps = availableTourSteps();
  if (!tourSteps.length) return;
  returnFocus = document.activeElement;
  tourIndex = 0;
  tour.hidden = false;
  document.body.classList.add("tour-open");
  showTourStep();
}

function closeTour() {
  tour.hidden = true;
  document.body.classList.remove("tour-open");
  returnFocus?.focus();
}

document.querySelector("#help-button").addEventListener("click", openTour);
document.querySelector("#tour-close").addEventListener("click", closeTour);
tourBack.addEventListener("click", () => {
  if (tourIndex > 0) {
    tourIndex -= 1;
    showTourStep();
  }
});
tourNext.addEventListener("click", () => {
  if (tourIndex === tourSteps.length - 1) closeTour();
  else {
    tourIndex += 1;
    showTourStep();
  }
});
document.addEventListener("keydown", event => {
  if (tour.hidden) return;
  if (event.key === "Escape") closeTour();
  if (event.key === "ArrowRight") tourNext.click();
  if (event.key === "ArrowLeft" && !tourBack.disabled) tourBack.click();
  if (event.key === "Tab") {
    const controls = [...tourCard.querySelectorAll("button:not(:disabled)")];
    const first = controls[0];
    const last = controls.at(-1);
    if (event.shiftKey && document.activeElement === first) {
      event.preventDefault();
      last.focus();
    } else if (!event.shiftKey && document.activeElement === last) {
      event.preventDefault();
      first.focus();
    }
  }
});
window.addEventListener("resize", () => {
  if (!tour.hidden) positionTour();
});
