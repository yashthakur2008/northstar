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

function parseTickers(value) {
  return [...new Set(value.split(",").map(v => v.trim().toUpperCase()).filter(Boolean))];
}

function escapeHtml(value) {
  return String(value).replace(/[&<>"']/g, char => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[char]));
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

function renderReport(report) {
  resultsEl.innerHTML = "";
  sourceBadge.textContent = report.source_status === "live" ? "Live data" : report.source_status;
  sourceBadge.dataset.status = report.source_status;
  runMeta.textContent = `${report.top_trades.length} scored · ${new Date(report.generated_at).toLocaleTimeString([], {hour:"2-digit", minute:"2-digit"})}`;
  methodology.textContent = `${report.methodology} ${report.market_context}`;

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
        <div><span>Last close</span><strong>${trade.last_price == null ? "—" : `$${trade.last_price.toLocaleString()}`}</strong></div>
        <div><span>Daily move</span><strong class="${trade.change_pct >= 0 ? "positive" : "negative"}">${trade.change_pct == null ? "—" : `${trade.change_pct > 0 ? "+" : ""}${trade.change_pct.toFixed(2)}%`}</strong></div>
        <div><span>Confidence</span><strong>${Math.round(trade.confidence * 100)}%</strong></div>
      </div>
      <p class="thesis">${escapeHtml(trade.thesis)}</p>
      <div class="confidence"><span style="width:${trade.confidence * 100}%"></span></div>
      <details><summary>Evidence & risks</summary>
        <div class="evidence">${trade.evidence.map(e => `<p><strong>${escapeHtml(e.label)}</strong><span>${escapeHtml(e.value)}</span><small>${escapeHtml(e.source)} · ${new Date(e.as_of).toLocaleDateString()}</small></p>`).join("")}</div>
        <ul>${trade.key_risks.map(r => `<li>${escapeHtml(r)}</li>`).join("")}</ul>
      </details>`;
    resultsEl.appendChild(card);
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
    buffer += decoder.decode(value, {stream: true});
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
  if (!tickers.length || tickers.length > 5 || tickers.some(t => !/^[A-Z][A-Z0-9.-]{0,9}$/.test(t))) {
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
      method: "POST", headers: {"Content-Type":"application/json"},
      body: JSON.stringify({tickers, debate_rounds:Number(document.querySelector("#rounds").value)})
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
