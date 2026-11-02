"use strict";

const $ = (sel) => document.querySelector(sel);

const els = {
  stage: $("#stage"),
  screen: $("#screen"),
  idle: $("#idle"),
  connecting: $("#connecting"),
  connectingText: $("#connecting-text"),
  tally: $("#tally"),
  tallyText: $("#tally-text"),
  castBtn: $("#btn-cast"),
  muteBtn: $("#btn-mute"),
  volume: $("#volume"),
  themeBtn: $("#btn-theme"),
  fullscreenBtn: $("#btn-fullscreen"),
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

let state = { phase: "idle", device: null };

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

const CASTING = ["connecting", "activating", "waiting", "handshake", "streaming"];
const TALLY = {
  idle: ["idle", "Off air"],
  connecting: ["wait", "Connecting"],
  activating: ["wait", "Preparing"],
  waiting: ["wait", "Unlock device"],
  handshake: ["wait", "Starting"],
  streaming: ["live", "Live"],
  error: ["error", "Error"],
};

function applyState(next) {
  const prevPhase = state.phase;
  state = next;
  const casting = CASTING.includes(state.phase);
  const live = state.phase === "streaming";

  const [tone, label] = TALLY[state.phase] || TALLY.idle;
  els.tally.dataset.state = tone;
  els.tallyText.textContent = label;

  els.castBtn.textContent = casting ? "Stop" : "Start casting";
  els.castBtn.className = casting ? "btn stop" : "btn primary";
  els.castBtn.disabled = false;

  els.stage.classList.toggle("live", live);
  els.screen.hidden = !live;
  els.idle.hidden = casting;
  els.connecting.hidden = !casting || live;
  els.connectingText.textContent = state.detail || label;
  els.metrics.device.textContent = state.device?.name || "—";

  if (state.phase === "error" && state.error && prevPhase !== "error") toast(state.error, "bad");
  if (!casting && prevPhase === "streaming") {
    player.reset();
    renderMetrics(null);
  }
}

function renderMetrics(stats) {
  const m = els.metrics;
  if (!stats) {
    m.res.textContent = m.fps.textContent = m.lat.textContent = m.audio.textContent = "—";
    return;
  }
  m.res.textContent = `${stats.width}×${stats.height}`;
  m.fps.textContent = String(stats.fps);
  m.lat.textContent = stats.latency === null ? "—" : `${stats.latency} ms`;
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
  const casting = CASTING.includes(state.phase);
  els.castBtn.disabled = true;
  try {
    if (casting) await api("/api/cast/stop");
    else {
      player.reset();
      await api("/api/cast/start", {});
    }
  } finally {
    els.castBtn.disabled = false;
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
  prefs.set("theme", theme);
}
els.themeBtn.addEventListener("click", () =>
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark")
);
applyTheme(prefs.get("theme", "dark"));

connect();
