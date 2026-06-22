const els = {
  activeCamera: document.getElementById("activeCamera"),
  personPosition: document.getElementById("personPosition"),
  modeState: document.getElementById("modeState"),
  ffmpegState: document.getElementById("ffmpegState"),
  mapCanvas: document.getElementById("mapCanvas"),
  signalList: document.getElementById("signalList"),
  cameraGrid: document.getElementById("cameraGrid"),
  historyList: document.getElementById("historyList"),
  camerasJson: document.getElementById("camerasJson"),
  zonesJson: document.getElementById("zonesJson"),
  switchCooldown: document.getElementById("switchCooldown"),
  idleFallback: document.getElementById("idleFallback"),
  apriltagFamily: document.getElementById("apriltagFamily"),
  apriltagScanInterval: document.getElementById("apriltagScanInterval"),
  apriltagCaptureWidth: document.getElementById("apriltagCaptureWidth"),
  apriltagCaptureHeight: document.getElementById("apriltagCaptureHeight"),
  apriltagMinDecisionMargin: document.getElementById("apriltagMinDecisionMargin"),
  xRange: document.getElementById("xRange"),
  yRange: document.getElementById("yRange"),
  zRange: document.getElementById("zRange"),
  printMarker: document.getElementById("printMarker"),
  saveConfig: document.getElementById("saveConfig"),
  resetDemo: document.getElementById("resetDemo"),
  nudgeLeft: document.getElementById("nudgeLeft"),
  nudgeRight: document.getElementById("nudgeRight"),
  nudgeForward: document.getElementById("nudgeForward"),
  nudgeBack: document.getElementById("nudgeBack")
};

const ctx = els.mapCanvas.getContext("2d");
let state = null;
let renderQueued = false;

const format = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit"
});

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options
  });
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function queueRender() {
  if (renderQueued) return;
  renderQueued = true;
  requestAnimationFrame(() => {
    renderQueued = false;
    render();
  });
}

function currentCamera() {
  return state?.cameras?.find((camera) => camera.id === state.active_camera_id) ?? null;
}

function updatePersonInputs(person) {
  els.xRange.value = String(person.x);
  els.yRange.value = String(person.y);
  els.zRange.value = String(person.z);
}

function syncConfigEditors() {
  els.switchCooldown.value = String(state.settings?.switch_cooldown_ms ?? 700);
  els.camerasJson.value = JSON.stringify(state.cameras ?? [], null, 2);
  els.zonesJson.value = JSON.stringify(state.zones ?? [], null, 2);
  els.apriltagFamily.value = state.settings?.apriltag_family ?? "tagStandard41h12";
  els.apriltagScanInterval.value = String(state.settings?.apriltag_scan_interval_s ?? 1.0);
  els.apriltagCaptureWidth.value = String(state.settings?.apriltag_capture_width ?? 640);
  els.apriltagCaptureHeight.value = String(state.settings?.apriltag_capture_height ?? 360);
  els.apriltagMinDecisionMargin.value = String(state.settings?.apriltag_min_decision_margin ?? 20.0);
  els.idleFallback.innerHTML = (state.cameras ?? [])
    .map((camera) => `<option value="${camera.id}">${camera.name}</option>`)
    .join("");
  els.idleFallback.value = state.settings?.idle_fallback_camera_id ?? state.active_camera_id ?? "";
}

