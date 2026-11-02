"use strict";

const $ = (sel) => document.querySelector(sel);

const els = {
  stage: $("#stage"),
  screen: $("#screen"),
  idle: $("#idle"),
  deviceArt: $("#device-art"),
  deviceChip: $("#device-chip"),
  deviceChipName: $("#device-chip-name"),
  deviceChipStatus: $("#device-chip-status"),
  renameBtn: $("#device-rename"),
  renameInput: $("#device-rename-input"),
  idleTitle: $("#idle-title"),
  idleSub: $("#idle-sub"),
  connect: $("#connect"),
  connectTitle: $("#connect-title"),
  connectPct: $("#connect-pct"),
  progressBar: $("#progress-bar"),
  flow: [...document.querySelectorAll("#flow li")],
  connectError: $("#connect-error"),
  connectErrorText: $("#connect-error-text"),
  retryBtn: $("#btn-retry"),
  tally: $("#tally"),
  tallyText: $("#tally-text"),
  castBtn: $("#btn-cast"),
  muteBtn: $("#btn-mute"),
  volume: $("#volume"),
  themeBtn: $("#btn-theme"),
  fullscreenBtn: $("#btn-fullscreen"),
  adminBanner: $("#admin-banner"),
  metrics: { device: $("#m-device"), res: $("#m-res"), fps: $("#m-fps"), lat: $("#m-lat"), audio: $("#m-audio") },
  toasts: $("#toasts"),
};

const prefs = {
  get(key, fallback) {
    try {
      const v = localStorage.getItem(`phonelink.${key}`);
      return v === null ? fallback : JSON.parse(v);
    } catch (_) {
      return fallback;
    }
  },
  set(key, value) {
    try { localStorage.setItem(`phonelink.${key}`, JSON.stringify(value)); } catch (_) {}
  },
};

let state = { phase: "idle", device: null, devices: [] };
let flowStep = -1;        // index of the furthest step reached in this attempt
let showingConnect = false;
let revealTimer = null;

const player = new CastPlayer(els.screen, renderMetrics);
player.setVolume(prefs.get("volume", 100) / 100);
player.setMuted(prefs.get("muted", false));
els.volume.value = String(prefs.get("volume", 100));
els.volume.style.setProperty("--fill", `${els.volume.value}%`);
els.muteBtn.setAttribute("aria-pressed", String(prefs.get("muted", false)));

// ---------------------------------------------------------------- server

async function api(path, body) {
  const resp = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body || {}),
  });
  return resp.json();
}

function connect() {
  const ws = new WebSocket(`ws://${location.host}/ws`);
  ws.binaryType = "arraybuffer";
  ws.onmessage = (event) => {
    if (typeof event.data !== "string") {
      player.handle(event.data);
      return;
    }
    const msg = JSON.parse(event.data);
    if (msg.type === "state") applyState(msg);
    else if (msg.type === "video-config") player.configure(msg);
  };
  ws.onclose = () => setTimeout(connect, 1000);
}

// ---------------------------------------------------------------- state

const CASTING = ["connecting", "activating", "trust", "waiting", "handshake", "streaming"];
// Which checklist step each session phase is working on.
const PHASE_STEP = { connecting: 0, activating: 1, trust: 2, waiting: 2, handshake: 3, streaming: 4 };
const TALLY = {
  idle: ["idle", "Off air"],
  connecting: ["wait", "Connecting"],
  activating: ["wait", "Connecting"],
  trust: ["wait", "Checking trust"],
  waiting: ["wait", "Unlock device"],
  handshake: ["wait", "Starting"],
  streaming: ["live", "Live"],
  error: ["error", "Failed"],
};

