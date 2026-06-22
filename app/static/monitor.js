const els = {
  activeCamera: document.getElementById("activeCamera"),
  lastSwitch: document.getElementById("lastSwitch"),
  ffmpegState: document.getElementById("ffmpegState"),
  cameraGrid: document.getElementById("cameraGrid")
};

let state = null;
let initialRenderDone = false;

const format = new Intl.DateTimeFormat(undefined, {
  hour: "2-digit",
  minute: "2-digit",
  second: "2-digit"
});

const slotDefinitions = [
  { id: "cam-a", label: "Camera 1" },
  { id: "cam-b", label: "Camera 2" }
];

async function request(path, options = {}) {
  const response = await fetch(path, {
    headers: { "content-type": "application/json" },
    ...options
  });
  if (!response.ok) {
    const message = await response.text().catch(() => "");
    throw new Error(message || `${response.status} ${response.statusText}`);
  }
  return response.json();
}

function fallbackCamera(slot) {
  return {
    id: slot.id,
    name: slot.label,
    stream_url: "",
    preview_mode: "placeholder"
  };
}

function cameraBySlot(slotId) {
  const slot = slotDefinitions.find((candidate) => candidate.id === slotId) ?? { id: slotId, label: slotId };
  return state?.cameras?.find((camera) => camera.id === slotId) ?? fallbackCamera(slot);
}

function previewMarkup(camera) {
  const source = camera.stream_url && state.ffmpeg_available ? `/api/cameras/${camera.id}/preview.mjpg` : "";
  return {
    source,
    html:
      source
        ? `<img src="${source}" alt="${camera.name} live preview" />`
        : `
          <div class="camera-preview empty">
            <div>
              <strong>No live preview yet</strong>
              <div>Paste the stream address below, then apply it to the headset.</div>
            </div>
          </div>
        `
  };
}

function cameraStatus(cameraId) {
  return state?.camera_statuses?.[cameraId] ?? null;
}

function cameraStatusLabel(cameraId) {
  const status = cameraStatus(cameraId);
  if (!status || status.reachable === undefined) {
    return "Not checked";
  }
  if (status.reachable) {
    return status.transport ? `Found via ${status.transport}` : "Found";
  }
  return status.error ? `Not found: ${status.error}` : "Not found";
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function renderCameraGrid() {
  els.cameraGrid.innerHTML = slotDefinitions
    .map((slot) => {
      const camera = cameraBySlot(slot.id);
      const preview = previewMarkup(camera);
      const active = camera.id === state.active_camera_id;
      return `
        <section class="camera-card" data-camera-id="${camera.id}">
          <div class="camera-preview-wrap" data-preview-source="${escapeHtml(preview.source)}">
            ${preview.html}
          </div>
          <div class="camera-info">
            <div class="camera-card-head">
              <strong>${slot.label}${active ? " · active" : ""}</strong>
              <span>${camera.id}</span>
            </div>
            <div class="camera-status">${cameraStatusLabel(camera.id)}</div>
            <label>
              Name
              <input data-field="name" value="${escapeHtml(camera.name || slot.label)}" />
            </label>
            <label>
              Stream URL
              <input
                data-field="stream_url"
                value="${escapeHtml(camera.stream_url || "")}"
                placeholder="rtsp://192.168.1.10:554/stream1"
              />
            </label>
            <div class="camera-actions">
              <button class="primary apply-camera" data-camera-id="${camera.id}">
                ${active ? "Showing on headset" : "Save & show on headset"}
              </button>
            </div>
          </div>
        </section>
      `;
    })
    .join("");
  initialRenderDone = true;
}

function updateStatus() {
  const active = state?.cameras?.find((camera) => camera.id === state.active_camera_id);
  els.activeCamera.textContent = active?.name || state?.active_camera_id || "-";
  els.lastSwitch.textContent = state?.last_switch_at ? format.format(new Date(state.last_switch_at)) : "never";
  els.ffmpegState.textContent = state?.ffmpeg_available ? "ffmpeg ready" : "ffmpeg missing";
}

function updateActiveCards() {
  if (!initialRenderDone) return;
  for (const slot of slotDefinitions) {
    const camera = cameraBySlot(slot.id);
    const card = els.cameraGrid.querySelector(`[data-camera-id="${camera.id}"]`);
    if (!card) continue;
    const heading = card.querySelector(".camera-card-head strong");
    const status = card.querySelector(".camera-status");
    const button = card.querySelector("button.apply-camera");
    if (heading) {
      heading.textContent = `${slot.label}${camera.id === state.active_camera_id ? " · active" : ""}`;
    }
    if (button) {
      button.disabled = camera.id === state.active_camera_id;
      button.textContent = camera.id === state.active_camera_id ? "Showing on headset" : "Save & show on headset";
    }
    if (status) {
      status.textContent = cameraStatusLabel(camera.id);
    }
    const previewWrap = card.querySelector(".camera-preview-wrap");
    if (previewWrap) {
      const preview = previewMarkup(camera);
      if (previewWrap.dataset.previewSource !== preview.source) {
        previewWrap.dataset.previewSource = preview.source;
        previewWrap.innerHTML = preview.html;
      }
    }
  }
}

async function loadState({ rerender = false } = {}) {
  state = await request("/api/state");
  updateStatus();
  if (rerender || !initialRenderDone) {
    renderCameraGrid();
  } else {
    updateActiveCards();
  }
}

function readCameraForm(cameraId) {
  const card = els.cameraGrid.querySelector(`[data-camera-id="${cameraId}"]`);
  if (!card) return null;
  const name = card.querySelector('[data-field="name"]')?.value.trim() || "Camera";
  const streamUrl = card.querySelector('[data-field="stream_url"]')?.value.trim() || "";
  return {
    id: cameraId,
    name,
    stream_url: streamUrl,
    preview_mode: streamUrl ? "mjpeg" : "placeholder"
  };
}

async function saveAndShow(cameraId) {
  const payload = readCameraForm(cameraId);
  if (!payload) return;
  await request(`/api/cameras/${cameraId}/activate`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
  await loadState({ rerender: true });
}

function bindControls() {
  els.cameraGrid.addEventListener("click", (event) => {
    const applyButton = event.target.closest("button.apply-camera");
    if (!applyButton) return;
    saveAndShow(applyButton.dataset.cameraId).catch(reportError);
  });
}

function reportError(error) {
  alert(error.message);
}

bindControls();

async function init() {
  await loadState({ rerender: true });
  setInterval(() => {
    loadState().catch(() => {});
  }, 1500);
}

init().catch((error) => {
  console.error(error);
});