function renderSignals() {
  const pieces = [];
  pieces.push({
    title: "Switch rule",
    value: "Server scans all cameras, last marker seen wins",
    meta: "The server checks each camera stream every second and stores the freshest detection."
  });
  pieces.push({
    title: "Person source",
    value: `${state.person.source ?? "manual"} ${state.person.confidence ? `(conf ${state.person.confidence})` : ""}`,
    meta: `position ${state.person.x.toFixed(2)}, ${state.person.y.toFixed(2)}, ${state.person.z.toFixed(2)}`
  });
  pieces.push({
    title: "Switch cooldown",
    value: `${state.settings?.switch_cooldown_ms ?? 700} ms`,
    meta: `fallback camera: ${state.settings?.idle_fallback_camera_id ?? "-"}`
  });
  pieces.push({
    title: "Marker",
    value: `${state.marker?.last_marker_id ?? "head-marker"}`,
    meta: `last seen by ${state.marker?.last_camera_id ?? "-"} at ${
      state.marker?.last_detected_at ? format.format(new Date(state.marker.last_detected_at * 1000)) : "never"
    }`
  });
  pieces.push({
    title: "Scanner",
    value: state.marker_scan?.running ? "running" : "idle",
    meta: `family: ${state.settings?.apriltag_family ?? "tagStandard41h12"}, capture: ${
      state.settings?.apriltag_capture_width ?? 640
    }x${state.settings?.apriltag_capture_height ?? 360}, margin >= ${
      state.settings?.apriltag_min_decision_margin ?? 20
    }`
  });

  els.signalList.innerHTML = pieces
    .map(
      (piece) => `
        <div class="signal">
          <strong>${piece.title}</strong>
          <div>${piece.value}</div>
          <div class="meta">${piece.meta}</div>
        </div>`
    )
    .join("");
}

function renderCameraGrid() {
  els.cameraGrid.innerHTML = (state.cameras ?? [])
    .map((camera) => {
      const active = camera.id === state.active_camera_id;
      const preview =
        camera.stream_url && state.ffmpeg_available
          ? `<img src="/api/cameras/${camera.id}/preview.mjpg" alt="${camera.name} live preview" />`
          : `<div class="camera-preview">No preview yet<br/>Add an RTSP URL and make sure ffmpeg is installed on the server.</div>`;
      const marker = state.marker_detections?.[camera.id];
      const markerLine = marker
        ? `marker: ${marker.marker_id} · ${Math.round((marker.confidence ?? 0) * 100)}% · ${format.format(
            new Date(marker.detected_at * 1000)
          )}`
        : "marker: none yet";
      return `
        <section class="camera-card">
          <div class="camera-preview">${preview}</div>
          <div class="camera-info">
            <strong>${camera.name}${active ? " (active)" : ""}</strong>
            <span>${camera.id}</span>
            <span>stream: ${camera.stream_url || "not set"}</span>
            <span>position: ${camera.position_x.toFixed(2)}, ${camera.position_y.toFixed(2)}, ${camera.position_z.toFixed(2)}</span>
            <span>${markerLine}</span>
            <button class="ghost marker-hit" data-camera-id="${camera.id}">Simulate marker seen here</button>
          </div>
        </section>
      `;
    })
    .join("");
}

function renderHistory() {
  const items = (state.history ?? []).slice().reverse().slice(0, 100);
  els.historyList.innerHTML = items
    .map((item) => {
      const time = format.format(new Date(item.at * 1000));
      const detail =
        item.type === "switch"
          ? `switched to ${item.camera_id} because ${item.reason}`
          : item.type === "person"
            ? `person moved to ${item.position.x.toFixed(2)}, ${item.position.y.toFixed(2)}, ${item.position.z.toFixed(2)}`
            : item.type === "camera"
              ? `camera ${item.camera_id} saved`
              : item.type === "zone"
                ? `zone ${item.zone_id} saved`
                : item.reason || item.type;
      return `
        <div class="history-item">
          <div>
            <strong>${item.type}</strong>
            <div class="meta">${detail}</div>
          </div>
          <div class="meta">${time}</div>
        </div>
      `;
    })
    .join("");
}