function applyState(next) {
  const prevPhase = state.phase;
  state = next;
  const phase = state.phase;
  const casting = CASTING.includes(phase);
  const device = (state.devices || [])[0] || null;

  const [tone, label] = TALLY[phase] || TALLY.idle;
  els.tally.dataset.state = tone;
  els.tallyText.textContent = label;

  els.adminBanner.hidden = !device || device.ready;
  els.castBtn.textContent = casting ? "Stop" : "Start casting";
  els.castBtn.className = casting ? "btn stop" : "btn primary";
  els.castBtn.disabled = !casting && !(device && device.ready);

  renderIdle(device);
  els.metrics.device.textContent = state.device?.name || device?.name || "—";

  if (casting) {
    if (!showingConnect) openConnect(state.device?.name || device?.name);
    advanceFlow(PHASE_STEP[phase]);
  } else if (phase === "error" && showingConnect) {
    failFlow(state.error || "Casting stopped.");
  } else if (phase === "error" && state.error && prevPhase !== "error") {
    toast(state.error, "bad");
  }

  if (!casting && phase !== "error") closeConnect();
  if (prevPhase === "streaming" && phase !== "streaming") {
    player.reset();
    renderMetrics(null);
    showScreen(false);
  }
}

function renderIdle(device) {
  let art = "none";
  els.renameBtn.hidden = !device || !els.renameInput.hidden;
  if (!els.renameInput.hidden) return;  // don't fight the user while renaming
  els.deviceChipName.textContent = device ? device.name : "No device connected";
  els.deviceChipStatus.textContent = !device ? "" : device.ready ? "Ready" : "Driver needed";
  if (!device) {
    els.idleTitle.textContent = "Plug in your iPhone or iPad";
    els.idleSub.textContent = "Use a USB cable. Screen and sound come through the cable, the same way TikTok LIVE Studio casts iOS.";
  } else if (!device.ready) {
    art = "driver";
    els.idleTitle.textContent = "One-time USB setup";
    els.idleSub.textContent = "Close PhoneLink and open Start.bat again. It installs the USB driver once; Windows asks for permission.";
  } else {
    art = "ready";
    els.idleTitle.textContent = `${device.name} is ready`;
    els.idleSub.textContent = "Unlock it, then press Start casting.";
  }
  els.deviceArt.dataset.state = art;
  els.deviceChip.dataset.state = art;
}

// ---------------------------------------------------------------- 1-2-3-4

function openConnect(name) {
  showingConnect = true;
  flowStep = -1;
  clearTimeout(revealTimer);
  els.connect.removeAttribute("data-error");
  els.connectError.hidden = true;
  els.connectTitle.textContent = `Connecting${name ? ` to ${name}` : ""}`;
  for (const li of els.flow) li.dataset.state = "todo";
  setProgress(0);
  els.idle.hidden = true;
  els.connect.hidden = false;
}

function advanceFlow(step) {
  if (step === undefined || step < flowStep) return;
  flowStep = step;
  els.flow.forEach((li, i) => {
    li.dataset.state = i < step ? "done" : i === step ? "active" : "todo";
  });
  setProgress(Math.min(step, 4) / 4);
  if (step >= 4) {
    els.connectTitle.textContent = "Connected";
    clearTimeout(revealTimer);
    revealTimer = setTimeout(() => {
      els.connect.hidden = true;
      showScreen(true);
    }, 650);
  }
}

function failFlow(message) {
  const i = Math.max(flowStep, 0);
  if (els.flow[i]) els.flow[i].dataset.state = "failed";
  els.connect.dataset.error = "";
  els.connectTitle.textContent = "Couldn't connect";
  els.connectErrorText.textContent = message;
  els.connectError.hidden = false;
}

function closeConnect() {
  if (!showingConnect) return;
  showingConnect = false;
  els.connect.hidden = true;
  if (state.phase !== "streaming") els.idle.hidden = false;
}

function setProgress(fraction) {
  els.progressBar.style.width = `${Math.round(fraction * 100)}%`;
  els.connectPct.textContent = `${Math.round(fraction * 100)}%`;
}

function showScreen(on) {
  els.stage.classList.toggle("live", on);
  els.screen.hidden = !on;
  els.idle.hidden = on || showingConnect;
}

// ---------------------------------------------------------------- metrics

function setMetric(el, text) {
  if (el.textContent === text) return;
  el.textContent = text;
  el.classList.remove("flash");
  void el.offsetWidth;
  el.classList.add("flash");
}

