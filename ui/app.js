"use strict";

const $ = (sel) => document.querySelector(sel);

const els = {
  deviceList: $("#device-list"),
  deviceEmpty: $("#device-empty"),
  stage: $("#stage"),
  screen: $("#screen"),
  setup: $("#setup"),
  stageMessage: $("#stage-message"),
  stageDevice: $("#stage-device"),
  stageStatus: $("#stage-status"),
  barStatus: $("#bar-status"),
  castBtn: $("#btn-cast"),
  muteBtn: $("#btn-mute"),
  volume: $("#volume"),
  fullscreenBtn: $("#btn-fullscreen"),
  metrics: { res: $("#m-res"), fps: $("#m-fps"), lat: $("#m-lat"), audio: $("#m-audio") },
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

let state = { phase: "idle", devices: [], device: null };
let selectedId = null;

const player = new CastPlayer(els.screen, renderMetrics);
player.setVolume(prefs.get("volume", 100) / 100);
player.setMuted(prefs.get("muted", false));
els.volume.value = String(prefs.get("volume", 100));
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

// ---------------------------------------------------------------- render

const PHASES = {
  idle: { label: "Idle", tone: "" },
  connecting: { label: "Connecting", tone: "warn" },
  activating: { label: "Preparing device", tone: "warn" },
  waiting: { label: "Waiting for device", tone: "warn" },
  handshake: { label: "Starting stream", tone: "warn" },
  streaming: { label: "Live", tone: "ok" },
  error: { label: "Error", tone: "bad" },
};

function setStatus(el, phase) {
  const info = PHASES[phase] || PHASES.idle;
  el.dataset.tone = info.tone;
  el.querySelector(".status-text").textContent = info.label;
}

function applyState(next) {
  const prevPhase = state.phase;
  state = next;
  const devices = state.devices || [];
  if (!devices.some((d) => d.id === selectedId)) selectedId = devices[0]?.id || null;
  renderDevices(devices);

  const casting = ["connecting", "activating", "waiting", "handshake", "streaming"].includes(state.phase);
  const live = state.phase === "streaming";
  const device = devices.find((d) => d.id === selectedId);

  setStatus(els.stageStatus, state.phase);
  setStatus(els.barStatus, state.phase);
  els.stageDevice.textContent = state.device?.name || device?.name || "No device";

  els.castBtn.textContent = casting ? "Stop casting" : "Start casting";
  els.castBtn.className = casting ? "btn danger" : "btn primary";
  els.castBtn.disabled = !casting && !(device && device.ready);

  els.stage.classList.toggle("live", live);
  els.screen.hidden = !live;
  els.setup.hidden = live || casting;
  renderChecklist(device);

  const message = casting && !live ? state.detail : "";
  els.stageMessage.hidden = !message;
  els.stageMessage.textContent = message || "";
  if (casting && !live) els.setup.hidden = true;


  if (state.phase === "error" && state.error && prevPhase !== "error") toast(state.error, "bad");
  if (!casting && prevPhase === "streaming") {
    player.reset();
    renderMetrics(null);
  }
}

function renderDevices(devices) {
  els.deviceEmpty.hidden = devices.length > 0;
  els.deviceList.replaceChildren(
    ...devices.map((d) => {
      const li = document.createElement("li");
      li.className = "device";
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", String(d.id === selectedId));
      li.tabIndex = 0;
      const text = document.createElement("div");
      const name = document.createElement("span");
      name.className = "device-name";
      name.textContent = d.name;
      const meta = document.createElement("span");
      meta.className = "device-meta";
      meta.textContent = d.ready ? "Ready to cast" : "USB setup needed";
      text.append(name, meta);
      const status = document.createElement("span");
      status.className = "status";
      status.dataset.tone = d.ready ? "ok" : "warn";
      status.innerHTML = '<span class="dot"></span>';
      li.append(text, status);
      const select = () => {
        selectedId = d.id;
        applyState(state);
      };
      li.addEventListener("click", select);
      li.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") select();
      });
      return li;
    })
  );
}

function renderChecklist(device) {
  const steps = {
    connect: device ? "done" : "current",
    unlock: device && device.ready ? "current" : "todo",
    cast: device && device.ready ? "current" : "todo",
  };
  for (const li of document.querySelectorAll("#checklist li")) {
    li.dataset.state = steps[li.dataset.step];
  }
}

function renderMetrics(stats) {
  const m = els.metrics;
  if (!stats) {
    m.res.textContent = m.fps.textContent = m.lat.textContent = m.audio.textContent = "–";
    return;
  }
  m.res.textContent = `${stats.width}×${stats.height}`;
  m.fps.textContent = String(stats.fps);
  m.lat.textContent = stats.latency === null ? "–" : `${stats.latency} ms`;
  m.audio.textContent = stats.audio ? "48 kHz" : "Silent";
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

els.castBtn.addEventListener("click", async () => {
  const casting = ["connecting", "activating", "waiting", "handshake", "streaming"].includes(state.phase);
  els.castBtn.disabled = true;
  if (casting) await api("/api/cast/stop");
  else {
    player.reset();
    await api("/api/cast/start", { device: selectedId });
  }
});


els.muteBtn.addEventListener("click", () => {
  const muted = els.muteBtn.getAttribute("aria-pressed") !== "true";
  els.muteBtn.setAttribute("aria-pressed", String(muted));
  player.setMuted(muted);
  prefs.set("muted", muted);
});

els.volume.addEventListener("input", () => {
  const v = Number(els.volume.value);
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
  // Switch without hover transitions, or controls keep the old theme's fill.
  document.documentElement.classList.add("theme-switching");
  document.documentElement.dataset.theme = theme;
  requestAnimationFrame(() =>
    requestAnimationFrame(() => document.documentElement.classList.remove("theme-switching"))
  );
  for (const b of document.querySelectorAll("[data-theme-choice]")) {
    b.setAttribute("aria-checked", String(b.dataset.themeChoice === theme));
  }
  prefs.set("theme", theme);
}
for (const b of document.querySelectorAll("[data-theme-choice]")) {
  b.addEventListener("click", () => applyTheme(b.dataset.themeChoice));
}
applyTheme(prefs.get("theme", "dark"));

connect();
