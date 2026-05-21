function showGlobalToast(message, tone = "success") {
  const stack = document.querySelector(".toast-stack");
  if (!stack) {
    window.alert(message);
    return;
  }
  const toast = document.createElement("div");
  toast.className = `toast toast-${tone}`;
  toast.textContent = message;
  stack.appendChild(toast);
  window.setTimeout(() => toast.classList.add("show"), 20);
  window.setTimeout(() => {
    toast.classList.remove("show");
    window.setTimeout(() => toast.remove(), 180);
  }, 3600);
}

async function postAction(url, button) {
  const oldText = button.textContent;
  button.disabled = true;
  button.textContent = "Working...";
  try {
    const response = await fetch(url, { method: "POST" });
    const payload = await response.json();
    if (!response.ok) throw new Error(payload.detail || "Request failed");
    showGlobalToast(payload.message + (payload.detail ? " " + JSON.stringify(payload.detail) : ""));
    if (url.includes("run-parser") || url.includes("run-sample")) window.location.reload();
  } catch (error) {
    showGlobalToast(error.message, "warn");
  } finally {
    button.disabled = false;
    button.textContent = oldText;
  }
}

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => postAction(button.dataset.action, button));
  });

document.querySelectorAll(".range-custom").forEach((form) => {
  const startInput = form.querySelector('input[name="start"]');
  const endInput = form.querySelector('input[name="end"]');
  const trigger = form.querySelector(".range-custom-trigger");
  const openPicker = (input) => {
    if (!input) return;
    if (typeof input.showPicker === "function") {
      input.showPicker();
    } else {
      input.focus();
      input.click();
    }
  };
  trigger?.addEventListener("click", () => {
    form.dataset.pickingRange = "start";
    openPicker(startInput);
  });
  startInput?.addEventListener("change", () => {
    form.dataset.pickingRange = "end";
    window.setTimeout(() => openPicker(endInput), 120);
  });
  endInput?.addEventListener("change", () => {
    const start = startInput?.value;
    const end = endInput?.value;
    if (start && end) {
      form.classList.add("range-complete");
      form.requestSubmit();
    }
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const showToast = showGlobalToast;
  const applyTheme = (theme) => {
    const dark = theme === "dark";
    document.documentElement.dataset.theme = dark ? "dark" : "";
    if (!dark) delete document.documentElement.dataset.theme;
    document.querySelectorAll(".theme-toggle").forEach((button) => {
      button.classList.toggle("is-dark", dark);
      button.setAttribute("aria-label", dark ? "Switch to light mode" : "Switch to dark mode");
      button.title = dark ? "Switch to light mode" : "Switch to dark mode";
      button.setAttribute("aria-pressed", dark.toString());
    });
  };
  let savedTheme = "";
  try {
    savedTheme = localStorage.getItem("dashboard-theme") || "";
  } catch {
    savedTheme = "";
  }
  applyTheme(savedTheme);
  document.querySelectorAll(".theme-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const nextTheme = document.documentElement.dataset.theme === "dark" ? "light" : "dark";
      try {
        if (nextTheme === "dark") {
          localStorage.setItem("dashboard-theme", "dark");
        } else {
          localStorage.removeItem("dashboard-theme");
        }
      } catch {}
      applyTheme(nextTheme);
    });
  });

  const refreshOverflowTitles = () => {
    const skipTags = new Set(["SCRIPT", "STYLE", "SVG", "PATH", "INPUT", "TEXTAREA", "SELECT", "OPTION"]);
    document.querySelectorAll("body *").forEach((element) => {
      if (skipTags.has(element.tagName)) return;
      const text = (element.textContent || "").replace(/\s+/g, " ").trim();
      if (!text || text.length < 2) return;
      const style = window.getComputedStyle(element);
      const canClip = style.textOverflow === "ellipsis" || style.overflow === "hidden" || style.whiteSpace === "nowrap";
      if (!canClip || !element.clientWidth) return;
      const clipped = element.scrollWidth > element.clientWidth + 1 || element.scrollHeight > element.clientHeight + 1;
      if (clipped) {
        if (!element.getAttribute("title") || element.dataset.autoTitle === "true") {
          element.setAttribute("title", text);
          element.dataset.autoTitle = "true";
        }
      } else if (element.dataset.autoTitle === "true") {
        element.removeAttribute("title");
        delete element.dataset.autoTitle;
      }
    });
  };

  let overflowTitleTimer;
  const scheduleOverflowTitles = () => {
    window.clearTimeout(overflowTitleTimer);
    overflowTitleTimer = window.setTimeout(refreshOverflowTitles, 80);
  };
  refreshOverflowTitles();
  window.addEventListener("load", scheduleOverflowTitles);
  window.addEventListener("resize", scheduleOverflowTitles);
  new MutationObserver(scheduleOverflowTitles).observe(document.body, {
    childList: true,
    subtree: true,
    characterData: true,
  });

  // Dashboard switcher dropdown
  const switcherToggle = document.getElementById("dash-switcher-toggle");
  const switcherMenu = document.getElementById("dash-switch-menu");
  if (switcherToggle && switcherMenu) {
    const switcher = switcherToggle.closest(".dash-switcher");
    let switcherCloseTimer;
    const openSwitcher = () => {
      window.clearTimeout(switcherCloseTimer);
      switcherMenu.classList.add("open");
      switcherToggle.setAttribute("aria-expanded", "true");
    };
    const closeSwitcher = () => {
      switcherMenu.classList.remove("open");
      switcherToggle.setAttribute("aria-expanded", "false");
    };
    const scheduleCloseSwitcher = () => {
      window.clearTimeout(switcherCloseTimer);
      switcherCloseTimer = window.setTimeout(closeSwitcher, 140);
    };
    switcher?.addEventListener("mouseenter", openSwitcher);
    switcher?.addEventListener("mouseleave", scheduleCloseSwitcher);
    switcherToggle.addEventListener("focus", openSwitcher);
    switcherToggle.addEventListener("click", (e) => {
      e.stopPropagation();
      const open = switcherMenu.classList.toggle("open");
      switcherToggle.setAttribute("aria-expanded", open.toString());
    });
    switcherMenu.addEventListener("mouseenter", openSwitcher);
    switcherMenu.addEventListener("mouseleave", scheduleCloseSwitcher);
    document.addEventListener("click", () => {
      closeSwitcher();
    });
    switcherMenu.addEventListener("click", (e) => e.stopPropagation());
  }

  if (new URLSearchParams(window.location.search).has("saved")) {
    const path = window.location.pathname;
    if (path.startsWith("/xymon")) {
      showToast("Xymon configuration saved.");
    } else if (path.startsWith("/acronis")) {
      showToast("Acronis configuration saved.");
    } else {
      showToast("Configuration saved and historical alerts rescored.");
    }
  }

  document.querySelectorAll(".db-panel").forEach((panel) => {
    const header = panel.querySelector(".db-panel-hd");
    const body = panel.querySelector(".db-panel-body");
    if (!header || !body) return;
    header.setAttribute("role", "button");
    header.setAttribute("tabindex", "0");
    header.setAttribute("aria-expanded", (!panel.classList.contains("db-panel-collapsed")).toString());
    const togglePanel = () => {
      const collapsed = panel.classList.toggle("db-panel-collapsed");
      header.setAttribute("aria-expanded", (!collapsed).toString());
    };
    header.addEventListener("click", togglePanel);
    header.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") return;
      event.preventDefault();
      togglePanel();
    });
  });

  const scoreDialog = document.getElementById("score-dialog");
  if (scoreDialog) {
    const title = document.getElementById("score-dialog-title");
    const score = document.getElementById("score-dialog-score");
    const reasons = document.getElementById("score-dialog-reasons");
    document.querySelectorAll(".sev-tag-button").forEach((button) => {
      button.addEventListener("click", () => {
        let parsedReasons = [];
        try {
          parsedReasons = JSON.parse(button.dataset.reasons || "[]");
        } catch {
          parsedReasons = [];
        }
        title.textContent = button.dataset.severity || "Unknown";
        score.textContent = button.dataset.score || "0";
        scoreDialog.dataset.severity = (button.dataset.severity || "unknown").toLowerCase();
        reasons.innerHTML = "";
        if (!parsedReasons.length) parsedReasons = ["No scoring reasons were saved for this alert."];
        parsedReasons.forEach((reason) => {
          const item = document.createElement("li");
          item.textContent = reason;
          reasons.appendChild(item);
        });
        scoreDialog.showModal();
      });
    });
    scoreDialog.querySelector(".score-dialog-close")?.addEventListener("click", () => scoreDialog.close());
  }

  const form = document.getElementById("settings-form");
  const dashboardBtn = document.getElementById("settings-dashboard-btn");
  const saveButton = document.getElementById("settings-save-btn");
  const dirtyNote = document.getElementById("settings-dirty-note");

  document.querySelectorAll(".secret-toggle").forEach((button) => {
    button.addEventListener("click", () => {
      const input = button.closest(".secret-control")?.querySelector("[data-secret]");
      if (!input) return;
      const revealing = input.type === "password";
      input.type = revealing ? "text" : "password";
      button.textContent = revealing ? "Hide" : "Show";
      button.classList.toggle("revealed", revealing);
      button.setAttribute("aria-label", revealing ? "Hide secret" : "Reveal secret");
      button.title = revealing ? "Hide" : "Reveal";
    });
  });

  document.querySelectorAll(".secret-copy").forEach((button) => {
    button.addEventListener("click", async () => {
      const input = button.closest(".secret-control")?.querySelector("[data-secret]");
      const value = input?.value || "";
      if (!value) {
        showToast("Enter a new secret value before copying.", "warn");
        return;
      }
      try {
        await navigator.clipboard.writeText(value);
        showToast("Copied to clipboard.");
      } catch {
        showToast("Clipboard copy was blocked by the browser.", "warn");
      }
    });
  });

  const validators = {
    guid: (value) => !value || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value),
    tenant: (value) => !value || /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(value) || /^[a-z0-9.-]+\.[a-z]{2,}$/i.test(value),
    email: (value) => !value || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value),
    "teams-webhook": (value) => !value || /^https:\/\/.+/i.test(value) && /(webhook|logic\.azure|office|powerautomate|workflows)/i.test(value),
  };

  const validationMessages = {
    guid: "Use a valid Azure app/client GUID.",
    tenant: "Use a tenant GUID or tenant domain.",
    email: "Use a valid mailbox email address.",
    "teams-webhook": "Use a valid HTTPS Teams Workflow or webhook URL.",
  };

  const validateField = (input) => {
    const type = input.dataset.validate;
    if (!type || !validators[type]) return true;
    const valid = validators[type](input.value.trim());
    const label = input.closest("label");
    const error = label?.querySelector(".field-error");
    input.classList.toggle("input-invalid", !valid);
    input.setCustomValidity(valid ? "" : validationMessages[type]);
    if (error) error.textContent = valid ? "" : validationMessages[type];
    return valid;
  };

  document.querySelectorAll("[data-validate]").forEach((input) => {
    input.addEventListener("input", () => validateField(input));
    input.addEventListener("blur", () => validateField(input));
  });

  const previewButton = document.getElementById("score-preview-btn");
  previewButton?.addEventListener("click", async () => {
    const result = document.getElementById("score-preview-result");
    result.textContent = "Calculating...";
    const previewConfigNames = [
      "use_taxonomy_weighting",
      "unknown_base_score",
      "severity_critical_threshold",
      "severity_high_threshold",
      "severity_medium_threshold",
      "repeated_same_host_window_hours",
      "repeated_same_host_1_adjustment",
      "repeated_same_host_2_adjustment",
      "repeated_same_host_3_adjustment",
      "campaign_endpoint_window_hours",
      "campaign_endpoint_2_adjustment",
      "campaign_endpoint_3_adjustment",
      "campaign_endpoint_5_adjustment",
      "persistence_2_day_adjustment",
      "persistence_4_day_adjustment",
      "velocity_window_hours",
      "velocity_baseline_days",
      "velocity_multiplier",
      "velocity_min_count",
      "velocity_adjustment",
      "host_alert_window_hours",
      "host_alert_count_threshold",
      "host_alert_adjustment",
      "failure_adjustment",
      "success_adjustment",
      "taxonomy_scores",
    ];
    const previewConfig = {};
    if (form) {
      previewConfigNames.forEach((name) => {
        const input = form.elements.namedItem(name);
        if (!input) return;
        if (input.type === "checkbox") {
          previewConfig[name] = input.checked;
        } else {
          previewConfig[name] = input.value;
        }
      });
    }
    const payload = {
      threat_name: document.getElementById("preview-threat")?.value || "",
      hostname: document.getElementById("preview-host")?.value || "",
      action_taken: document.getElementById("preview-action")?.value || "",
      containment_status: document.getElementById("preview-containment")?.value || "",
      resolved_status: document.getElementById("preview-resolved")?.value || "",
      config: previewConfig,
    };
    try {
      const response = await fetch("/api/scoring-preview", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || "Preview failed");
      const reasons = data.reasons?.length ? data.reasons.join("; ") : "No context adjustments.";
      result.textContent = `${data.severity} (${data.score}) - base ${data.base_score}, context ${data.context_adjustment}. ${reasons}`;
    } catch (error) {
      result.textContent = error.message;
    }
  });

  if (!form || !dashboardBtn) return;

  const serialize = (targetForm) => {
    const data = [...new FormData(targetForm).entries()];
    return data.sort(([a], [b]) => a.localeCompare(b)).map(([key, value]) => `${key}=${encodeURIComponent(value)}`).join("&");
  };

  const initialState = serialize(form);
  const isDirty = () => serialize(form) !== initialState;

  const updateDirtyState = () => {
    const dirty = isDirty();
    form.classList.toggle("is-dirty", dirty);
    if (dirtyNote) {
      dirtyNote.textContent = dirty
        ? "Unsaved changes pending. Save to rescore historical alerts."
        : "Auto-scan stays at 60 days, refreshes every 60 seconds, and rescoring runs after save.";
    }
  };

  form.addEventListener("input", updateDirtyState);
  form.addEventListener("change", updateDirtyState);

  window.addEventListener("beforeunload", (event) => {
    if (!isDirty() || form.dataset.submitting === "true") return;
    event.preventDefault();
    event.returnValue = "";
  });

  dashboardBtn.addEventListener("click", (event) => {
    if (!isDirty()) return;
    event.preventDefault();
    const saveFirst = window.confirm(
      "You have unsaved settings changes. OK to save and go back to Dashboard, or Cancel to discard changes and go back."
    );
    if (saveFirst) {
      form.submit();
    } else {
      window.location.href = dashboardBtn.dataset.href || "/dashboard";
    }
  });

  form.addEventListener("submit", (event) => {
    let valid = true;
    form.querySelectorAll("[data-validate]").forEach((input) => {
      if (!validateField(input)) valid = false;
    });
    const criticalField = form.elements.namedItem("severity_critical_threshold");
    const highField = form.elements.namedItem("severity_high_threshold");
    const mediumField = form.elements.namedItem("severity_medium_threshold");
    if (criticalField && highField && mediumField) {
      const critical = Number(criticalField.value || 0);
      const high = Number(highField.value || 0);
      const medium = Number(mediumField.value || 0);
      if (!(critical > high && high > medium)) {
        valid = false;
        showToast("Severity thresholds must descend: Critical > High > Medium.", "warn");
      }
    }
    if (!valid) {
      event.preventDefault();
      return;
    }
    form.dataset.submitting = "true";
    saveButton?.classList.add("is-saving");
    if (saveButton) saveButton.disabled = true;
  });
});
