const grid = document.querySelector("#all-news-grid");
const statusEl = document.querySelector("#all-news-status");
const escapeHtml = value => String(value ?? "").replace(/[&<>"']/g, character => ({
  "&":"&amp;", "<":"&lt;", ">":"&gt;", '"':"&quot;", "'":"&#039;"
})[character]);
const safeUrl = value => {
  try {
    const url = new URL(value);
    return ["http:", "https:"].includes(url.protocol) ? url.href : "#";
  } catch (_) {
    return "#";
  }
};

function card(item, index) {
  const visual = item.image_url ? `<div class="news-visual"><img src="${escapeHtml(safeUrl(item.image_url))}" alt="" loading="lazy"><span class="news-visual-label">${escapeHtml(item.publisher)}</span></div>` : "";
  return `<a class="news-card${index === 0 ? " lead-news" : ""}${visual ? "" : " no-image"}" href="${escapeHtml(safeUrl(item.url))}" target="_blank" rel="noopener noreferrer">
    ${visual}
    <div class="news-body">
      <span class="news-meta">${escapeHtml(item.publisher)} · ${new Date(item.published_at).toLocaleString([], {month:"short",day:"numeric",hour:"numeric",minute:"2-digit"})}</span>
      <strong>${escapeHtml(item.title)}</strong>
      <span class="news-link">Read original article ↗</span>
    </div>
  </a>`;
}

fetch("/api/market-pulse")
  .then(response => {
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
  })
  .then(payload => {
    const news = payload.news || [];
    grid.innerHTML = news.length ? news.map(card).join("") : `<div class="news-loading">No current headlines are available.</div>`;
    grid.querySelectorAll(".news-visual img").forEach(image => image.addEventListener("error", () => {
      const article = image.closest(".news-card");
      image.parentElement.remove();
      article.classList.add("no-image");
    }, {once:true}));
    grid.querySelectorAll(".news-visual img").forEach(image => {
      const applyPreset = () => {
        const article = image.closest(".news-card");
        article.classList.toggle("portrait-image", image.naturalHeight > image.naturalWidth * 1.08);
        article.classList.toggle("landscape-image", image.naturalWidth >= image.naturalHeight * 1.08);
      };
      image.complete ? applyPreset() : image.addEventListener("load", applyPreset, {once:true});
    });
    statusEl.textContent = `${news.length} attributed articles · Updated ${new Date(payload.generated_at).toLocaleTimeString([], {hour:"numeric",minute:"2-digit"})}`;
  })
  .catch(() => {
    grid.innerHTML = `<div class="news-loading">Market news is temporarily unavailable. Please try again shortly.</div>`;
  });