function renderMetrics(stats) {
  const m = els.metrics;
  if (!stats) {
    for (const key of ["res", "fps", "lat", "audio"]) m[key].textContent = "—";
    return;
  }
  setMetric(m.res, `${stats.width}×${stats.height}`);
  m.fps.textContent = String(stats.fps);
  m.lat.textContent = stats.latency === null ? "—" : `${stats.latency} ms`;
  setMetric(m.audio, stats.audio ? "48 kHz" : "Silent");
}

function toast(text, tone = "") {
  const el = document.createElement("div");
  el.className = "toast";
  el.dataset.tone = tone;
  const body = document.createElement("span");
  body.textContent = text;
  const close = document.createElement("button");
  close.type = "button";
  close.setAttribute("aria-label", "Dismiss");
  close.textContent = "×";
  close.addEventListener("click", () => el.remove());
  el.append(body, close);
  els.toasts.append(el);
  if (tone !== "bad") setTimeout(() => el.remove(), 5000);
}

// ---------------------------------------------------------------- actions

async function startCasting() {
  player.reset();
  openConnect((state.devices || [])[0]?.name);
  await api("/api/cast/start", {});
}

els.castBtn.addEventListener("click", async () => {
  els.castBtn.disabled = true;
  try {
    if (CASTING.includes(state.phase)) await api("/api/cast/stop");
    else await startCasting();
  } finally {
    applyState(state);
  }
});

els.retryBtn.addEventListener("click", () => startCasting());

// Rename the connected device (stored per device in devices.json).
els.renameBtn.addEventListener("click", () => {
  const device = (state.devices || [])[0];
  if (!device) return;
  els.renameInput.value = device.name;
  els.deviceChipName.hidden = els.deviceChipStatus.hidden = els.renameBtn.hidden = true;
  els.renameInput.hidden = false;
  els.renameInput.focus();
  els.renameInput.select();
});

async function finishRename(save) {
  if (els.renameInput.hidden) return;
  const device = (state.devices || [])[0];
  els.renameInput.hidden = true;
  els.deviceChipName.hidden = els.deviceChipStatus.hidden = false;
  if (save && device) {
    els.deviceChipName.textContent = els.renameInput.value.trim() || device.name;
    applyState(await api("/api/device/name", { id: device.id, name: els.renameInput.value }));
  } else {
    applyState(state);
  }
}
els.renameInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter") finishRename(true);
  else if (e.key === "Escape") finishRename(false);
});
els.renameInput.addEventListener("blur", () => finishRename(true));

els.muteBtn.addEventListener("click", () => {
  const muted = els.muteBtn.getAttribute("aria-pressed") !== "true";
  els.muteBtn.setAttribute("aria-pressed", String(muted));
  player.setMuted(muted);
  prefs.set("muted", muted);
});

els.volume.addEventListener("input", () => {
  const v = Number(els.volume.value);
  els.volume.style.setProperty("--fill", `${v}%`);
  player.setVolume(v / 100);
  prefs.set("volume", v);
});

function toggleFullscreen() {
  const on = !document.body.classList.contains("fullscreen");
  document.body.classList.toggle("fullscreen", on);
  if (on) document.documentElement.requestFullscreen?.().catch(() => {});
  else if (document.fullscreenElement) document.exitFullscreen?.().catch(() => {});
}
els.fullscreenBtn.addEventListener("click", toggleFullscreen);
document.addEventListener("fullscreenchange", () => {
  if (!document.fullscreenElement) document.body.classList.remove("fullscreen");
});
document.addEventListener("keydown", (e) => {
  if (e.key === "F11") {
    e.preventDefault();
    toggleFullscreen();
  } else if (e.key === "Escape" && document.body.classList.contains("fullscreen")) {
    toggleFullscreen();
  }
});
els.stage.addEventListener("dblclick", () => {
  if (state.phase === "streaming") toggleFullscreen();
});

// ---------------------------------------------------------------- theme

function applyTheme(theme) {
  // Switch without transitions, or controls keep the old theme's fill.
  document.documentElement.classList.add("theme-switching");
  document.documentElement.dataset.theme = theme;
  requestAnimationFrame(() =>
    requestAnimationFrame(() => document.documentElement.classList.remove("theme-switching"))
  );
  prefs.set("theme", theme);
}
els.themeBtn.addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark")
);
applyTheme(prefs.get("theme", "dark"));

connect();