function renderMap() {
  const canvas = els.mapCanvas;
  const width = canvas.width;
  const height = canvas.height;
  const margin = 46;
  const world = {
    minX: -5,
    maxX: 10,
    minZ: -4,
    maxZ: 4
  };

  const toCanvas = (x, z) => ({
    x: margin + ((x - world.minX) / (world.maxX - world.minX)) * (width - margin * 2),
    y: height - margin - ((z - world.minZ) / (world.maxZ - world.minZ)) * (height - margin * 2)
  });

  ctx.clearRect(0, 0, width, height);

  const gradient = ctx.createLinearGradient(0, 0, width, height);
  gradient.addColorStop(0, "rgba(12, 24, 40, 1)");
  gradient.addColorStop(1, "rgba(5, 11, 19, 1)");
  ctx.fillStyle = gradient;
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = "rgba(255,255,255,0.06)";
  for (let i = 0; i <= 10; i += 1) {
    const x = margin + (i / 10) * (width - margin * 2);
    ctx.beginPath();
    ctx.moveTo(x, margin);
    ctx.lineTo(x, height - margin);
    ctx.stroke();
  }
  for (let i = 0; i <= 8; i += 1) {
    const y = margin + (i / 8) * (height - margin * 2);
    ctx.beginPath();
    ctx.moveTo(margin, y);
    ctx.lineTo(width - margin, y);
    ctx.stroke();
  }

  const roomRect = toCanvas(world.minX, world.minZ);
  const roomWidth = toCanvas(world.maxX, world.maxZ).x - roomRect.x;
  const roomHeight = roomRect.y - toCanvas(world.maxX, world.maxZ).y;
  ctx.strokeStyle = "rgba(142,240,184,0.25)";
  ctx.lineWidth = 2;
  ctx.strokeRect(roomRect.x, toCanvas(world.maxX, world.maxZ).y, roomWidth, roomHeight);

  for (const zone of state.zones ?? []) {
    const a = toCanvas(zone.box.min_x, zone.box.max_z);
    const b = toCanvas(zone.box.max_x, zone.box.min_z);
    const fill =
      zone.type === "overlap"
        ? "rgba(120,200,255,0.16)"
        : zone.cameras?.[0] === state.active_camera_id
          ? "rgba(142,240,184,0.18)"
          : "rgba(255,255,255,0.08)";
    ctx.fillStyle = fill;
    ctx.strokeStyle = zone.type === "overlap" ? "rgba(120,200,255,0.7)" : "rgba(255,255,255,0.35)";
    ctx.lineWidth = 1.5;
    ctx.beginPath();
    ctx.rect(a.x, a.y, b.x - a.x, b.y - a.y);
    ctx.fill();
    ctx.stroke();
    ctx.fillStyle = "#eaf4ff";
    ctx.font = "13px ui-sans-serif, system-ui";
    ctx.fillText(zone.name, a.x + 10, a.y + 20);
  }

  for (const camera of state.cameras ?? []) {
    const p = toCanvas(camera.position_x, camera.position_z);
    ctx.fillStyle = camera.color || "#78c8ff";
    ctx.beginPath();
    ctx.arc(p.x, p.y, camera.id === state.active_camera_id ? 8 : 6, 0, Math.PI * 2);
    ctx.fill();
    ctx.fillStyle = "#eaf4ff";
    ctx.fillText(camera.name, p.x + 10, p.y - 10);
  }

  const person = toCanvas(state.person.x, state.person.z);
  ctx.fillStyle = "#ff8f6b";
  ctx.beginPath();
  ctx.arc(person.x, person.y, 10, 0, Math.PI * 2);
  ctx.fill();
  ctx.strokeStyle = "rgba(255,143,107,0.6)";
  ctx.beginPath();
  ctx.arc(person.x, person.y, 20, 0, Math.PI * 2);
  ctx.stroke();
  ctx.fillStyle = "#fff6ef";
  ctx.fillText("You", person.x + 16, person.y + 4);
}

