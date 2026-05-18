async function postAction(url, button) {
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "Working...";
  try {
    const response = await fetch(url, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Request failed");
    alert(payload.message + (payload.detail ? "\n" + JSON.stringify(payload.detail, null, 2) : ""));
    if (url.includes("run-parser") || url.includes("run-sample")) window.location.reload();
  } catch (error) {
    alert(error.message);
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

document.querySelectorAll("[data-action]").forEach((button) => {
  button.addEventListener("click", () => postAction(button.dataset.action, button));
});

document.addEventListener("DOMContentLoaded", () => {
  const form = document.getElementById("settings-form");
  const dashboardBtn = document.getElementById("settings-dashboard-btn");
  if (!form || !dashboardBtn) return;

  const serialize = (targetForm) => {
    const data = [...new FormData(targetForm).entries()];
    return data.sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `${key}=${encodeURIComponent(value)}`).join("&");
  };

  const initialState = serialize(form);
  const isDirty = () => serialize(form) !== initialState;

  dashboardBtn.addEventListener("click", (event) => {
    if (!isDirty()) return;
    event.preventDefault();
    const saveFirst = window.confirm(
      "You have unsaved settings changes. OK to save and go back to Dashboard, or Cancel to discard changes and go back."
    );
    if (saveFirst) {
      form.submit();
    } else {
      window.location.href = "/dashboard";
    }
  });
});
