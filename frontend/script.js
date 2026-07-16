const form = document.getElementById("analyze-form");
const statusEl = document.getElementById("status");
const resultsEl = document.getElementById("results");
const submitBtn = form.querySelector(".stamp-btn");

const DIRECTION_LABEL = {
  long: "Long",
  short: "Short",
  options_spread: "Spread",
};

function parseTickers(raw) {
  return raw
    .split(",")
    .map((t) => t.trim().toUpperCase())
    .filter(Boolean);
}

function setStatus(message, tone) {
  statusEl.textContent = message;
  if (tone) {
    statusEl.dataset.tone = tone;
  } else {
    delete statusEl.dataset.tone;
  }
}

function renderReport(report) {
  resultsEl.innerHTML = "";

  if (report.is_mocked) {
    const flag = document.createElement("span");
    flag.className = "mock-flag";
    flag.textContent = "Mock data — Phase 1 scaffold";
    resultsEl.appendChild(flag);
  }

  const context = document.createElement("p");
  context.className = "context-note";
  context.textContent = report.market_context;
  resultsEl.appendChild(context);

  report.top_trades.forEach((trade, index) => {
    resultsEl.appendChild(renderTicket(trade, index));
  });
}

function renderTicket(trade, index) {
  const ticket = document.createElement("article");
  ticket.className = "ticket";

  const stamp = document.createElement("span");
  stamp.className = "stamp";
  stamp.dataset.direction = trade.direction;
  stamp.textContent = DIRECTION_LABEL[trade.direction] || trade.direction;
  ticket.appendChild(stamp);

  const head = document.createElement("div");
  head.className = "ticket-head";
  head.innerHTML = `
    <span class="ticket-symbol">${trade.symbol}</span>
    <span class="ticket-rank">Pick #${index + 1}</span>
  `;
  ticket.appendChild(head);

  const confidence = document.createElement("div");
  confidence.className = "confidence";
  const pct = Math.round(trade.confidence * 100);
  confidence.innerHTML = `
    <div class="confidence-label">
      <span>Confidence</span><span>${pct}%</span>
    </div>
    <div class="confidence-track">
      <div class="confidence-fill" style="width: ${pct}%"></div>
    </div>
  `;
  ticket.appendChild(confidence);

  const thesis = document.createElement("p");
  thesis.className = "thesis";
  thesis.textContent = trade.thesis;
  ticket.appendChild(thesis);

  const agentRow = document.createElement("div");
  agentRow.className = "agent-row";
  trade.supporting_agents.forEach((a) => agentRow.appendChild(renderTag(a, "supporting")));
  trade.dissenting_agents.forEach((a) => agentRow.appendChild(renderTag(a, "dissenting")));
  ticket.appendChild(agentRow);

  if (trade.key_risks?.length) {
    const risks = document.createElement("ul");
    risks.className = "risks";
    trade.key_risks.forEach((r) => {
      const li = document.createElement("li");
      li.textContent = r;
      risks.appendChild(li);
    });
    ticket.appendChild(risks);
  }

  return ticket;
}

function renderTag(label, stance) {
  const tag = document.createElement("span");
  tag.className = "tag";
  tag.dataset.stance = stance;
  tag.textContent = label;
  return tag;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();

  const tickers = parseTickers(document.getElementById("tickers").value);
  const rounds = Number(document.getElementById("rounds").value) || 2;

  if (tickers.length === 0) {
    setStatus("Enter at least one ticker.", "error");
    return;
  }
  if (tickers.length > 5) {
    setStatus("Enter at most 5 tickers.", "error");
    return;
  }

  submitBtn.disabled = true;
  resultsEl.innerHTML = "";
  setStatus("— running the desk (this can take a moment on a cold start) —");

  try {
    const response = await fetch("/api/analyze", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ tickers, debate_rounds: rounds }),
    });

    if (!response.ok) {
      const body = await response.json().catch(() => null);
      throw new Error(body?.detail ? JSON.stringify(body.detail) : `Request failed (${response.status})`);
    }

    const report = await response.json();
    renderReport(report);
    setStatus(`Desk closed at ${new Date(report.generated_at).toLocaleTimeString()}.`);
  } catch (err) {
    setStatus(`— desk offline: ${err.message} —`, "error");
  } finally {
    submitBtn.disabled = false;
  }
});
