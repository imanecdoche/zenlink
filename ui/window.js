// Frameless window: title-bar drag, double-click to maximize, window buttons,
// and edge resize, all through the native window API (pywebview js_api).
"use strict";

(() => {
  const topbar = document.querySelector(".topbar");
  const api = () => window.pywebview && window.pywebview.api;

  async function syncMaximized() {
    const a = api();
    if (!a) return;
    document.body.classList.toggle("maximized", Boolean(await a.is_maximized()));
  }

  function onReady() {
    document.body.classList.add("pywebview");
    syncMaximized();
  }
  if (api()) onReady();
  else window.addEventListener("pywebviewready", onReady);

  topbar.addEventListener("mousedown", (e) => {
    if (e.button !== 0 || e.target.closest("button, input, a, .tally")) return;
    api()?.start_drag();
  });
  topbar.addEventListener("dblclick", async (e) => {
    if (e.target.closest("button, input, a")) return;
    await api()?.toggle_maximize();
    syncMaximized();
  });

  document.querySelectorAll("[data-win]").forEach((btn) => {
    btn.addEventListener("click", async () => {
      const a = api();
      if (!a) return;
      if (btn.dataset.win === "minimize") a.minimize();
      else if (btn.dataset.win === "maximize") { await a.toggle_maximize(); syncMaximized(); }
      else a.close();
    });
  });

  document.querySelectorAll(".grips i").forEach((grip) => {
    grip.addEventListener("mousedown", (e) => {
      if (e.button !== 0) return;
      e.preventDefault();
      api()?.start_resize(grip.dataset.edge);
    });
  });

  window.addEventListener("resize", syncMaximized);
})();