function render() {
  if (!state) return;
  const active = currentCamera();
  els.activeCamera.textContent = active ? active.name : "-";
  els.personPosition.textContent = `${state.person.x.toFixed(2)}, ${state.person.y.toFixed(2)}, ${state.person.z.toFixed(2)}`;
  els.modeState.textContent = state.last_switch_reason || "ready";
  els.ffmpegState.textContent = state.ffmpeg_available ? "ffmpeg: ready on server" : "ffmpeg: missing on server";
  updatePersonInputs(state.person);
  renderSignals();
  renderCameraGrid();
  renderHistory();
  syncConfigEditors();
  renderMap();
}

async function loadState() {
  state = await request("/api/state");
  queueRender();
}

async function sendPersonDelta(dx, dz) {
  const next = {
    x: Number(state.person.x + dx),
    y: Number(state.person.y),
    z: Number(state.person.z + dz),
    confidence: state.person.confidence,
    source: "manual"
  };
  await request("/api/person", {
    method: "POST",
    body: JSON.stringify(next)
  });
  await loadState();
}

async function saveConfig() {
  const settings = {
    switch_cooldown_ms: Number(els.switchCooldown.value || 700),
    idle_fallback_camera_id: els.idleFallback.value,
    apriltag_family: els.apriltagFamily.value.trim() || "tagStandard41h12",
    apriltag_scan_interval_s: Number(els.apriltagScanInterval.value || 1.0),
    apriltag_capture_width: Number(els.apriltagCaptureWidth.value || 640),
    apriltag_capture_height: Number(els.apriltagCaptureHeight.value || 360),
    apriltag_min_decision_margin: Number(els.apriltagMinDecisionMargin.value || 20.0)
  };
  const cameras = JSON.parse(els.camerasJson.value);
  const zones = JSON.parse(els.zonesJson.value);

  await request("/api/settings", {
    method: "POST",
    body: JSON.stringify(settings)
  });
  await request("/api/seed", {
    method: "POST",
    body: JSON.stringify({ cameras, zones })
  });
  await loadState();
}

function bindControls() {
  const updateFromSlider = async () => {
    const next = {
      x: Number(els.xRange.value),
      y: Number(els.yRange.value),
      z: Number(els.zRange.value),
      confidence: state.person.confidence,
      source: "manual"
    };
    await request("/api/person", { method: "POST", body: JSON.stringify(next) });
    await loadState();
  };

  els.xRange.addEventListener("input", updateFromSlider);
  els.yRange.addEventListener("input", updateFromSlider);
  els.zRange.addEventListener("input", updateFromSlider);

  els.saveConfig.addEventListener("click", () => {
    saveConfig().catch((error) => {
      alert(`Save failed: ${error.message}`);
    });
  });

  els.printMarker.addEventListener("click", () => {
    window.open("/marker-sheet", "_blank", "noopener");
  });

  els.resetDemo.addEventListener("click", async () => {
    await request("/api/reset", { method: "POST", body: "{}" });
    await loadState();
  });

  els.nudgeLeft.addEventListener("click", () => sendPersonDelta(-0.35, 0).catch(reportError));
  els.nudgeRight.addEventListener("click", () => sendPersonDelta(0.35, 0).catch(reportError));
  els.nudgeForward.addEventListener("click", () => sendPersonDelta(0, 0.35).catch(reportError));
  els.nudgeBack.addEventListener("click", () => sendPersonDelta(0, -0.35).catch(reportError));

  els.cameraGrid.addEventListener("click", async (event) => {
    const button = event.target.closest("button.marker-hit");
    if (!button) return;
    const cameraId = button.dataset.cameraId;
    try {
      await request("/api/marker-detection", {
        method: "POST",
        body: JSON.stringify({ camera_id: cameraId, marker_id: "head-marker", confidence: 1, source: "manual-sim" })
      });
      await loadState();
    } catch (error) {
      reportError(error);
    }
  });
}

function reportError(error) {
  alert(error.message);
}

bindControls();
async function init() {
  await loadState();
  setInterval(() => {
    loadState().catch(() => {});
  }, 1000);
}

init().catch((error) => {
  console.error(error);
});
