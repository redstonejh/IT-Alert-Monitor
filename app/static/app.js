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

  document.querySelectorAll(".nav-status-menu").forEach((menu) => {
    let closeTimer;
    let closeAfterAnimationTimer;
    const closeMenu = (targetMenu = menu) => {
      window.clearTimeout(closeAfterAnimationTimer);
      targetMenu.classList.remove("is-open");
      closeAfterAnimationTimer = window.setTimeout(() => {
        if (!targetMenu.classList.contains("is-open")) targetMenu.open = false;
      }, 220);
    };
    const openMenu = () => {
      window.clearTimeout(closeTimer);
      window.clearTimeout(closeAfterAnimationTimer);
      document.querySelectorAll(".nav-status-menu[open]").forEach((otherMenu) => {
        if (otherMenu !== menu) {
          otherMenu.classList.remove("is-open");
          otherMenu.open = false;
        }
      });
      menu.open = true;
      menu.classList.remove("is-open");
      void menu.offsetWidth;
      window.requestAnimationFrame(() => menu.classList.add("is-open"));
    };
    const scheduleClose = () => {
      window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(() => {
        if (!menu.matches(":hover") && !menu.contains(document.activeElement)) closeMenu();
      }, 140);
    };
    menu.addEventListener("mouseenter", openMenu);
    menu.addEventListener("mouseleave", scheduleClose);
    menu.addEventListener("focusin", openMenu);
    menu.addEventListener("focusout", scheduleClose);
    menu.addEventListener("toggle", () => {
      if (!menu.open) return;
      document.querySelectorAll(".nav-status-menu[open]").forEach((otherMenu) => {
        if (otherMenu !== menu) {
          otherMenu.classList.remove("is-open");
          otherMenu.open = false;
        }
      });
    });
  });

  document.addEventListener("click", (event) => {
    if (event.target?.closest?.(".nav-status-menu")) return;
    document.querySelectorAll(".nav-status-menu[open]").forEach((menu) => {
      menu.classList.remove("is-open");
      menu.open = false;
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

  const dashboardSearchForms = document.querySelectorAll(".range-search");
  const searchableItemsForPanel = (panel) => {
    const rows = [...panel.querySelectorAll("tbody tr")].filter((row) => !row.querySelector(".al-empty"));
    const cards = [...panel.querySelectorAll(".esc-card, .viz-panel")];
    const emptyStates = [...panel.querySelectorAll(".empty-state")];
    return [...rows, ...cards, ...emptyStates];
  };
  const keywordMatches = (text, terms) => {
    const haystack = String(text || "").replace(/\s+/g, " ").toLowerCase();
    return terms.every((term) => haystack.includes(term));
  };
  const applyDashboardKeywordSearch = (input) => {
    const terms = String(input?.value || "").trim().toLowerCase().split(/\s+/).filter(Boolean);
    const searching = terms.length > 0;
    document.querySelectorAll(".panel-layout > .db-panel").forEach((panel) => {
      if (searching && panel.dataset.searchCollapsedBefore === undefined) {
        panel.dataset.searchCollapsedBefore = panel.classList.contains("db-panel-collapsed") ? "true" : "false";
      }
      const items = searchableItemsForPanel(panel);
      const titleText = panel.querySelector(".db-panel-title")?.textContent || "";
      const titleMatches = searching && keywordMatches(titleText, terms);
      let visibleCount = 0;
      let matchedItems = 0;

      if (!panel.dataset.originalPanelCount) {
        panel.dataset.originalPanelCount = panel.querySelector(".db-panel-count")?.textContent?.trim() || "";
      }

      if (items.length) {
        items.forEach((item) => {
          const matched = !searching || titleMatches || keywordMatches(item.textContent, terms);
          item.classList.toggle("dashboard-search-hidden", !matched);
          if (matched) matchedItems += 1;
          if (matched && !item.classList.contains("empty-state")) visibleCount += 1;
        });
      }

      const panelMatches = !searching || titleMatches || (items.length ? matchedItems > 0 : keywordMatches(panel.textContent, terms));
      panel.classList.toggle("dashboard-search-hidden", !panelMatches);
      if (searching && panelMatches) {
        panel.classList.remove("db-panel-collapsed");
        panel.querySelector(".db-panel-hd")?.setAttribute("aria-expanded", "true");
      } else if (!searching && panel.dataset.searchCollapsedBefore !== undefined) {
        const restoreCollapsed = panel.dataset.searchCollapsedBefore === "true";
        panel.classList.toggle("db-panel-collapsed", restoreCollapsed);
        panel.querySelector(".db-panel-hd")?.setAttribute("aria-expanded", (!restoreCollapsed).toString());
        delete panel.dataset.searchCollapsedBefore;
      }

      const count = panel.querySelector(".db-panel-count");
      if (count) {
        count.textContent = searching && items.length ? String(visibleCount) : panel.dataset.originalPanelCount || count.textContent;
      }
    });
    scheduleOverflowTitles();
  };
  dashboardSearchForms.forEach((form) => {
    const input = form.querySelector(".range-search-input");
    if (!input) return;
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      applyDashboardKeywordSearch(input);
    });
    input.addEventListener("input", () => applyDashboardKeywordSearch(input));
    applyDashboardKeywordSearch(input);
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

  const panelStoragePrefix = "dashboard-panel-layout:";
  const panelProfilePrefix = "dashboard-panel-profile:";
  const customPanelsPrefix = "dashboard-custom-panels:";
  const hiddenPanelsPrefix = "dashboard-hidden-panels:";
  const widgetStoragePrefix = "dashboard-widget-layout:";
  const customWidgetsPrefix = "dashboard-custom-widgets:";
  const hiddenWidgetsPrefix = "dashboard-hidden-widgets:";
  const layoutUndoPrefix = "dashboard-layout-undo:";
  const getActivePanelProfile = (layoutKey) => {
    try {
      return localStorage.getItem(`${panelProfilePrefix}${layoutKey}`) || "1";
    } catch {
      return "1";
    }
  };
  const panelStorageKey = (layoutKey, key, profile = getActivePanelProfile(layoutKey)) => {
    return `${panelStoragePrefix}${profile}:${layoutKey}:${key}`;
  };
  const customPanelsKey = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    return `${customPanelsPrefix}${profile}:${layoutKey}`;
  };
  const hiddenPanelsKey = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    return `${hiddenPanelsPrefix}${profile}:${layoutKey}`;
  };
  const widgetStorageKey = (layoutKey, key, profile = getActivePanelProfile(layoutKey)) => {
    return `${widgetStoragePrefix}${profile}:${layoutKey}:${key}`;
  };
  const customWidgetsKey = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    return `${customWidgetsPrefix}${profile}:${layoutKey}`;
  };
  const hiddenWidgetsKey = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    return `${hiddenWidgetsPrefix}${profile}:${layoutKey}`;
  };
  const layoutUndoKey = (layoutKey, profile = getActivePanelProfile(layoutKey)) => `${layoutUndoPrefix}${profile}:${layoutKey}`;
  let layoutUndoCaptureLock = false;
  const layoutScopedPrefixes = (layoutKey, profile = getActivePanelProfile(layoutKey)) => [
    `${panelStoragePrefix}${profile}:${layoutKey}:`,
    `${customPanelsPrefix}${profile}:${layoutKey}`,
    `${hiddenPanelsPrefix}${profile}:${layoutKey}`,
    `${widgetStoragePrefix}${profile}:${layoutKey}:`,
    `${customWidgetsPrefix}${profile}:${layoutKey}`,
    `${hiddenWidgetsPrefix}${profile}:${layoutKey}`,
  ];
  const layoutStorageKeys = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    const prefixes = layoutScopedPrefixes(layoutKey, profile);
    try {
      return Object.keys(localStorage).filter((key) => prefixes.some((prefix) => key.startsWith(prefix)));
    } catch {
      return [];
    }
  };
  const readDraftList = (element, key) => {
    try {
      return JSON.parse(element?.dataset?.[key] || "[]");
    } catch {
      return [];
    }
  };
  const writeDraftList = (element, key, values) => {
    if (!element) return;
    element.dataset[key] = JSON.stringify([...new Set(values.filter(Boolean))]);
  };
  const syncLayoutToolsActive = () => {
    const hasOpenTools = Boolean(document.querySelector(".db-panel-tools-open, .widget-tools-open"));
    document.body.classList.toggle("layout-tools-active", hasOpenTools);
  };
  const liveLayoutUndo = new Map();
  const liveLayoutUndoKey = (layoutKey, profile = getActivePanelProfile(layoutKey)) => `${profile}:${layoutKey}`;
  const serializeLayoutElement = (element, keyName) => ({
    key: element.dataset[keyName],
    html: element.outerHTML,
    hidden: element.hidden,
  });
  const captureLiveLayoutState = (layoutKey, profile = getActivePanelProfile(layoutKey)) => ({
    panels: [...document.querySelectorAll(`.panel-layout[data-layout-key="${CSS.escape(layoutKey)}"]`)].map((layout) => ({
      selector: `.panel-layout[data-layout-key="${CSS.escape(layout.dataset.layoutKey || layoutKey)}"]`,
      hiddenDraft: layout.dataset.hiddenPanelsDraft || "[]",
      items: [...layout.querySelectorAll(":scope > .db-panel, :scope > .db-panel-row-break")].map((item) => (
        item.classList.contains("db-panel-row-break")
          ? { rowBreak: true, html: item.outerHTML }
          : serializeLayoutElement(item, "panelKey")
      )),
    })),
    widgets: [...document.querySelectorAll(`.widget-layout[data-widget-layout-key="${CSS.escape(layoutKey)}"]`)].map((layout) => ({
      selector: `.widget-layout[data-widget-layout-key="${CSS.escape(layout.dataset.widgetLayoutKey || layoutKey)}"]`,
      hiddenDraft: layout.dataset.hiddenWidgetsDraft || "[]",
      items: [...layout.querySelectorAll(":scope > .widget-card")].map((item) => serializeLayoutElement(item, "widgetKey")),
    })),
    profile,
  });
  const pushLiveLayoutUndo = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    const key = liveLayoutUndoKey(layoutKey, profile);
    const stack = liveLayoutUndo.get(key) || [];
    stack.push(captureLiveLayoutState(layoutKey, profile));
    if (stack.length > 12) stack.shift();
    liveLayoutUndo.set(key, stack);
  };
  const restoreLayoutItems = (layout, items, initItem) => {
    layout.replaceChildren();
    items.forEach((item) => {
      const template = document.createElement("template");
      template.innerHTML = item.html;
      const element = template.content.firstElementChild;
      if (!element) return;
      if (!item.rowBreak) element.hidden = Boolean(item.hidden);
      delete element.dataset.panelInitialized;
      delete element.dataset.widgetInitialized;
      element.classList.remove("db-panel-tools-open", "widget-tools-open", "db-panel-dragging", "widget-dragging");
      layout.appendChild(element);
      if (!item.rowBreak) initItem?.(element);
    });
  };
  const captureLayoutUndo = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    if (layoutUndoCaptureLock) return;
    layoutUndoCaptureLock = true;
    window.setTimeout(() => {
      layoutUndoCaptureLock = false;
    }, 250);
    try {
      const snapshot = {};
      layoutStorageKeys(layoutKey, profile).forEach((key) => {
        snapshot[key] = localStorage.getItem(key);
      });
      localStorage.setItem(layoutUndoKey(layoutKey, profile), JSON.stringify({ layoutKey, profile, snapshot }));
    } catch {}
  };
  const restoreLayoutUndo = (layoutKey, profile = getActivePanelProfile(layoutKey)) => {
    const liveKey = liveLayoutUndoKey(layoutKey, profile);
    const stack = liveLayoutUndo.get(liveKey) || [];
    if (stack.length > 1) {
      stack.pop();
      const undo = stack[stack.length - 1];
      undo.widgets.forEach((snapshot) => {
        const layout = document.querySelector(snapshot.selector);
        if (!layout) return;
        layout.dataset.hiddenWidgetsDraft = snapshot.hiddenDraft;
        restoreLayoutItems(layout, snapshot.items, layout.__initWidget);
      });
      undo.panels.forEach((snapshot) => {
        const layout = document.querySelector(snapshot.selector);
        if (!layout) return;
        layout.dataset.hiddenPanelsDraft = snapshot.hiddenDraft;
        restoreLayoutItems(layout, snapshot.items, layout.__initPanel);
        cleanupPanelRowBreaks(layout);
      });
      liveLayoutUndo.set(liveKey, stack);
      syncLayoutToolsActive();
      return true;
    }
    return false;
  };
  const panelDeleteDialog = document.getElementById("panel-delete-dialog");
  const panelDeleteMessage = document.getElementById("panel-delete-message");
  const panelDeleteConfirm = panelDeleteDialog?.querySelector(".confirm-dialog-danger");
  const panelDeleteCancel = panelDeleteDialog?.querySelector(".confirm-dialog-cancel");
  const panelDeleteClose = panelDeleteDialog?.querySelector(".confirm-dialog-close");
  let pendingPanelDelete = null;
  const closePanelDeleteDialog = () => {
    pendingPanelDelete = null;
    panelDeleteDialog?.close();
  };
  const requestPanelDelete = ({ panel, layout, layoutKey, title }) => {
    pendingPanelDelete = { panel, layout, layoutKey, title };
    if (panelDeleteMessage) {
      panelDeleteMessage.textContent = `Are you sure you want to delete "${title} panel"?`;
    }
    if (typeof panelDeleteDialog?.showModal === "function") {
      panelDeleteDialog.showModal();
    } else if (window.confirm(`Are you sure you want to delete "${title} panel"?`)) {
      panelDeleteConfirm?.click();
    }
  };
  panelDeleteCancel?.addEventListener("click", closePanelDeleteDialog);
  panelDeleteClose?.addEventListener("click", closePanelDeleteDialog);
  panelDeleteDialog?.addEventListener("cancel", (event) => {
    event.preventDefault();
    closePanelDeleteDialog();
  });
  panelDeleteConfirm?.addEventListener("click", () => {
    if (!pendingPanelDelete) return;
    const { panel, layout, layoutKey, title } = pendingPanelDelete;
    if (!panel.dataset.customPanel) {
      const hidden = readDraftList(layout, "hiddenPanelsDraft");
      if (!hidden.includes(panel.dataset.panelKey)) hidden.push(panel.dataset.panelKey);
      writeDraftList(layout, "hiddenPanelsDraft", hidden);
    }
    if (panel.dataset.customPanel) {
      panel.remove();
    } else {
      panel.hidden = true;
    }
    cleanupPanelRowBreaks(layout);
    savePanelLayouts(layout);
    showToast(`${title} panel deleted.`);
    closePanelDeleteDialog();
  });
  const getPanelMinimumWidth = (panel) => {
    const drawer = panel.querySelector(".panel-tool-drawer");
    const drawerWidth = Math.ceil(drawer?.scrollWidth || 0);
    const buttonCount = drawer?.querySelectorAll(".panel-tool-button").length || 6;
    const fallbackDrawerWidth = (buttonCount * 34) + (Math.max(0, buttonCount - 1) * 6) + 8;
    const measuredDrawerWidth = Math.max(fallbackDrawerWidth, drawerWidth);
    const drawerRightOffset = 42;
    const safeInset = 28;
    return Math.ceil(measuredDrawerWidth + drawerRightOffset + safeInset);
  };

  const syncPanelMinimumWidth = (panel) => {
    panel.style.setProperty("--panel-min-width", `${getPanelMinimumWidth(panel)}px`);
  };

  const applyPanelSpan = (panel, span) => {
    const safeSpan = Math.max(3, Math.min(12, Number(span) || Number(panel.dataset.defaultSpan) || 12));
    const displaySpan = Number(safeSpan.toFixed(3));
    const gap = 16;
    const columnGaps = Math.max(0, displaySpan - 1);
    panel.style.gridColumn = `span ${Math.ceil(displaySpan)}`;
    panel.style.setProperty("--panel-basis", `calc(((100% - ${gap * 11}px) / 12 * ${displaySpan}) + ${columnGaps * gap}px)`);
    panel.dataset.currentSpan = String(displaySpan);
  };

  const getPanelMinimumHeight = (panel) => {
    const headerHeight = Math.ceil(panel.querySelector(".db-panel-hd")?.getBoundingClientRect().height || 58);
    const bodyFloor = panel.classList.contains("analytics-panel") ? 132 : 168;
    return headerHeight + bodyFloor;
  };

  const applyPanelHeight = (panel, height) => {
    if (!height) {
      panel.style.height = "";
      delete panel.dataset.savedHeight;
      return;
    }
    const safeHeight = Math.max(getPanelMinimumHeight(panel), Number(height));
    panel.dataset.savedHeight = String(safeHeight);
    if (!panel.classList.contains("db-panel-collapsed")) {
      panel.style.height = `${safeHeight}px`;
    }
  };

  const hexToRgb = (hex) => {
    const clean = String(hex || "").replace("#", "").trim();
    if (!/^[0-9a-f]{6}$/i.test(clean)) return null;
    return {
      r: parseInt(clean.slice(0, 2), 16),
      g: parseInt(clean.slice(2, 4), 16),
      b: parseInt(clean.slice(4, 6), 16),
    };
  };

  const readableTextFor = ({ r, g, b }) => {
    const luminance = ((0.299 * r) + (0.587 * g) + (0.114 * b)) / 255;
    return luminance > 0.62 ? "#102033" : "#ffffff";
  };

  const syncPanelThemeVars = (panel, target) => {
    if (!panel || !target) return;
    const rgb = hexToRgb(panel.dataset.panelColor);
    if (!rgb) return;
    const textColor = readableTextFor(rgb);
    const menuTextColor = readableTextFor(rgb);
    target.style.setProperty("--panel-accent", panel.dataset.panelColor);
    target.style.setProperty("--panel-accent-rgb", `${rgb.r}, ${rgb.g}, ${rgb.b}`);
    target.style.setProperty("--panel-accent-text", textColor);
    target.style.setProperty("--panel-menu-fg", menuTextColor);
    target.style.setProperty("--panel-lock-fg", menuTextColor);
    target.style.setProperty("--panel-lock-border", `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, .46)`);
    target.style.setProperty("--panel-lock-glow", `rgba(${rgb.r}, ${rgb.g}, ${rgb.b}, .24)`);
  };

  const applyPanelColor = (panel, color) => {
    const rgb = hexToRgb(color);
    if (!rgb) {
      panel.classList.remove("db-panel-custom-color");
      panel.style.removeProperty("--panel-accent");
      panel.style.removeProperty("--panel-accent-rgb");
      panel.style.removeProperty("--panel-accent-text");
      delete panel.dataset.panelColor;
      return;
    }
    panel.dataset.panelColor = `#${String(color).replace("#", "")}`;
    panel.classList.add("db-panel-custom-color");
    panel.style.setProperty("--panel-accent", panel.dataset.panelColor);
    panel.style.setProperty("--panel-accent-rgb", `${rgb.r}, ${rgb.g}, ${rgb.b}`);
    panel.style.setProperty("--panel-accent-text", readableTextFor(rgb));
  };

  const applyPanelTitleColor = (panel, color) => {
    delete panel.dataset.panelTitleColor;
    panel.classList.remove("db-panel-custom-title");
    const panelRgb = hexToRgb(panel.dataset.panelColor);
    if (panelRgb) {
      panel.style.setProperty("--panel-accent-text", readableTextFor(panelRgb));
    } else {
      panel.style.removeProperty("--panel-accent-text");
    }
  };

  const panelThemePresets = [
    "#2563eb", "#0ea5e9", "#0891b2", "#14b8a6", "#16a34a", "#65a30d", "#ca8a04", "#d97706",
    "#dc2626", "#e11d48", "#db2777", "#9333ea", "#7c3aed", "#4f46e5", "#64748b", "#111827",
  ];
  const panelToolButtonsMarkup = (theme = "#2563eb", includeDelete = true) => `
        <button class="panel-tool-button panel-move-handle" type="button" aria-label="Move panel" title="Move panel"><span class="move-icon" aria-hidden="true"></span></button>
        <button class="panel-tool-button panel-resize-handle" type="button" aria-label="Resize panel" title="Resize panel"><span class="resize-icon" aria-hidden="true"></span></button>
        <button class="panel-tool-button panel-pin-toggle" type="button" aria-label="Pin panel" aria-pressed="false" title="Pin panel"><span class="pin-icon" aria-hidden="true"></span></button>
        <button class="panel-tool-button panel-title-handle" type="button" aria-label="Rename panel" title="Rename panel"><span class="text-icon" aria-hidden="true"></span></button>
        <button class="panel-tool-button panel-color-toggle" type="button" aria-label="Panel colors" aria-expanded="false" title="Panel colors" data-default-theme="${theme}"><span class="color-icon" aria-hidden="true"></span></button>
        ${includeDelete ? '<button class="panel-tool-button panel-delete-handle" type="button" aria-label="Delete panel" title="Delete panel"><span class="trash-icon" aria-hidden="true"></span></button>' : ""}`;

  const createCustomPanel = (definition) => {
    const safeTitle = String(definition.title || "Panel").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
    const panel = document.createElement("section");
    panel.className = "db-panel db-panel-empty-custom";
    panel.dataset.panelKey = definition.key;
    panel.dataset.defaultSpan = String(definition.span || 4);
    panel.dataset.customPanel = "true";
    panel.dataset.defaultTitle = definition.title || "Panel";
    panel.innerHTML = `
      <div class="db-panel-hd db-panel-hd-alerts">
        <span class="db-panel-title">${safeTitle}</span>
        <span class="db-panel-count">0</span>
        <div class="panel-tools">
          <div class="panel-tool-drawer" aria-label="Panel tools">
            ${panelToolButtonsMarkup(definition.color || "#2563eb", true)}
          </div>
          <button class="panel-settings-toggle" type="button" aria-label="Panel settings" aria-expanded="false" title="Panel settings"><span class="settings-icon" aria-hidden="true"></span></button>
        </div>
      </div>
      <div class="db-panel-body">
        <div class="empty-state panel-empty-state">
          <strong>Empty panel</strong>
          <small>Use panel settings to rename, resize, recolor, move, or delete this panel.</small>
        </div>
      </div>`;
    return panel;
  };

  const savePanelLayouts = (layout, profile = getActivePanelProfile(layout.dataset.layoutKey || "default"), options = {}) => {
    const layoutKey = layout.dataset.layoutKey || "default";
    const persist = Boolean(options.persist);
    if (!persist) {
      pushLiveLayoutUndo(layoutKey, profile);
      return;
    }
    captureLayoutUndo(layoutKey, profile);
    [...layout.querySelectorAll(":scope > .db-panel:not([hidden])")].forEach((panel, index) => {
      const key = panel.dataset.panelKey;
      if (!key) return;
      try {
        localStorage.setItem(panelStorageKey(layoutKey, key, profile), JSON.stringify({
          order: index,
          span: Number(panel.dataset.currentSpan) || Number(panel.dataset.defaultSpan) || 12,
          height: panel.dataset.savedHeight ? parseFloat(panel.dataset.savedHeight) : null,
          color: panel.dataset.panelColor || null,
          title: panel.dataset.panelTitle || null,
          pinned: panel.classList.contains("db-panel-pinned"),
          breakBefore: panel.previousElementSibling?.classList.contains("db-panel-row-break") || false,
        }));
      } catch {}
    });
    const customPanels = [...layout.querySelectorAll(':scope > .db-panel[data-custom-panel="true"]:not([hidden])')]
      .map((panel) => ({
        key: panel.dataset.panelKey,
        title: panel.dataset.panelTitle || panel.querySelector(".db-panel-title")?.textContent?.trim() || "Panel",
        color: panel.dataset.panelColor || panel.querySelector(".panel-color-toggle")?.dataset.defaultTheme || "#2563eb",
        span: Number(panel.dataset.defaultSpan) || 4,
      }));
    try {
      localStorage.setItem(customPanelsKey(layoutKey, profile), JSON.stringify(customPanels));
      localStorage.setItem(hiddenPanelsKey(layoutKey, profile), layout.dataset.hiddenPanelsDraft || "[]");
    } catch {}
  };

  const createPanelRowBreak = () => {
    const rowBreak = document.createElement("div");
    rowBreak.className = "db-panel-row-break";
    rowBreak.setAttribute("aria-hidden", "true");
    return rowBreak;
  };

  const cleanupPanelRowBreaks = (layout) => {
    [...layout.querySelectorAll(":scope > .db-panel-row-break")].forEach((rowBreak) => {
      const prev = rowBreak.previousElementSibling;
      const next = rowBreak.nextElementSibling;
      if (!prev || !next || next.classList.contains("db-panel-row-break")) rowBreak.remove();
    });
  };

  const positionPanelColorMenu = (colorToggle, menu) => {
    if (!colorToggle || !menu) return;
    const rect = colorToggle.getBoundingClientRect();
    const width = menu.offsetWidth || 248;
    const gutter = 12;
    const left = Math.max(gutter, Math.min(window.innerWidth - width - gutter, rect.right - width + 2));
    const top = Math.min(window.innerHeight - gutter, rect.bottom + 12);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
  };

  const buildPanelColorMenu = (panel, layout, colorToggle) => {
    if (!colorToggle) return null;
    if (colorToggle.__panelColorMenu) return colorToggle.__panelColorMenu;
    const menu = document.createElement("div");
    menu.className = "panel-color-menu";
    menu.setAttribute("role", "menu");
    const cleanColor = (color) => `#${String(color || "").replace("#", "").toLowerCase()}`;
    const refreshSwatchSelection = () => {
      const activeTheme = cleanColor(panel.dataset.panelColor || colorToggle.dataset.defaultTheme || "");
      menu.querySelectorAll(".panel-color-swatch").forEach((swatch) => {
        const selected = cleanColor(swatch.dataset.color) === activeTheme;
        swatch.classList.toggle("is-selected", selected);
        swatch.setAttribute("aria-pressed", selected.toString());
      });
    };
    colorToggle.__refreshPanelColorMenu = refreshSwatchSelection;

    const addGroup = (label, colors, onSelect, colorGroup) => {
      const group = document.createElement("div");
      group.className = "panel-color-group";
      const groupLabel = document.createElement("span");
      groupLabel.className = "panel-color-label";
      groupLabel.textContent = label;
      const swatches = document.createElement("div");
      swatches.className = "panel-color-swatches";
      colors.forEach((color) => {
        const swatch = document.createElement("button");
        swatch.className = "panel-color-swatch";
        swatch.type = "button";
        swatch.title = color;
        swatch.dataset.color = color;
        swatch.dataset.colorGroup = colorGroup;
        swatch.setAttribute("aria-pressed", "false");
        swatch.style.setProperty("--swatch", color);
        swatch.addEventListener("click", (event) => {
          event.preventDefault();
          event.stopPropagation();
          onSelect(color);
          syncPanelThemeVars(panel, menu);
          if (typeof panel.__saveWidgetLayout === "function") {
            panel.__saveWidgetLayout();
          } else {
            savePanelLayouts(layout);
          }
          refreshSwatchSelection();
          colorToggle.setAttribute("aria-expanded", "true");
          positionPanelColorMenu(colorToggle, menu);
          menu.classList.add("panel-color-menu-open");
        });
        swatches.appendChild(swatch);
      });
      group.append(groupLabel, swatches);
      menu.appendChild(group);
    };

    addGroup("Theme color", panelThemePresets, (color) => applyPanelColor(panel, color), "theme");
    menu.addEventListener("click", (event) => event.stopPropagation());
    menu.addEventListener("keydown", (event) => event.stopPropagation());
    document.body.appendChild(menu);
    colorToggle.__panelColorMenu = menu;
    return menu;
  };

  const animatePanelReflow = (layout, update, excludeItem = null) => {
    const items = [...layout.querySelectorAll(":scope > .db-panel, :scope > .db-panel-placeholder")]
      .filter((item) => item !== excludeItem && !item.classList.contains("db-panel-dragging"));
    const before = new Map(items.map((item) => [item, item.getBoundingClientRect()]));
    update();
    const afterItems = [...layout.querySelectorAll(":scope > .db-panel, :scope > .db-panel-placeholder")]
      .filter((item) => item !== excludeItem && !item.classList.contains("db-panel-dragging"));
    afterItems.forEach((item) => {
      const first = before.get(item);
      if (!first) return;
      const last = item.getBoundingClientRect();
      const dx = first.left - last.left;
      const dy = first.top - last.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      item.animate(
        [
          { transform: `translate(${dx}px, ${dy}px)` },
          { transform: "translate(0, 0)" },
        ],
        {
          duration: 180,
          easing: "cubic-bezier(.2, .8, .2, 1)",
        }
      );
    });
  };
  const animateWidgetReflow = (layout, update, excludeItem = null) => {
    const items = [...layout.querySelectorAll(":scope > .widget-card, :scope > .widget-placeholder")]
      .filter((item) => item !== excludeItem && !item.classList.contains("widget-dragging"));
    const before = new Map(items.map((item) => [item, item.getBoundingClientRect()]));
    update();
    const afterItems = [...layout.querySelectorAll(":scope > .widget-card, :scope > .widget-placeholder")]
      .filter((item) => item !== excludeItem && !item.classList.contains("widget-dragging"));
    afterItems.forEach((item) => {
      const first = before.get(item);
      if (!first) return;
      const last = item.getBoundingClientRect();
      const dx = first.left - last.left;
      const dy = first.top - last.top;
      if (Math.abs(dx) < 1 && Math.abs(dy) < 1) return;
      item.animate(
        [
          { transform: `translate(${dx}px, ${dy}px)` },
          { transform: "translate(0, 0)" },
        ],
        {
          duration: 180,
          easing: "cubic-bezier(.2, .8, .2, 1)",
        }
      );
    });
  };

  const createCustomWidget = (definition) => {
    const safeTitle = String(definition.title || "Widget").replace(/[&<>"']/g, (char) => ({
      "&": "&amp;",
      "<": "&lt;",
      ">": "&gt;",
      '"': "&quot;",
      "'": "&#39;",
    }[char]));
    const widget = document.createElement("a");
    widget.className = "stat-card widget-card widget-card-custom";
    widget.href = definition.href || window.location.pathname + window.location.search;
    widget.dataset.widgetKey = definition.key;
    widget.dataset.widgetType = definition.type || "tracker";
    widget.dataset.defaultSpan = String(definition.span || 3);
    widget.dataset.customWidget = "true";
    widget.innerHTML = `
      <span class="stat-val">${definition.value || "0"}</span>
      <span class="stat-lbl">${safeTitle}</span>`;
    return widget;
  };

  const ensureWidgetTools = (widget, theme = "#2563eb") => {
    if (widget.querySelector(".widget-tools")) return;
    widget.insertAdjacentHTML("beforeend", `
      <div class="widget-tools" aria-label="Widget tools">
        <div class="panel-tool-drawer widget-tool-drawer">
          ${panelToolButtonsMarkup(theme, true)}
        </div>
        <button class="panel-settings-toggle widget-settings-toggle" type="button" aria-label="Widget settings" aria-expanded="false" title="Widget settings"><span class="settings-icon" aria-hidden="true"></span></button>
      </div>`);
  };

  const applyWidgetSpan = (widget, span) => {
    const safeSpan = Math.max(2, Math.min(12, Number(span) || Number(widget.dataset.defaultSpan) || 3));
    const displaySpan = Number(safeSpan.toFixed(3));
    widget.dataset.currentSpan = String(displaySpan);
    const gap = 12;
    widget.style.flexBasis = `calc(((100% - ${gap * 11}px) / 12 * ${displaySpan}) + ${Math.max(0, displaySpan - 1) * gap}px)`;
  };

  const saveWidgetLayouts = (layout, profile = getActivePanelProfile(layout.dataset.widgetLayoutKey || "default"), options = {}) => {
    const layoutKey = layout.dataset.widgetLayoutKey || "default";
    const persist = Boolean(options.persist);
    if (!persist) {
      pushLiveLayoutUndo(layoutKey, profile);
      return;
    }
    captureLayoutUndo(layoutKey, profile);
    [...layout.querySelectorAll(":scope > .widget-card:not([hidden])")].forEach((widget, index) => {
      const key = widget.dataset.widgetKey;
      if (!key) return;
      try {
        localStorage.setItem(widgetStorageKey(layoutKey, key, profile), JSON.stringify({
          order: index,
          span: Number(widget.dataset.currentSpan) || Number(widget.dataset.defaultSpan) || 3,
          color: widget.dataset.panelColor || null,
          title: widget.dataset.panelTitle || null,
          pinned: widget.classList.contains("db-panel-pinned"),
        }));
      } catch {}
    });
    const customWidgets = [...layout.querySelectorAll(':scope > .widget-card[data-custom-widget="true"]:not([hidden])')]
      .map((widget) => ({
        key: widget.dataset.widgetKey,
        title: widget.dataset.panelTitle || widget.querySelector(".stat-lbl")?.textContent?.trim() || "Widget",
        value: widget.querySelector(".stat-val")?.textContent?.trim() || "0",
        color: widget.dataset.panelColor || widget.querySelector(".panel-color-toggle")?.dataset.defaultTheme || "#2563eb",
        span: Number(widget.dataset.currentSpan) || 3,
        type: widget.dataset.widgetType || "tracker",
        href: widget.getAttribute("href") || "",
      }));
    try {
      localStorage.setItem(customWidgetsKey(layoutKey, profile), JSON.stringify(customWidgets));
      localStorage.setItem(hiddenWidgetsKey(layoutKey, profile), layout.dataset.hiddenWidgetsDraft || "[]");
    } catch {}
  };

  const initWidgetLayout = (layout) => {
    const layoutKey = layout.dataset.widgetLayoutKey || "default";
    const profile = getActivePanelProfile(layoutKey);
    let customDefinitions = [];
    try {
      customDefinitions = JSON.parse(localStorage.getItem(customWidgetsKey(layoutKey, profile)) || "[]");
    } catch {
      customDefinitions = [];
    }
    customDefinitions
      .filter((definition) => definition?.key && !layout.querySelector(`:scope > .widget-card[data-widget-key="${CSS.escape(definition.key)}"]`))
      .forEach((definition) => layout.appendChild(createCustomWidget(definition)));
    let hiddenWidgets = [];
    try {
      hiddenWidgets = JSON.parse(localStorage.getItem(hiddenWidgetsKey(layoutKey, profile)) || "[]");
    } catch {
      hiddenWidgets = [];
    }
    writeDraftList(layout, "hiddenWidgetsDraft", hiddenWidgets);
    hiddenWidgets.forEach((key) => {
      const widget = layout.querySelector(`:scope > .widget-card[data-widget-key="${CSS.escape(key)}"]`);
      if (widget) widget.hidden = true;
    });
    const widgets = [...layout.querySelectorAll(":scope > .widget-card")];
    const savedByWidget = new Map();
    widgets.forEach((widget, index) => {
      const key = widget.dataset.widgetKey || `widget-${index}`;
      widget.dataset.defaultOrder = String(index);
      widget.dataset.defaultTitle = widget.querySelector(".stat-lbl")?.textContent?.trim() || "Widget";
      ensureWidgetTools(widget);
      let saved = null;
      try {
        saved = JSON.parse(localStorage.getItem(widgetStorageKey(layoutKey, key, profile)) || "null");
      } catch {}
      savedByWidget.set(widget, saved);
      applyWidgetSpan(widget, saved?.span ?? widget.dataset.defaultSpan ?? 3);
      widget.classList.toggle("db-panel-pinned", Boolean(saved?.pinned));
      applyPanelColor(widget, saved?.color || widget.querySelector(".panel-color-toggle")?.dataset.defaultTheme);
      applyPanelTitleColor(widget, "");
      if (saved?.title) {
        widget.dataset.panelTitle = saved.title;
        const label = widget.querySelector(".stat-lbl");
        if (label) label.textContent = saved.title;
      }
    });
    widgets
      .sort((a, b) => Number(savedByWidget.get(a)?.order ?? a.dataset.defaultOrder ?? 0) - Number(savedByWidget.get(b)?.order ?? b.dataset.defaultOrder ?? 0))
      .forEach((widget) => layout.appendChild(widget));

    const initWidget = (widget) => {
      if (widget.dataset.widgetInitialized === "true") return;
      widget.dataset.widgetInitialized = "true";
      widget.__saveWidgetLayout = () => saveWidgetLayouts(layout);
      const tools = widget.querySelector(".widget-tools");
      const drawer = widget.querySelector(".widget-tool-drawer");
      const settings = widget.querySelector(".widget-settings-toggle");
      const moveHandle = widget.querySelector(".panel-move-handle");
      const resizeHandle = widget.querySelector(".panel-resize-handle");
      const pinButton = widget.querySelector(".panel-pin-toggle");
      const titleButton = widget.querySelector(".panel-title-handle");
      const colorToggle = widget.querySelector(".panel-color-toggle");
      const deleteButton = widget.querySelector(".panel-delete-handle");
      const colorMenu = buildPanelColorMenu(widget, layout, colorToggle);
      let closeTimer;
      let dragging = false;
      const openTools = () => {
        window.clearTimeout(closeTimer);
        widget.classList.add("widget-tools-open");
        settings?.setAttribute("aria-expanded", "true");
        syncLayoutToolsActive();
      };
      const closeTools = () => {
        widget.classList.remove("widget-tools-open");
        settings?.setAttribute("aria-expanded", "false");
        colorMenu?.classList.remove("panel-color-menu-open");
        colorToggle?.setAttribute("aria-expanded", "false");
        syncLayoutToolsActive();
      };
      const scheduleClose = () => {
        window.clearTimeout(closeTimer);
        closeTimer = window.setTimeout(() => {
          if (!tools?.matches(":hover") && !colorMenu?.matches(":hover")) closeTools();
        }, 260);
      };
      tools?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
      });
      tools?.addEventListener("mouseenter", openTools);
      tools?.addEventListener("mouseleave", scheduleClose);
      settings?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        widget.classList.contains("widget-tools-open") ? closeTools() : openTools();
      });
      colorToggle?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const nextOpen = !colorMenu?.classList.contains("panel-color-menu-open");
        if (nextOpen) {
          syncPanelThemeVars(widget, colorMenu);
          colorToggle.__refreshPanelColorMenu?.();
          positionPanelColorMenu(colorToggle, colorMenu);
        }
        colorMenu?.classList.toggle("panel-color-menu-open", nextOpen);
        colorToggle.setAttribute("aria-expanded", nextOpen.toString());
      });
      colorMenu?.addEventListener("mouseenter", openTools);
      colorMenu?.addEventListener("mouseleave", closeTools);
      document.addEventListener("pointerdown", (event) => {
        if (!colorMenu?.classList.contains("panel-color-menu-open")) return;
        if (widget.contains(event.target) || colorMenu.contains(event.target)) return;
        closeTools();
      });
      pinButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const pinned = widget.classList.toggle("db-panel-pinned");
        pinButton.setAttribute("aria-pressed", pinned.toString());
        saveWidgetLayouts(layout);
      });
      titleButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const label = widget.querySelector(".stat-lbl");
        if (!label) return;
        const original = label.textContent.trim();
        label.contentEditable = "true";
        label.focus();
        window.getSelection?.()?.selectAllChildren(label);
        const finish = (commit) => {
          label.contentEditable = "false";
          label.removeEventListener("blur", onBlur);
          label.removeEventListener("keydown", onKeydown);
          const clean = commit ? label.textContent.trim().replace(/\s+/g, " ").slice(0, 36) : original;
          label.textContent = clean || original;
          widget.dataset.panelTitle = label.textContent;
          saveWidgetLayouts(layout);
        };
        const onBlur = () => finish(true);
        const onKeydown = (keyEvent) => {
          keyEvent.stopPropagation();
          if (keyEvent.key === "Enter") {
            keyEvent.preventDefault();
            finish(true);
          } else if (keyEvent.key === "Escape") {
            keyEvent.preventDefault();
            finish(false);
          }
        };
        label.addEventListener("blur", onBlur);
        label.addEventListener("keydown", onKeydown);
      });
      deleteButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const key = widget.dataset.widgetKey;
        if (!widget.dataset.customWidget) {
          const hidden = readDraftList(layout, "hiddenWidgetsDraft");
          if (!hidden.includes(key)) hidden.push(key);
          writeDraftList(layout, "hiddenWidgetsDraft", hidden);
        }
        if (widget.dataset.customWidget) {
          widget.remove();
        } else {
          widget.hidden = true;
        }
        saveWidgetLayouts(layout);
      });
      moveHandle?.addEventListener("pointerdown", (event) => {
        if (event.button !== 0 || widget.classList.contains("db-panel-pinned")) return;
        event.preventDefault();
        event.stopPropagation();
        document.body.classList.add("panel-interaction-active");
        window.getSelection?.()?.removeAllRanges();
        openTools();
        const startX = event.clientX;
        const startY = event.clientY;
        let rect = null;
        let placeholder = null;
        let offsetX = 0;
        let offsetY = 0;
        let lastPlaceholderMove = 0;
        const startWidgets = [...layout.querySelectorAll(":scope > .widget-card")];
        const startIndex = startWidgets.indexOf(widget);
        const pinnedBefore = startWidgets
          .slice(0, Math.max(0, startIndex))
          .filter((item) => item.classList.contains("db-panel-pinned"));
        const previousPinned = pinnedBefore[pinnedBefore.length - 1] || null;
        const nextPinned = startWidgets
          .slice(Math.max(0, startIndex) + 1)
          .find((item) => item.classList.contains("db-panel-pinned")) || null;

        const childIndex = (item) => [...layout.children].indexOf(item);
        const isInsidePinnedSegment = (item) => {
          if (!item || item === widget) return false;
          if (item === placeholder) return true;
          if (item.classList.contains("db-panel-pinned")) return false;
          const itemIndex = childIndex(item);
          if (itemIndex < 0) return false;
          if (previousPinned && itemIndex <= childIndex(previousPinned)) return false;
          if (nextPinned && itemIndex >= childIndex(nextPinned)) return false;
          return true;
        };
        const clampDropBeforeNode = (beforeNode) => {
          if (!beforeNode) return nextPinned?.parentNode === layout ? nextPinned : null;
          const beforeIndex = childIndex(beforeNode);
          if (beforeIndex < 0) return beforeNode;
          if (previousPinned && beforeIndex <= childIndex(previousPinned)) return previousPinned.nextSibling;
          if (nextPinned && beforeIndex >= childIndex(nextPinned)) return nextPinned;
          return beforeNode;
        };
        const startDrag = () => {
          if (dragging) return;
          dragging = true;
          rect = widget.getBoundingClientRect();
          placeholder = document.createElement("div");
          placeholder.className = "widget-placeholder";
          placeholder.style.flexBasis = widget.style.flexBasis;
          placeholder.style.height = `${Math.max(72, rect.height)}px`;
          layout.insertBefore(placeholder, widget);
          widget.classList.add("widget-dragging");
          widget.style.width = `${rect.width}px`;
          widget.style.left = `${rect.left}px`;
          widget.style.top = `${rect.top}px`;
          offsetX = startX - rect.left;
          offsetY = startY - rect.top;
        };
        const orderedDropTargets = () => {
          return [...layout.querySelectorAll(":scope > .widget-card, :scope > .widget-placeholder")]
            .filter((item) => item !== widget)
            .filter(isInsidePinnedSegment)
            .sort((a, b) => {
              const aRect = a.getBoundingClientRect();
              const bRect = b.getBoundingClientRect();
              if (Math.abs(aRect.top - bRect.top) > 12) return aRect.top - bRect.top;
              return aRect.left - bRect.left;
            });
        };
        const placePlaceholder = (beforeNode) => {
          layout.insertBefore(placeholder, clampDropBeforeNode(beforeNode) || null);
        };
        const updatePlaceholderPosition = (clientX, clientY) => {
          if (!placeholder) return;
          const now = performance.now();
          if (now - lastPlaceholderMove < 90) return;
          const ordered = orderedDropTargets();
          const targets = ordered.filter((item) => item !== placeholder);
          if (!targets.length) {
            animateWidgetReflow(layout, () => placePlaceholder(nextPinned || null));
            lastPlaceholderMove = now;
            return;
          }
          const layoutRect = layout.getBoundingClientRect();
          const currentIndex = ordered
            .slice(0, Math.max(0, ordered.indexOf(placeholder)))
            .filter((item) => item !== placeholder).length;
          let nextIndex = currentIndex;
          if (clientY <= layoutRect.top) {
            nextIndex = 0;
          } else if (clientY >= layoutRect.bottom) {
            nextIndex = targets.length;
          } else {
            let best = null;
            let bestDistance = Number.POSITIVE_INFINITY;
            targets.forEach((target) => {
              const targetRect = target.getBoundingClientRect();
              const centerX = targetRect.left + targetRect.width / 2;
              const centerY = targetRect.top + targetRect.height / 2;
              const dx = clientX - centerX;
              const dy = clientY - centerY;
              const distance = (dy * dy) + (dx * dx * 0.35);
              if (distance < bestDistance) {
                bestDistance = distance;
                best = target;
              }
            });
            if (!best) return;
            const bestRect = best.getBoundingClientRect();
            const sameRow = clientY >= bestRect.top && clientY <= bestRect.bottom;
            const before = sameRow
              ? clientX < bestRect.left + bestRect.width / 2
              : clientY < bestRect.top + bestRect.height / 2;
            nextIndex = targets.indexOf(best) + (before ? 0 : 1);
          }

          if (nextIndex === currentIndex) return;

          const placeholderRect = placeholder.getBoundingClientRect();
          const samePlaceholderRow = clientY >= placeholderRect.top - 18 && clientY <= placeholderRect.bottom + 18;
          const switchPadding = 44;
          if (samePlaceholderRow) {
            if (nextIndex > currentIndex && clientX < placeholderRect.right + switchPadding) return;
            if (nextIndex < currentIndex && clientX > placeholderRect.left - switchPadding) return;
          } else {
            if (nextIndex > currentIndex && clientY < placeholderRect.bottom + switchPadding) return;
            if (nextIndex < currentIndex && clientY > placeholderRect.top - switchPadding) return;
          }

          if (nextIndex <= 0) {
            animateWidgetReflow(layout, () => placePlaceholder(targets[0]));
          } else if (nextIndex >= targets.length) {
            animateWidgetReflow(layout, () => placePlaceholder(targets[targets.length - 1].nextSibling));
          } else {
            animateWidgetReflow(layout, () => placePlaceholder(targets[nextIndex]));
          }
          lastPlaceholderMove = now;
        };
        const onMove = (moveEvent) => {
          const dx = moveEvent.clientX - startX;
          const dy = moveEvent.clientY - startY;
          if (!dragging && Math.hypot(dx, dy) < 5) return;
          startDrag();
          moveEvent.preventDefault();
          const visibleEdge = 88;
          const minLeft = Math.min(0, visibleEdge - rect.width);
          const maxLeft = Math.max(0, window.innerWidth - visibleEdge);
          const minTop = Math.min(0, visibleEdge - rect.height);
          const maxTop = Math.max(0, window.innerHeight - visibleEdge);
          widget.style.left = `${Math.round(Math.max(minLeft, Math.min(maxLeft, moveEvent.clientX - offsetX)))}px`;
          widget.style.top = `${Math.round(Math.max(minTop, Math.min(maxTop, moveEvent.clientY - offsetY)))}px`;
          updatePlaceholderPosition(moveEvent.clientX, moveEvent.clientY);
        };
        const onUp = () => {
          document.body.classList.remove("panel-interaction-active");
          closeTools();
          if (dragging && placeholder) {
            widget.classList.remove("widget-dragging");
            widget.style.left = "";
            widget.style.top = "";
            widget.style.width = "";
            layout.insertBefore(widget, placeholder);
            placeholder.remove();
            saveWidgetLayouts(layout);
          }
          dragging = false;
          document.removeEventListener("pointermove", onMove);
          document.removeEventListener("pointerup", onUp);
          document.removeEventListener("pointercancel", onUp);
        };
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onUp);
        document.addEventListener("pointercancel", onUp);
      });
      resizeHandle?.addEventListener("pointerdown", (event) => {
        if (widget.classList.contains("db-panel-pinned")) return;
        event.preventDefault();
        event.stopPropagation();
        document.body.classList.add("panel-interaction-active");
        window.getSelection?.()?.removeAllRanges();
        const layoutWidth = Math.max(1, layout.getBoundingClientRect().width);
        const startSpan = Number(widget.dataset.currentSpan) || 3;
        const startX = event.clientX;
        let lastAnimatedSpan = startSpan;
        const onMove = (moveEvent) => {
          const nextSpan = Math.max(2, Math.min(12, startSpan + (((moveEvent.clientX - startX) / layoutWidth) * 12)));
          if (Math.abs(nextSpan - lastAnimatedSpan) >= .35) {
            animateWidgetReflow(layout, () => applyWidgetSpan(widget, nextSpan), widget);
            lastAnimatedSpan = nextSpan;
          } else {
            applyWidgetSpan(widget, nextSpan);
          }
        };
        const onUp = () => {
          document.body.classList.remove("panel-interaction-active");
          animateWidgetReflow(layout, () => applyWidgetSpan(widget, Math.round(Number(widget.dataset.currentSpan) || startSpan)), widget);
          saveWidgetLayouts(layout);
          document.removeEventListener("pointermove", onMove);
          document.removeEventListener("pointerup", onUp);
          document.removeEventListener("pointercancel", onUp);
        };
        document.addEventListener("pointermove", onMove);
        document.addEventListener("pointerup", onUp);
        document.addEventListener("pointercancel", onUp);
      });
    };
    widgets.forEach(initWidget);
    layout.__initWidget = initWidget;
  };

  document.querySelectorAll(".widget-layout").forEach(initWidgetLayout);

  document.querySelectorAll(".panel-layout").forEach((layout) => {
    const layoutKey = layout.dataset.layoutKey || "default";
    const layoutProfile = getActivePanelProfile(layoutKey);
    let customPanelDefinitions = [];
    try {
      customPanelDefinitions = JSON.parse(localStorage.getItem(customPanelsKey(layoutKey, layoutProfile)) || "[]");
    } catch {
      customPanelDefinitions = [];
    }
    customPanelDefinitions
      .filter((definition) => definition?.key && !layout.querySelector(`:scope > .db-panel[data-panel-key="${CSS.escape(definition.key)}"]`))
      .forEach((definition) => layout.appendChild(createCustomPanel(definition)));
    let hiddenPanels = [];
    try {
      hiddenPanels = JSON.parse(localStorage.getItem(hiddenPanelsKey(layoutKey, layoutProfile)) || "[]");
    } catch {
      hiddenPanels = [];
    }
    writeDraftList(layout, "hiddenPanelsDraft", hiddenPanels);
    hiddenPanels.forEach((key) => {
      const panel = layout.querySelector(`:scope > .db-panel[data-panel-key="${CSS.escape(key)}"]`);
      if (panel) panel.hidden = true;
    });
    const panels = [...layout.querySelectorAll(":scope > .db-panel")];
    const savedByPanel = new Map();
    panels.forEach((panel, index) => {
      const key = panel.dataset.panelKey || `panel-${index}`;
      const titleEl = panel.querySelector(".db-panel-title");
      const defaultTheme = panel.querySelector(".panel-color-toggle")?.dataset.defaultTheme;
      panel.dataset.defaultOrder = String(index);
      if (titleEl) panel.dataset.defaultTitle = titleEl.textContent.trim();
      let saved = null;
      try {
        saved = JSON.parse(localStorage.getItem(panelStorageKey(layoutKey, key, layoutProfile)) || "null");
      } catch {}
      savedByPanel.set(panel, saved);
      applyPanelSpan(panel, saved?.span ?? panel.dataset.defaultSpan ?? 12);
      panel.classList.remove("db-panel-unlocked", "db-panel-pinned");
      if (saved?.pinned) panel.classList.add("db-panel-pinned");
      if (saved?.height) applyPanelHeight(panel, saved.height);
      applyPanelColor(panel, saved?.color || defaultTheme);
      applyPanelTitleColor(panel, "");
      if (saved?.title && titleEl) {
        panel.dataset.panelTitle = saved.title;
        titleEl.textContent = saved.title;
      }
    });

    panels
      .sort((a, b) => {
        const aSaved = savedByPanel.get(a);
        const bSaved = savedByPanel.get(b);
        return Number(aSaved?.order ?? a.dataset.defaultOrder ?? 0) - Number(bSaved?.order ?? b.dataset.defaultOrder ?? 0);
      })
      .forEach((panel) => {
        if (savedByPanel.get(panel)?.breakBefore) layout.appendChild(createPanelRowBreak());
        layout.appendChild(panel);
      });
    cleanupPanelRowBreaks(layout);

    const initPanel = (panel) => {
      if (panel.dataset.panelInitialized === "true") return;
      panel.dataset.panelInitialized = "true";
      syncPanelMinimumWidth(panel);
      const header = panel.querySelector(".db-panel-hd");
      const body = panel.querySelector(".db-panel-body");
      const settingsButton = panel.querySelector(".panel-settings-toggle");
      const panelTools = panel.querySelector(".panel-tools");
      const panelToolDrawer = panel.querySelector(".panel-tool-drawer");
      if (panelToolDrawer && !panelToolDrawer.querySelector(".panel-delete-handle")) {
        panelToolDrawer.insertAdjacentHTML("beforeend", '<button class="panel-tool-button panel-delete-handle" type="button" aria-label="Delete panel" title="Delete panel"><span class="trash-icon" aria-hidden="true"></span></button>');
      }
      const moveHandle = panel.querySelector(".panel-move-handle");
      const resizeHandle = panel.querySelector(".panel-resize-handle");
      const pinButton = panel.querySelector(".panel-pin-toggle");
      const titleButton = panel.querySelector(".panel-title-handle");
      const colorToggle = panel.querySelector(".panel-color-toggle");
      const deleteButton = panel.querySelector(".panel-delete-handle");
      if (!header || !body) return;
      const colorMenu = buildPanelColorMenu(panel, layout, colorToggle);
      pinButton?.setAttribute("aria-pressed", panel.classList.contains("db-panel-pinned").toString());
      let movedDuringPointer = false;
      let toolsCloseTimer;
      let toolPointerCapture = false;

      const openPanelTools = () => {
        window.clearTimeout(toolsCloseTimer);
        panel.classList.add("db-panel-tools-open");
        settingsButton?.setAttribute("aria-expanded", "true");
        syncLayoutToolsActive();
      };

      const closePanelTools = () => {
        panel.classList.remove("db-panel-tools-open");
        settingsButton?.setAttribute("aria-expanded", "false");
        colorToggle?.setAttribute("aria-expanded", "false");
        colorMenu?.classList.remove("panel-color-menu-open");
        syncLayoutToolsActive();
      };

      const scheduleClosePanelTools = () => {
        window.clearTimeout(toolsCloseTimer);
        toolsCloseTimer = window.setTimeout(() => {
          if (toolPointerCapture) return;
          const activeElement = document.activeElement;
          const stillUsingTools =
            settingsButton?.matches(":hover") ||
            panelToolDrawer?.matches(":hover") ||
            colorMenu?.matches(":hover") ||
            (panelTools?.contains(activeElement) && activeElement !== colorToggle);
          if (!stillUsingTools) closePanelTools();
        }, 300);
      };

      panelTools?.addEventListener("click", (event) => event.stopPropagation());
      panelTools?.addEventListener("keydown", (event) => event.stopPropagation());
      panelTools?.addEventListener("mouseleave", scheduleClosePanelTools);
      panelTools?.addEventListener("focusin", openPanelTools);
      panelTools?.addEventListener("focusout", scheduleClosePanelTools);
      settingsButton?.addEventListener("mouseenter", openPanelTools);
      settingsButton?.addEventListener("mouseleave", scheduleClosePanelTools);
      panelToolDrawer?.addEventListener("mouseenter", openPanelTools);
      panelToolDrawer?.addEventListener("mouseleave", scheduleClosePanelTools);
      colorMenu?.addEventListener("mouseenter", openPanelTools);
      colorMenu?.addEventListener("mouseleave", () => {
        if (!toolPointerCapture) closePanelTools();
      });

      settingsButton?.addEventListener("click", (event) => {
        event.stopPropagation();
        if (panel.classList.contains("db-panel-tools-open")) {
          closePanelTools();
        } else {
          openPanelTools();
        }
      });

      colorToggle?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const nextOpen = !colorMenu?.classList.contains("panel-color-menu-open");
        if (nextOpen) {
          syncPanelThemeVars(panel, colorMenu);
          colorToggle.__refreshPanelColorMenu?.();
          positionPanelColorMenu(colorToggle, colorMenu);
        }
        colorMenu?.classList.toggle("panel-color-menu-open", nextOpen);
        colorToggle.setAttribute("aria-expanded", nextOpen.toString());
      });

      window.addEventListener("resize", () => {
        if (colorMenu?.classList.contains("panel-color-menu-open")) positionPanelColorMenu(colorToggle, colorMenu);
      });
      window.addEventListener("scroll", () => {
        if (colorMenu?.classList.contains("panel-color-menu-open")) positionPanelColorMenu(colorToggle, colorMenu);
      }, true);

      pinButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const pinned = panel.classList.toggle("db-panel-pinned");
        pinButton.setAttribute("aria-pressed", pinned.toString());
        savePanelLayouts(layout);
      });

      titleButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const titleEl = panel.querySelector(".db-panel-title");
        if (!titleEl) return;
        const originalTitle = panel.dataset.panelTitle || titleEl.textContent.trim();
        panel.classList.add("db-panel-title-editing");
        titleEl.contentEditable = "true";
        titleEl.spellcheck = false;
        titleEl.focus();
        window.getSelection?.()?.selectAllChildren(titleEl);

        const finishEdit = (commit) => {
          titleEl.removeEventListener("blur", onBlur);
          titleEl.removeEventListener("keydown", onKeydown);
          titleEl.contentEditable = "false";
          panel.classList.remove("db-panel-title-editing");
          if (!commit) {
            titleEl.textContent = originalTitle;
            return;
          }
          const cleanTitle = titleEl.textContent.trim().replace(/\s+/g, " ").slice(0, 36);
          if (cleanTitle) {
            panel.dataset.panelTitle = cleanTitle;
            titleEl.textContent = cleanTitle;
          } else {
            delete panel.dataset.panelTitle;
            titleEl.textContent = panel.dataset.defaultTitle || originalTitle;
          }
          savePanelLayouts(layout);
        };

        const onBlur = () => finishEdit(true);
        const onKeydown = (keyEvent) => {
          keyEvent.stopPropagation();
          if (keyEvent.key === "Enter") {
            keyEvent.preventDefault();
            finishEdit(true);
          } else if (keyEvent.key === "Escape") {
            keyEvent.preventDefault();
            finishEdit(false);
          }
        };

        titleEl.addEventListener("blur", onBlur);
        titleEl.addEventListener("keydown", onKeydown);
      });

      deleteButton?.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const title = panel.dataset.panelTitle || panel.querySelector(".db-panel-title")?.textContent?.trim() || "this";
        requestPanelDelete({ panel, layout, layoutKey, title });
      });

      header.setAttribute("role", "button");
      header.setAttribute("tabindex", "0");
      header.setAttribute("aria-expanded", (!panel.classList.contains("db-panel-collapsed")).toString());
      const togglePanel = () => {
        if (panel.classList.contains("db-panel-title-editing")) return;
        if (movedDuringPointer) {
          movedDuringPointer = false;
          return;
        }
        const collapsed = panel.classList.toggle("db-panel-collapsed");
        if (collapsed) {
          if (panel.style.height) panel.dataset.savedHeight = String(parseFloat(panel.style.height));
          panel.style.height = "";
        } else if (panel.dataset.savedHeight) {
          applyPanelHeight(panel, panel.dataset.savedHeight);
        }
        header.setAttribute("aria-expanded", (!collapsed).toString());
        savePanelLayouts(layout);
      };
      header.addEventListener("click", togglePanel);
      header.addEventListener("keydown", (event) => {
        if (event.target?.closest?.(".panel-tools")) return;
        if (event.target?.isContentEditable) return;
        if (event.key !== "Enter" && event.key !== " ") return;
        event.preventDefault();
        togglePanel();
      });

      moveHandle?.addEventListener("pointerdown", (event) => {
        if (event.button !== 0) return;
        if (panel.classList.contains("db-panel-pinned")) return;
        event.preventDefault();
        event.stopPropagation();
        toolPointerCapture = true;
        openPanelTools();
        document.body.classList.add("panel-interaction-active");
        const startX = event.clientX;
        const startY = event.clientY;
        let rect = null;
        let placeholder = null;
        let rowBreak = null;
        let placeholderBreakActive = false;
        let offsetX = 0;
        let offsetY = 0;
        let dragged = false;
        let lastPlaceholderMove = 0;
        const startPanels = [...layout.querySelectorAll(":scope > .db-panel")];
        const startIndex = startPanels.indexOf(panel);
        const pinnedBefore = startPanels
          .slice(0, Math.max(0, startIndex))
          .filter((item) => item.classList.contains("db-panel-pinned"));
        const previousPinned = pinnedBefore[pinnedBefore.length - 1] || null;
        const nextPinned = startPanels
          .slice(Math.max(0, startIndex) + 1)
          .find((item) => item.classList.contains("db-panel-pinned")) || null;

        const childIndex = (item) => [...layout.children].indexOf(item);

        const isInsidePinnedSegment = (item) => {
          if (!item || item === panel) return false;
          if (item === placeholder) return true;
          if (item.classList.contains("db-panel-pinned")) return false;
          const itemIndex = childIndex(item);
          if (itemIndex < 0) return false;
          if (previousPinned && itemIndex <= childIndex(previousPinned)) return false;
          if (nextPinned && itemIndex >= childIndex(nextPinned)) return false;
          return true;
        };

        const clampDropBeforeNode = (beforeNode) => {
          if (!beforeNode) return nextPinned?.parentNode === layout ? nextPinned : null;
          const beforeIndex = childIndex(beforeNode);
          if (beforeIndex < 0) return beforeNode;
          if (previousPinned && beforeIndex <= childIndex(previousPinned)) return previousPinned.nextSibling;
          if (nextPinned && beforeIndex >= childIndex(nextPinned)) return nextPinned;
          return beforeNode;
        };

        const startDrag = () => {
          if (dragged) return;
          dragged = true;
          window.getSelection?.()?.removeAllRanges();
          rect = panel.getBoundingClientRect();
          placeholder = document.createElement("div");
          placeholder.className = "db-panel-placeholder";
          placeholder.style.gridColumn = panel.style.gridColumn || `span ${panel.dataset.currentSpan || panel.dataset.defaultSpan || 12}`;
          placeholder.style.setProperty("--panel-basis", panel.style.getPropertyValue("--panel-basis"));
          placeholder.style.height = `${Math.max(72, rect.height)}px`;
          if (panel.previousElementSibling?.classList.contains("db-panel-row-break")) {
            panel.previousElementSibling.remove();
          }
          layout.insertBefore(placeholder, panel);
          panel.classList.add("db-panel-dragging");
          panel.style.width = `${rect.width}px`;
          panel.style.height = `${rect.height}px`;
          panel.style.left = `${rect.left}px`;
          panel.style.top = `${rect.top}px`;
          offsetX = startX - rect.left;
          offsetY = startY - rect.top;
        };

        const orderedDropTargets = () => {
          return [...layout.querySelectorAll(":scope > .db-panel, :scope > .db-panel-placeholder")]
            .filter((item) => item !== panel)
            .filter(isInsidePinnedSegment)
            .sort((a, b) => {
              const aRect = a.getBoundingClientRect();
              const bRect = b.getBoundingClientRect();
              if (Math.abs(aRect.top - bRect.top) > 12) return aRect.top - bRect.top;
              return aRect.left - bRect.left;
            });
        };

        const placePlaceholder = (beforeNode, forceRowBreak) => {
          const safeBeforeNode = clampDropBeforeNode(beforeNode);
          if (forceRowBreak && !rowBreak) rowBreak = createPanelRowBreak();
          if (forceRowBreak) {
            layout.insertBefore(rowBreak, safeBeforeNode || null);
            layout.insertBefore(placeholder, rowBreak.nextSibling);
            placeholderBreakActive = true;
          } else {
            if (rowBreak?.parentNode) rowBreak.remove();
            layout.insertBefore(placeholder, safeBeforeNode || null);
            placeholderBreakActive = false;
          }
        };

        const updatePlaceholderPosition = (clientX, clientY) => {
          if (!placeholder) return;
          const now = performance.now();
          if (now - lastPlaceholderMove < 110) return;
          const ordered = orderedDropTargets();
          const targets = ordered.filter((item) => item !== placeholder);
          if (!targets.length) {
            animatePanelReflow(layout, () => placePlaceholder(nextPinned || null, false));
            lastPlaceholderMove = now;
            return;
          }
          const layoutRect = layout.getBoundingClientRect();
          const currentIndex = ordered
            .slice(0, Math.max(0, ordered.indexOf(placeholder)))
            .filter((item) => item !== placeholder).length;
          let nextIndex = currentIndex;
          let forceRowBreak = false;
          if (clientY <= layoutRect.top) {
            nextIndex = 0;
          } else if (clientY >= layoutRect.bottom) {
            nextIndex = targets.length;
            forceRowBreak = true;
          } else {
            let best = null;
            let bestDistance = Number.POSITIVE_INFINITY;
            targets.forEach((target) => {
              const targetRect = target.getBoundingClientRect();
              const centerX = targetRect.left + targetRect.width / 2;
              const centerY = targetRect.top + targetRect.height / 2;
              const dx = clientX - centerX;
              const dy = clientY - centerY;
              const distance = (dy * dy) + (dx * dx * 0.35);
              if (distance < bestDistance) {
                bestDistance = distance;
                best = target;
              }
            });
            if (!best) return;
            const bestRect = best.getBoundingClientRect();
            const sameRow = clientY >= bestRect.top && clientY <= bestRect.bottom;
            forceRowBreak = clientY > bestRect.bottom + 28;
            const before = sameRow
              ? clientX < bestRect.left + bestRect.width / 2
              : clientY < bestRect.top + bestRect.height / 2;
            nextIndex = targets.indexOf(best) + (before ? 0 : 1);
          }

          if (nextIndex === currentIndex && forceRowBreak === placeholderBreakActive) return;

          const placeholderRect = placeholder.getBoundingClientRect();
          const samePlaceholderRow = clientY >= placeholderRect.top - 20 && clientY <= placeholderRect.bottom + 20;
          const switchPadding = 56;
          if (samePlaceholderRow) {
            if (nextIndex > currentIndex && clientX < placeholderRect.right + switchPadding) return;
            if (nextIndex < currentIndex && clientX > placeholderRect.left - switchPadding) return;
          } else {
            if (nextIndex > currentIndex && clientY < placeholderRect.bottom + switchPadding) return;
            if (nextIndex < currentIndex && clientY > placeholderRect.top - switchPadding) return;
          }

          if (nextIndex <= 0) {
            animatePanelReflow(layout, () => placePlaceholder(targets[0], false));
          } else if (nextIndex >= targets.length) {
            animatePanelReflow(layout, () => placePlaceholder(targets[targets.length - 1].nextSibling, forceRowBreak));
          } else {
            animatePanelReflow(layout, () => placePlaceholder(targets[nextIndex], forceRowBreak));
          }
          lastPlaceholderMove = now;
        };

        const onPointerMove = (moveEvent) => {
          const dx = moveEvent.clientX - startX;
          const dy = moveEvent.clientY - startY;
          if (!dragged && Math.hypot(dx, dy) < 6) return;
          startDrag();
          moveEvent.preventDefault();
          const visibleEdge = 96;
          const minLeft = Math.min(0, visibleEdge - rect.width);
          const maxLeft = Math.max(0, window.innerWidth - visibleEdge);
          const minTop = Math.min(0, visibleEdge - rect.height);
          const maxTop = Math.max(0, window.innerHeight - visibleEdge);
          const nextLeft = Math.max(minLeft, Math.min(maxLeft, moveEvent.clientX - offsetX));
          const nextTop = Math.max(minTop, Math.min(maxTop, moveEvent.clientY - offsetY));
          panel.style.left = `${Math.round(nextLeft)}px`;
          panel.style.top = `${Math.round(nextTop)}px`;
          updatePlaceholderPosition(moveEvent.clientX, moveEvent.clientY);
        };

        const onPointerUp = () => {
          document.body.classList.remove("panel-interaction-active");
          toolPointerCapture = false;
          closePanelTools();
          if (dragged && placeholder) {
            panel.classList.remove("db-panel-dragging");
            panel.style.left = "";
            panel.style.top = "";
            panel.style.width = "";
            layout.insertBefore(panel, placeholder);
            placeholder.remove();
            cleanupPanelRowBreaks(layout);
            savePanelLayouts(layout);
          }
          movedDuringPointer = dragged;
          window.setTimeout(() => {
            movedDuringPointer = false;
          }, 0);
          document.removeEventListener("pointermove", onPointerMove);
          document.removeEventListener("pointerup", onPointerUp);
          document.removeEventListener("pointercancel", onPointerUp);
        };

        document.addEventListener("pointermove", onPointerMove);
        document.addEventListener("pointerup", onPointerUp);
        document.addEventListener("pointercancel", onPointerUp);
      });

      resizeHandle?.addEventListener("pointerdown", (event) => {
        if (panel.classList.contains("db-panel-pinned")) return;
        event.preventDefault();
        event.stopPropagation();
        toolPointerCapture = true;
        openPanelTools();
        document.body.classList.add("panel-interaction-active");
        window.getSelection?.()?.removeAllRanges();
        const startX = event.clientX;
        const startY = event.clientY;
        const startRect = panel.getBoundingClientRect();
        const layoutRect = layout.getBoundingClientRect();
        const layoutWidth = Math.max(1, layoutRect.width);
        const startWidthPct = (startRect.width / layoutWidth) * 100;
        const minWidthPct = Math.min(100, (getPanelMinimumWidth(panel) / layoutWidth) * 100);
        let lastAnimatedSpan = Number(panel.dataset.currentSpan) || Number(panel.dataset.defaultSpan) || 12;
        let lastAnimatedHeight = startRect.height;

        const onResizeMove = (moveEvent) => {
          const nextWidthPct = Math.max(minWidthPct, Math.min(100, startWidthPct + (((moveEvent.clientX - startX) / layoutWidth) * 100)));
          const nextSpan = (nextWidthPct / 100) * 12;
          const nextHeight = Math.max(getPanelMinimumHeight(panel), Math.round(startRect.height + (moveEvent.clientY - startY)));
          const normalizedSpan = Math.max(3, Math.min(12, nextSpan));
          const shouldAnimateReflow =
            Math.abs(normalizedSpan - lastAnimatedSpan) >= .35 ||
            Math.abs(nextHeight - lastAnimatedHeight) >= 24;
          if (shouldAnimateReflow) {
            animatePanelReflow(layout, () => {
              applyPanelSpan(panel, normalizedSpan);
              applyPanelHeight(panel, nextHeight);
            }, panel);
            lastAnimatedSpan = normalizedSpan;
            lastAnimatedHeight = nextHeight;
          } else {
            applyPanelSpan(panel, normalizedSpan);
            applyPanelHeight(panel, nextHeight);
          }
        };

        const onResizeEnd = () => {
          document.body.classList.remove("panel-interaction-active");
          toolPointerCapture = false;
          animatePanelReflow(layout, () => applyPanelSpan(panel, Math.round(Number(panel.dataset.currentSpan) || lastAnimatedSpan)), panel);
          closePanelTools();
          savePanelLayouts(layout);
          document.removeEventListener("pointermove", onResizeMove);
          document.removeEventListener("pointerup", onResizeEnd);
          document.removeEventListener("pointercancel", onResizeEnd);
        };

        document.addEventListener("pointermove", onResizeMove);
        document.addEventListener("pointerup", onResizeEnd);
        document.addEventListener("pointercancel", onResizeEnd);
      });
    };

    panels.forEach(initPanel);
    layout.__initPanel = initPanel;
  });

  const bindRangeCustomControls = (root = document) => {
    root.querySelectorAll(".range-custom").forEach((form) => {
      if (form.dataset.rangeCustomBound === "true") return;
      form.dataset.rangeCustomBound = "true";
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
  };

  const bindDashboardKeywordForms = (root = document) => {
    root.querySelectorAll(".range-search").forEach((form) => {
      if (form.dataset.keywordSearchBound === "true") return;
      form.dataset.keywordSearchBound = "true";
      const input = form.querySelector(".range-search-input");
      if (!input) return;
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        applyDashboardKeywordSearch(input);
      });
      input.addEventListener("input", () => applyDashboardKeywordSearch(input));
      applyDashboardKeywordSearch(input);
    });
  };

  const updatePanelFromFetchedPanel = (panel, nextPanel) => {
    const nextTitle = nextPanel.querySelector(".db-panel-title");
    const title = panel.querySelector(".db-panel-title");
    if (title && nextTitle && !panel.dataset.panelTitle) title.textContent = nextTitle.textContent;
    const nextCount = nextPanel.querySelector(".db-panel-count");
    const count = panel.querySelector(".db-panel-count");
    if (count && nextCount) {
      count.textContent = nextCount.textContent;
      panel.dataset.originalPanelCount = nextCount.textContent.trim();
    }
    const nextBody = nextPanel.querySelector(".db-panel-body");
    const body = panel.querySelector(".db-panel-body");
    if (body && nextBody) {
      body.className = nextBody.className;
      body.innerHTML = nextBody.innerHTML;
    }
  };

  const replaceDashboardFilterContent = (nextDocument) => {
    nextDocument.querySelectorAll(".widget-layout").forEach((nextLayout) => {
      const key = nextLayout.dataset.widgetLayoutKey || "default";
      const layout = document.querySelector(`.widget-layout[data-widget-layout-key="${CSS.escape(key)}"]`);
      if (!layout) return;
      layout.replaceWith(nextLayout);
      initWidgetLayout(nextLayout);
      bindRangeCustomControls(nextLayout);
      bindDashboardKeywordForms(nextLayout);
    });

    nextDocument.querySelectorAll(".panel-layout").forEach((nextLayout) => {
      const key = nextLayout.dataset.layoutKey || "default";
      const layout = document.querySelector(`.panel-layout[data-layout-key="${CSS.escape(key)}"]`);
      if (!layout) return;
      nextLayout.querySelectorAll(":scope > .db-panel").forEach((nextPanel) => {
        const panelKey = nextPanel.dataset.panelKey;
        if (!panelKey) return;
        const panel = layout.querySelector(`:scope > .db-panel[data-panel-key="${CSS.escape(panelKey)}"]`);
        if (panel) updatePanelFromFetchedPanel(panel, nextPanel);
      });
    });

    nextDocument.querySelectorAll(".severity-popover, .score-dialog").forEach((nextElement) => {
      if (!nextElement.id) return;
      const element = document.getElementById(nextElement.id);
      if (element) element.replaceWith(nextElement);
    });

    scheduleOverflowTitles();
  };

  const loadDashboardFilter = async (url, { push = true } = {}) => {
    document.body.classList.add("dashboard-filter-loading");
    try {
      const response = await fetch(url, {
        headers: { "X-Requested-With": "fetch" },
      });
      if (!response.ok) throw new Error("Filter request failed");
      const html = await response.text();
      const nextDocument = new DOMParser().parseFromString(html, "text/html");
      replaceDashboardFilterContent(nextDocument);
      if (push) window.history.pushState({ dashboardFilterUrl: url }, "", url);
    } catch (error) {
      window.location.href = url;
    } finally {
      document.body.classList.remove("dashboard-filter-loading");
    }
  };

  document.addEventListener("click", (event) => {
    if (event.defaultPrevented || event.button !== 0 || event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;
    const filterTarget = event.target?.closest?.(".widget-card[data-widget-type='tracker'], .range-bar a[href]");
    if (!filterTarget || filterTarget.closest(".widget-tools")) return;
    const href = filterTarget.getAttribute("href");
    if (!href) return;
    const url = new URL(href, window.location.href);
    if (url.origin !== window.location.origin) return;
    if (!["/dashboard", "/acronis", "/xymon"].includes(url.pathname)) return;
    event.preventDefault();
    loadDashboardFilter(url.toString());
  });

  document.addEventListener("submit", (event) => {
    const form = event.target?.closest?.(".range-custom");
    if (!form) return;
    const action = form.getAttribute("action") || window.location.pathname;
    const url = new URL(action, window.location.href);
    if (url.origin !== window.location.origin) return;
    if (!["/dashboard", "/acronis", "/xymon"].includes(url.pathname)) return;
    event.preventDefault();
    const params = new URLSearchParams(new FormData(form));
    url.search = params.toString();
    loadDashboardFilter(url.toString());
  });

  window.addEventListener("popstate", () => {
    if (!["/dashboard", "/acronis", "/xymon"].includes(window.location.pathname)) return;
    loadDashboardFilter(window.location.href, { push: false });
  });

  [...new Set([
    ...[...document.querySelectorAll(".panel-layout")].map((layout) => layout.dataset.layoutKey || "default"),
    ...[...document.querySelectorAll(".widget-layout")].map((layout) => layout.dataset.widgetLayoutKey || "default"),
  ])].forEach((layoutKey) => pushLiveLayoutUndo(layoutKey));

  const activeLayoutSlot = (layoutKey) => {
    return document.querySelector(`.layout-slot-trigger[data-layout-target="${CSS.escape(layoutKey)}"]`)?.dataset.currentSlot || getActivePanelProfile(layoutKey);
  };

  document.querySelectorAll(".layout-slot-picker").forEach((picker) => {
    const layoutKey = picker.dataset.layoutTarget || "default";
    const trigger = picker.querySelector(".layout-slot-trigger");
    const menu = picker.querySelector(".layout-slot-menu");
    const activeSlot = getActivePanelProfile(layoutKey);
    if (trigger) {
      trigger.dataset.layoutTarget = layoutKey;
      trigger.dataset.currentSlot = activeSlot;
      trigger.textContent = `Layout ${activeSlot}`;
    }
    menu?.querySelectorAll("[data-slot]").forEach((option) => {
      option.classList.toggle("is-active", option.dataset.slot === activeSlot);
      option.addEventListener("click", (event) => {
        event.preventDefault();
        event.stopPropagation();
        const slot = option.dataset.slot || "1";
        if (trigger) {
          trigger.dataset.currentSlot = slot;
          trigger.textContent = `Layout ${slot}`;
          trigger.setAttribute("aria-expanded", "false");
        }
        menu.classList.remove("open");
        menu.querySelectorAll("[data-slot]").forEach((item) => item.classList.toggle("is-active", item.dataset.slot === slot));
      });
    });
    let closeTimer;
    const openMenu = () => {
      window.clearTimeout(closeTimer);
      menu?.classList.add("open");
      trigger?.setAttribute("aria-expanded", "true");
    };
    const scheduleClose = () => {
      window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(() => {
        menu?.classList.remove("open");
        trigger?.setAttribute("aria-expanded", "false");
      }, 140);
    };
    picker.addEventListener("mouseenter", openMenu);
    picker.addEventListener("mouseleave", scheduleClose);
    trigger?.addEventListener("focus", openMenu);
    trigger?.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !menu?.classList.contains("open");
      menu?.classList.toggle("open", open);
      trigger.setAttribute("aria-expanded", String(open));
    });
  });

  document.querySelectorAll(".layout-load-button").forEach((button) => {
    button.addEventListener("click", () => {
      const layoutKey = button.dataset.layoutTarget || "default";
      const selected = activeLayoutSlot(layoutKey) || "1";
      try {
        localStorage.setItem(`${panelProfilePrefix}${layoutKey}`, selected);
      } catch {}
      showToast(`Loading layout ${selected}.`);
      window.location.reload();
    });
  });

  document.querySelectorAll(".layout-save-button").forEach((button) => {
    button.addEventListener("click", () => {
      const layoutKey = button.dataset.layoutTarget || "default";
      const selected = activeLayoutSlot(layoutKey) || "1";
      try {
        localStorage.setItem(`${panelProfilePrefix}${layoutKey}`, selected);
        layoutStorageKeys(layoutKey, selected).forEach((key) => localStorage.removeItem(key));
      } catch {}
      const layout = document.querySelector(`.panel-layout[data-layout-key="${CSS.escape(layoutKey)}"]`);
      if (layout) savePanelLayouts(layout, selected, { persist: true });
      const widgetLayout = document.querySelector(`.widget-layout[data-widget-layout-key="${CSS.escape(layoutKey)}"]`);
      if (widgetLayout) saveWidgetLayouts(widgetLayout, selected, { persist: true });
      showToast(`Layout ${selected} saved.`);
    });
  });

  document.querySelectorAll(".panel-add-picker").forEach((picker) => {
    const trigger = picker.querySelector(".panel-add-button");
    const menu = picker.querySelector(".panel-add-menu");
    let closeTimer;
    const openMenu = () => {
      window.clearTimeout(closeTimer);
      menu?.classList.add("open");
      trigger?.setAttribute("aria-expanded", "true");
    };
    const scheduleClose = () => {
      window.clearTimeout(closeTimer);
      closeTimer = window.setTimeout(() => {
        menu?.classList.remove("open");
        trigger?.setAttribute("aria-expanded", "false");
      }, 140);
    };
    picker.addEventListener("mouseenter", openMenu);
    picker.addEventListener("mouseleave", scheduleClose);
    trigger?.addEventListener("focus", openMenu);
    trigger?.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !menu?.classList.contains("open");
      menu?.classList.toggle("open", open);
      trigger.setAttribute("aria-expanded", String(open));
    });
  });

  document.querySelectorAll(".panel-add-action").forEach((button) => {
    button.addEventListener("click", () => {
      const layoutKey = button.dataset.layoutTarget || "default";
      const layout = document.querySelector(`.panel-layout[data-layout-key="${CSS.escape(layoutKey)}"]`);
      if (!layout) return;
      const selected = getActivePanelProfile(layoutKey);
      savePanelLayouts(layout, selected);
      layout.querySelectorAll(":scope > .db-panel").forEach(syncPanelMinimumWidth);
      const used = new Set(
        [...layout.querySelectorAll(":scope > .db-panel")]
          .map((panel) => panel.dataset.panelColor || panel.querySelector(".panel-color-toggle")?.dataset.defaultTheme)
          .filter(Boolean)
          .map((color) => color.toLowerCase())
      );
      const customCount = layout.querySelectorAll(':scope > .db-panel[data-custom-panel="true"]').length;
      const nextColor =
        panelThemePresets.find((color) => !used.has(color.toLowerCase())) ||
        panelThemePresets[customCount % panelThemePresets.length];
      const key = `custom-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
      const title = `Panel ${customCount + 1}`;
      const definition = { key, title, color: nextColor, span: 4 };
      const order = [...layout.querySelectorAll(":scope > .db-panel")].length;
      const panel = createCustomPanel(definition);
      panel.dataset.defaultOrder = String(order);
      applyPanelSpan(panel, 4);
      applyPanelColor(panel, nextColor);
      applyPanelTitleColor(panel, "#ffffff");
      animatePanelReflow(layout, () => layout.appendChild(panel));
      layout.__initPanel?.(panel);
      savePanelLayouts(layout, selected);
      showToast(`${title} added.`);
    });
  });

  document.querySelectorAll(".widget-add-action").forEach((button) => {
    button.addEventListener("click", () => {
      const layoutKey = button.dataset.widgetTarget || "default";
      const layout = document.querySelector(`.widget-layout[data-widget-layout-key="${CSS.escape(layoutKey)}"]`);
      if (!layout) return;
      const selected = getActivePanelProfile(layoutKey);
      saveWidgetLayouts(layout, selected);
      const used = new Set(
        [...layout.querySelectorAll(":scope > .widget-card")]
          .map((widget) => widget.dataset.panelColor || widget.querySelector(".panel-color-toggle")?.dataset.defaultTheme)
          .filter(Boolean)
          .map((color) => color.toLowerCase())
      );
      const customCount = layout.querySelectorAll(':scope > .widget-card[data-custom-widget="true"]').length;
      const nextColor =
        panelThemePresets.find((color) => !used.has(color.toLowerCase())) ||
        panelThemePresets[customCount % panelThemePresets.length];
      const key = `widget-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`;
      const title = `Widget ${customCount + 1}`;
      const definition = { key, title, value: "0", color: nextColor, span: 3, type: "tracker" };
      const widget = createCustomWidget(definition);
      ensureWidgetTools(widget, nextColor);
      applyWidgetSpan(widget, 3);
      applyPanelColor(widget, nextColor);
      applyPanelTitleColor(widget, "#ffffff");
      animateWidgetReflow(layout, () => layout.appendChild(widget));
      layout.__initWidget?.(widget);
      saveWidgetLayouts(layout, selected);
      showToast(`${title} added.`);
    });
  });

  document.querySelectorAll(".panel-undo-button").forEach((button) => {
    button.addEventListener("click", () => {
      const layoutKey = button.dataset.layoutTarget || "default";
      const profile = getActivePanelProfile(layoutKey);
      if (!restoreLayoutUndo(layoutKey, profile)) {
        showToast("No layout change to undo.", "warn");
        return;
      }
      showToast("Layout change undone.");
    });
  });

  document.querySelectorAll(".panel-reset-button").forEach((button) => {
    button.addEventListener("click", () => {
      const layoutKey = button.dataset.layoutTarget || document.querySelector(".panel-layout")?.dataset.layoutKey || "default";
      const profile = getActivePanelProfile(layoutKey);
      const layouts = [...document.querySelectorAll(`.panel-layout[data-layout-key="${CSS.escape(layoutKey)}"]`)];
      const widgetLayouts = [...document.querySelectorAll(`.widget-layout[data-widget-layout-key="${CSS.escape(layoutKey)}"]`)];
      captureLayoutUndo(layoutKey, profile);
      widgetLayouts.forEach((layout) => {
        writeDraftList(layout, "hiddenWidgetsDraft", []);
        layout.querySelectorAll(':scope > .widget-card[data-custom-widget="true"]').forEach((widget) => widget.remove());
        [...layout.querySelectorAll(":scope > .widget-card")]
          .sort((a, b) => Number(a.dataset.defaultOrder || 0) - Number(b.dataset.defaultOrder || 0))
          .forEach((widget) => {
            widget.hidden = false;
            widget.classList.remove("db-panel-pinned", "widget-tools-open", "db-panel-custom-color", "db-panel-custom-title");
            widget.style.flexBasis = "";
            delete widget.dataset.currentSpan;
            delete widget.dataset.panelColor;
            delete widget.dataset.panelTitleColor;
            delete widget.dataset.panelTitle;
            widget.style.removeProperty("--panel-accent");
            widget.style.removeProperty("--panel-accent-rgb");
            widget.style.removeProperty("--panel-accent-text");
            applyWidgetSpan(widget, widget.dataset.defaultSpan || 3);
            const label = widget.querySelector(".stat-lbl");
            if (label && widget.dataset.defaultTitle) label.textContent = widget.dataset.defaultTitle;
            const defaultTheme = widget.querySelector(".panel-color-toggle")?.dataset.defaultTheme;
            applyPanelColor(widget, defaultTheme);
            applyPanelTitleColor(widget, "");
            layout.appendChild(widget);
          });
      });
      layouts.forEach((layout) => {
        writeDraftList(layout, "hiddenPanelsDraft", []);
        layout.querySelectorAll(":scope > .db-panel-row-break").forEach((rowBreak) => rowBreak.remove());
        layout.querySelectorAll(':scope > .db-panel[data-custom-panel="true"]').forEach((panel) => panel.remove());
        [...layout.querySelectorAll(":scope > .db-panel")]
          .sort((a, b) => Number(a.dataset.defaultOrder || 0) - Number(b.dataset.defaultOrder || 0))
          .forEach((panel) => {
            panel.hidden = false;
            panel.classList.remove("db-panel-unlocked", "db-panel-dragging");
            panel.classList.remove("db-panel-pinned");
            panel.classList.remove("db-panel-tools-open", "db-panel-custom-color", "db-panel-custom-title");
            panel.style.gridColumn = "";
            panel.style.height = "";
            delete panel.dataset.savedHeight;
            delete panel.dataset.panelColor;
            delete panel.dataset.panelTitleColor;
            delete panel.dataset.panelTitle;
            panel.style.left = "";
            panel.style.top = "";
            panel.style.width = "";
            panel.style.removeProperty("--panel-accent");
            panel.style.removeProperty("--panel-accent-rgb");
            panel.style.removeProperty("--panel-accent-text");
            applyPanelSpan(panel, panel.dataset.defaultSpan || 12);
            const defaultTheme = panel.querySelector(".panel-color-toggle")?.dataset.defaultTheme;
            applyPanelColor(panel, defaultTheme);
            applyPanelTitleColor(panel, "#ffffff");
            const titleEl = panel.querySelector(".db-panel-title");
            if (titleEl && panel.dataset.defaultTitle) titleEl.textContent = panel.dataset.defaultTitle;
            layout.appendChild(panel);
            const settingsButton = panel.querySelector(".panel-settings-toggle");
            settingsButton?.setAttribute("aria-expanded", "false");
            const pinButton = panel.querySelector(".panel-pin-toggle");
            pinButton?.setAttribute("aria-pressed", "false");
          });
      });
      showToast("Layout reset to default.");
      pushLiveLayoutUndo(layoutKey, profile);
    });
  });

  const scoreDialog = document.getElementById("score-dialog");
  if (scoreDialog) {
    document.addEventListener("click", (event) => {
      const button = event.target?.closest?.(".sev-tag-button");
      if (!button) return;
      const currentDialog = document.getElementById("score-dialog");
      const title = document.getElementById("score-dialog-title");
      const score = document.getElementById("score-dialog-score");
      const reasons = document.getElementById("score-dialog-reasons");
      if (!currentDialog || !title || !score || !reasons) return;
      let parsedReasons = [];
      try {
        parsedReasons = JSON.parse(button.dataset.reasons || "[]");
      } catch {
        parsedReasons = [];
      }
      title.textContent = button.dataset.severity || "Unknown";
      score.textContent = button.dataset.score || "0";
      currentDialog.dataset.severity = (button.dataset.severity || "unknown").toLowerCase();
      reasons.innerHTML = "";
      if (!parsedReasons.length) parsedReasons = ["No scoring reasons were saved for this alert."];
      parsedReasons.forEach((reason) => {
        const item = document.createElement("li");
        item.textContent = reason;
        reasons.appendChild(item);
      });
      currentDialog.showModal();
    });
    document.addEventListener("click", (event) => {
      if (!event.target?.closest?.(".score-dialog-close")) return;
      document.getElementById("score-dialog")?.close();
    });
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
