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

const agentInitial = {"Market Data":"M","Technical":"T","Bull":"B+","Bear":"B−","Risk":"R","Portfolio Manager":"PM"};
const money = new Intl.NumberFormat("en-US", {style:"currency", currency:"USD", maximumFractionDigits:2});

function parseTickers(value) {
  return [...new Set(value.split(",").map(value => value.trim().toUpperCase()).filter(Boolean))];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, character => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[character]));
}

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

function renderReport(report) {
  resultsEl.innerHTML = "";
  sourceBadge.textContent = report.source_status === "live" ? "Live data" : report.source_status;
  sourceBadge.dataset.status = report.source_status;
  runMeta.textContent = `${report.top_trades.length} scored · ${new Date(report.generated_at).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}`;
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
  report.top_trades.forEach((trade, index) => {
    const card = document.createElement("article");
    card.className = "trade";
    card.innerHTML = `
      <div class="trade-top">
        <div><span class="rank">0${index + 1}</span><h3>${escapeHtml(trade.symbol)}</h3>
          <span class="direction" data-direction="${trade.direction}">${escapeHtml(trade.direction)}</span></div>
        <div class="score"><strong>${trade.score > 0 ? "+" : ""}${trade.score.toFixed(1)}</strong><span>signal score</span></div>
      </div>
      <div class="metrics">
        <div><span>Last close</span><strong>${trade.last_price == null ? "—" : money.format(trade.last_price)}</strong></div>
        <div><span>Daily move</span><strong class="${trade.change_pct >= 0 ? "positive" : "negative"}">${trade.change_pct == null ? "—" : `${trade.change_pct > 0 ? "+" : ""}${trade.change_pct.toFixed(2)}%`}</strong></div>
        <div><span>Confidence</span><strong>${Math.round(trade.confidence * 100)}%</strong></div>
      </div>
      <p class="thesis">${escapeHtml(trade.thesis)}</p>
      <div class="confidence" aria-label="${Math.round(trade.confidence * 100)} percent confidence"><span style="width:${trade.confidence * 100}%"></span></div>
      <div class="chart-widget" data-tour="chart"></div>
      <details><summary>Evidence & risks</summary>
        <div class="evidence">${trade.evidence.map(e => `<p><strong>${escapeHtml(e.label)}</strong><span>${escapeHtml(e.value)}</span><small>${escapeHtml(e.source)} · ${new Date(e.as_of).toLocaleDateString()}</small></p>`).join("")}</div>
        <ul>${trade.key_risks.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
      </details>`;
    resultsEl.appendChild(card);
    renderPriceChart(card.querySelector(".chart-widget"), trade);
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
      if (event === "debate") addDebate(payload);
      if (event === "report") renderReport(payload);
    }
  }
}

form.addEventListener("submit", async event => {
  event.preventDefault();
  const tickers = parseTickers(document.querySelector("#tickers").value);
  if (!tickers.length || tickers.length > 5 || tickers.some(ticker => !/^[A-Z][A-Z0-9.-]{0,9}$/.test(ticker))) {
    statusEl.textContent = "Enter 1–5 valid ticker symbols.";
    statusEl.dataset.tone = "error";
    return;
  }
  delete statusEl.dataset.tone;
  runButton.disabled = true;
  workspace.hidden = false;
  debateEl.innerHTML = "";
  resultsEl.innerHTML = `<div class="loader"><i></i><span>Agents are gathering and challenging evidence…</span></div>`;
  eventCount.textContent = "0 events";
  sourceBadge.textContent = "Running";
  delete sourceBadge.dataset.status;
  statusEl.textContent = "Desk in session. Follow the live room below.";
  workspace.scrollIntoView({behavior:"smooth", block:"start"});
  try {
    const response = await fetch("/api/analyze/stream", {
      method:"POST",
      headers:{"Content-Type":"application/json"},
      body:JSON.stringify({tickers, debate_rounds:Number(document.querySelector("#rounds").value)}),
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
  {selector:"#analyze-form", kicker:"Start here", title:"Choose what to research", copy:"Enter up to five ticker symbols. Debate depth controls how many times the Bull and Bear challenge each other."},
  {selector:".process-card", kicker:"Follow the reasoning", title:"Live agent room", copy:"This feed shows each step in order. Bull looks for upside, Bear challenges it, Risk applies safeguards, and the Portfolio Manager makes the final call."},
  {selector:".output-card", kicker:"Read the decision", title:"PM scorecard", copy:"This is the concise outcome. Direction shows the current signal, while the score measures strength—not a guaranteed return."},
  {selector:".metrics", kicker:"Understand the numbers", title:"Three useful reference points", copy:"Last close is the latest validated price. Daily move is the most recent change. Confidence is deliberately reduced when volatility or evidence risk is high."},
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
  target.scrollIntoView({behavior:"smooth", block:"center"});
  requestAnimationFrame(() => {
    const rect = target.getBoundingClientRect();
    const gap = 8;
    tourFocus.style.left = `${Math.max(gap, rect.left - gap)}px`;
    tourFocus.style.top = `${Math.max(gap, rect.top - gap)}px`;
    tourFocus.style.width = `${Math.min(window.innerWidth - gap * 2, rect.width + gap * 2)}px`;
    tourFocus.style.height = `${Math.min(window.innerHeight - gap * 2, rect.height + gap * 2)}px`;
    const cardWidth = Math.min(360, window.innerWidth - 32);
    const preferRight = rect.right + cardWidth + 24 < window.innerWidth;
    const left = preferRight ? rect.right + 18 : Math.max(16, Math.min(rect.left, window.innerWidth - cardWidth - 16));
    const below = rect.bottom + 260 < window.innerHeight;
    const top = below ? rect.bottom + 18 : Math.max(16, Math.min(rect.top - 250, window.innerHeight - 250));
    tourCard.style.left = `${left}px`;
    tourCard.style.top = `${top}px`;
    tourCard.style.width = `${cardWidth}px`;
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
