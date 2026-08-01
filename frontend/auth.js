const authTabs = [...document.querySelectorAll("[data-auth-tab]")];
const authForms = [...document.querySelectorAll("[data-auth-form]")];
const accountPanel = document.querySelector("#account-panel");
const authGateway = document.querySelector("#auth-gateway");
const authStatus = document.querySelector("#auth-status");
const accountName = document.querySelector("#account-name");
const accountEmail = document.querySelector("#account-email");
const logoutButton = document.querySelector("#logout-button");
const oauthButtons = [...document.querySelectorAll("[data-oauth]")];

function showStatus(message, tone = "") {
  authStatus.textContent = message;
  authStatus.dataset.tone = tone;
}

function selectTab(name) {
  authTabs.forEach((tab) => {
    const selected = tab.dataset.authTab === name;
    tab.setAttribute("aria-selected", String(selected));
  });
  authForms.forEach((form) => {
    form.hidden = form.dataset.authForm !== name;
  });
  showStatus("");
}

function showAccount(user) {
  authGateway.hidden = true;
  accountPanel.hidden = false;
  accountName.textContent = user.display_name;
  accountEmail.textContent = user.email;
}

function showGateway() {
  accountPanel.hidden = true;
  authGateway.hidden = false;
  selectTab("login");
}

async function authRequest(path, payload) {
  const response = await fetch(path, {
    method: "POST",
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(typeof data.detail === "string" ? data.detail : "We could not complete that request.");
  }
  return data;
}

authTabs.forEach((tab) => tab.addEventListener("click", () => selectTab(tab.dataset.authTab)));

authForms.forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const submit = form.querySelector("button[type=submit]");
    const values = Object.fromEntries(new FormData(form));
    submit.disabled = true;
    showStatus(form.dataset.authForm === "login" ? "Signing you in…" : "Creating your account…");
    try {
      const result = await authRequest(
        form.dataset.authForm === "login" ? "/api/auth/login" : "/api/auth/register",
        values,
      );
      showAccount(result.user);
      const next = new URLSearchParams(location.search).get("next");
      if (next?.startsWith("/") && !next.startsWith("//")) {
        location.assign(next);
      }
    } catch (error) {
      showStatus(error.message, "error");
    } finally {
      submit.disabled = false;
    }
  });
});

logoutButton.addEventListener("click", async () => {
  logoutButton.disabled = true;
  await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" }).catch(() => {});
  logoutButton.disabled = false;
  showGateway();
  showStatus("You have been signed out.");
});

fetch("/api/auth/me", { credentials: "same-origin" })
  .then((response) => response.json())
  .then((session) => session.authenticated ? showAccount(session.user) : showGateway())
  .catch(() => {
    showGateway();
    showStatus("Account services are temporarily unavailable.", "error");
  });

const query = new URLSearchParams(location.search);
const oauthError = query.get("oauth_error");
if (oauthError) {
  showStatus(oauthError.includes("not_configured") ? "This sign-in provider has not been configured yet." : "External sign-in could not be completed. Please try again.", "error");
}
fetch("/api/auth/providers")
  .then(response => response.json())
  .then(providers => oauthButtons.forEach(button => {
    const available = Boolean(providers[button.dataset.oauth]);
    button.classList.toggle("is-unavailable", !available);
    button.setAttribute("aria-disabled", String(!available));
    if (!available) button.title = `${button.dataset.oauth === "google" ? "Google" : "GitHub"} sign-in requires server credentials`;
  }))
  .catch(() => oauthButtons.forEach(button => button.classList.add("is-unavailable")));
