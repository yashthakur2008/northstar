const themeToggle = document.querySelector("#theme-toggle");
const authLink = document.querySelector("[data-auth-link]");

function applySiteTheme(theme, persist = true) {
  const dark = theme === "dark";
  document.documentElement.dataset.theme = dark ? "dark" : "light";
  document.documentElement.style.colorScheme = dark ? "dark" : "light";
  if (themeToggle) {
    themeToggle.setAttribute("aria-pressed", String(dark));
    themeToggle.setAttribute("aria-label", `Switch to ${dark ? "light" : "dark"} mode`);
    themeToggle.querySelector(".theme-icon").textContent = dark ? "☀" : "☾";
    themeToggle.querySelector(".theme-label").textContent = dark ? "Light" : "Dark";
  }
  if (persist) {
    try {
      localStorage.setItem("northstar-theme", dark ? "dark" : "light");
    } catch (_) {}
  }
}

applySiteTheme(document.documentElement.dataset.theme || "light", false);
themeToggle?.addEventListener("click", () => {
  applySiteTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});

if (authLink) {
  fetch("/api/auth/me", { credentials: "same-origin" })
    .then((response) => response.ok ? response.json() : null)
    .then((session) => {
      if (session?.authenticated) {
        authLink.textContent = session.user.display_name;
        authLink.classList.add("is-authenticated");
        authLink.setAttribute("aria-label", `Open account for ${session.user.display_name}`);
      }
    })
    .catch(() => {});
}
