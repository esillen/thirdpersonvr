const els = {
  activeCamera: document.getElementById("activeCamera"),
  lastSwitch: document.getElementById("lastSwitch"),
  serverState: document.getElementById("serverState"),
  cameraGrid: document.getElementById("cameraGrid"),
  laptopCameraCard: document.getElementById("laptopCameraCard")
};

let state = null;
let initialRenderDone = false;
let laptopDevices = [];
const peerConnections = new Map();

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
    const body = await response.json().catch(async () => ({ detail: await response.text().catch(() => "") }));
    const message = body?.detail || `${response.status} ${response.statusText}`;
    throw new Error(message);
  }
  return response.json();
}

async function loadLaptopDevices() {
  const payload = await request("/api/webrtc/laptop-camera/devices");
  laptopDevices = payload.devices || [];
}

function fallbackCamera(slot) {
  return {
    id: slot.id,
    name: slot.label,
    source_kind: slot.id === "laptop-camera" ? "laptop" : "rtsp",
    stream_url: "",
    avfoundation_device: "0"
  };
}

function cameraBySlot(slotId) {
  const slot = slotDefinitions.find((candidate) => candidate.id === slotId) ?? { id: slotId, label: slotId };
  return state?.cameras?.find((camera) => camera.id === slotId) ?? fallbackCamera(slot);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function previewMarkup() {
  return `
    <div class="camera-preview-wrap" data-preview-key="">
      <video class="camera-preview-feed" autoplay playsinline muted></video>
      <div class="camera-preview-overlay">Connecting…</div>
    </div>
  `;
}

function renderCameraGrid() {
  els.cameraGrid.innerHTML = slotDefinitions
    .map((slot) => {
      const camera = cameraBySlot(slot.id);
      const active = camera.id === state.active_camera_id;
      return `
        <section class="camera-card" data-camera-id="${camera.id}">
          ${previewMarkup()}
          <div class="camera-info">
            <div class="camera-card-head">
              <strong>${slot.label}${active ? " · active" : ""}</strong>
              <span>${camera.id}</span>
            </div>
            <label>
              Name
              <input data-field="name" value="${escapeHtml(camera.name || slot.label)}" />
            </label>
            <label>
              Stream URL
              <input
                data-field="stream_url"
                value="${escapeHtml(camera.stream_url || "")}"
                placeholder="rtsp://192.168.1.10/stream1"
              />
            </label>
            <div class="camera-actions">
              <button class="primary apply-camera" data-camera-id="${camera.id}">
                ${active ? "Shown on headset" : "Save & show on headset"}
              </button>
            </div>
          </div>
        </section>
      `;
    })
    .join("");
  initialRenderDone = true;
}

function renderLaptopCameraCard() {
  if (!els.laptopCameraCard) return;
  const camera =
    state?.cameras?.find((item) => item.id === "laptop-camera") ??
    fallbackCamera({ id: "laptop-camera", label: "Laptop camera" });
  const active = camera.id === state.active_camera_id;
  const options = laptopDevices.length
    ? laptopDevices
        .map(
          (device) =>
            `<option value="${escapeHtml(device.index)}" ${device.index === camera.avfoundation_device ? "selected" : ""}>${escapeHtml(device.label)} (${escapeHtml(device.index)})</option>`
        )
        .join("")
    : `<option value="${escapeHtml(camera.avfoundation_device)}" selected>Camera ${escapeHtml(camera.avfoundation_device)}</option>`;
  els.laptopCameraCard.innerHTML = `
    <section class="camera-card camera-card-single" data-camera-id="${camera.id}">
      ${previewMarkup()}
      <div class="camera-info">
        <div class="camera-card-head">
          <strong>Laptop camera${active ? " · active" : ""}</strong>
          <span>${camera.id}</span>
        </div>
        <label>
          Camera device
          <select data-field="avfoundation_device">
            ${options}
          </select>
        </label>
        <label>
          Manual index
          <input data-field="avfoundation_device_manual" value="${escapeHtml(camera.avfoundation_device || "0")}" />
        </label>
        <div class="camera-actions">
          <button class="ghost refresh-laptop-devices" type="button">Refresh devices</button>
          <button class="primary use-laptop-camera" data-camera-id="${camera.id}" ${active ? "disabled" : ""}>
            ${active ? "Using laptop camera" : "Use laptop camera"}
          </button>
        </div>
      </div>
    </section>
  `;
}

function updateStatus() {
  const active = state?.cameras?.find((camera) => camera.id === state.active_camera_id);
  els.activeCamera.textContent = active?.name || state?.active_camera_id || "-";
  els.lastSwitch.textContent = state?.last_switch_at ? format.format(new Date(state.last_switch_at)) : "never";
  els.serverState.textContent = state?.webrtc_available ? "WebRTC ready" : "WebRTC missing";
}

function cameraKey(camera) {
  return `${camera.source_kind}:${camera.stream_url || ""}:${camera.avfoundation_device || ""}`;
}

async function connectCameraPreview(card, camera) {
  const previewWrap = card.querySelector(".camera-preview-wrap");
  const video = previewWrap?.querySelector("video");
  const overlay = previewWrap?.querySelector(".camera-preview-overlay");
  if (!previewWrap || !video || !overlay) return;

  if ((camera.source_kind === "rtsp" && !camera.stream_url) || (camera.source_kind === "laptop" && camera.id !== "laptop-camera")) {
    overlay.textContent = camera.source_kind === "rtsp" ? "Paste a stream URL to start." : "Unavailable.";
    overlay.classList.remove("hidden");
    return;
  }

  const key = cameraKey(camera);
  const existing = peerConnections.get(camera.id);
  if (
    previewWrap.dataset.previewKey === key &&
    existing &&
    (existing.pc.connectionState === "connecting" || existing.pc.connectionState === "connected")
  ) {
    return;
  }

  if (existing) {
    existing.pc.close();
    peerConnections.delete(camera.id);
  }

  previewWrap.dataset.previewKey = key;
  video.srcObject = null;
  overlay.textContent = "Connecting…";
  overlay.classList.remove("hidden");

  const pc = new RTCPeerConnection();
  peerConnections.set(camera.id, { pc, key });
  pc.addTransceiver("video", { direction: "recvonly" });

  pc.ontrack = (event) => {
    const [stream] = event.streams;
    video.srcObject = stream ?? new MediaStream([event.track]);
    video.play().catch(() => {});
    overlay.textContent = "Live";
    overlay.classList.add("hidden");
  };

  pc.onconnectionstatechange = () => {
    if (pc.connectionState === "connecting") {
      overlay.textContent = "Connecting…";
      overlay.classList.remove("hidden");
    } else if (pc.connectionState === "connected") {
      overlay.classList.add("hidden");
    } else if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
      if (peerConnections.get(camera.id)?.pc === pc) {
        peerConnections.delete(camera.id);
      }
      overlay.textContent = "Connection lost";
      overlay.classList.remove("hidden");
    } else if (pc.connectionState === "closed") {
      if (peerConnections.get(camera.id)?.pc === pc) {
        peerConnections.delete(camera.id);
      }
      overlay.textContent = "Stream closed";
      overlay.classList.remove("hidden");
    }
  };

  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const answer = await request(`/api/webrtc/cameras/${camera.id}/offer`, {
      method: "POST",
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type
      })
    });
    await pc.setRemoteDescription(answer);
  } catch (error) {
    if (peerConnections.get(camera.id)?.pc === pc) {
      peerConnections.delete(camera.id);
    }
    overlay.textContent = error.message;
    overlay.classList.remove("hidden");
  }
}

function syncCameraCard(slot) {
  const camera = cameraBySlot(slot.id);
  const card = els.cameraGrid.querySelector(`[data-camera-id="${camera.id}"]`);
  if (!card) return;
  const heading = card.querySelector(".camera-card-head strong");
  const button = card.querySelector("button.apply-camera");
  const nameInput = card.querySelector('input[data-field="name"]');
  const streamInput = card.querySelector('input[data-field="stream_url"]');
  if (heading) {
    heading.textContent = `${slot.label}${camera.id === state.active_camera_id ? " · active" : ""}`;
  }
  if (button) {
    button.disabled = camera.id === state.active_camera_id;
    button.textContent = camera.id === state.active_camera_id ? "Shown on headset" : "Save & show on headset";
  }
  if (nameInput && document.activeElement !== nameInput) {
    nameInput.value = camera.name || slot.label;
  }
  if (streamInput && document.activeElement !== streamInput) {
    streamInput.value = camera.stream_url || "";
  }
  connectCameraPreview(card, camera).catch(() => {});
}

function syncLaptopCard() {
  if (!els.laptopCameraCard) return;
  const camera =
    state?.cameras?.find((item) => item.id === "laptop-camera") ??
    fallbackCamera({ id: "laptop-camera", label: "Laptop camera" });
  const card = els.laptopCameraCard.querySelector(`[data-camera-id="${camera.id}"]`);
  if (!card) return;
  const heading = card.querySelector(".camera-card-head strong");
  const button = card.querySelector("button.use-laptop-camera");
  const deviceSelect = card.querySelector('select[data-field="avfoundation_device"]');
  const manualInput = card.querySelector('input[data-field="avfoundation_device_manual"]');
  if (heading) {
    heading.textContent = `Laptop camera${camera.id === state.active_camera_id ? " · active" : ""}`;
  }
  if (deviceSelect && document.activeElement !== deviceSelect) {
    const available = laptopDevices.some((device) => device.index === camera.avfoundation_device);
    deviceSelect.innerHTML = laptopDevices.length
      ? laptopDevices
          .map(
            (device) =>
              `<option value="${escapeHtml(device.index)}" ${device.index === camera.avfoundation_device ? "selected" : ""}>${escapeHtml(device.label)} (${escapeHtml(device.index)})</option>`
          )
          .join("")
      : `<option value="${escapeHtml(camera.avfoundation_device)}" selected>Camera ${escapeHtml(camera.avfoundation_device)}</option>`;
    if (!available && laptopDevices.length) {
      deviceSelect.insertAdjacentHTML(
        "afterbegin",
        `<option value="${escapeHtml(camera.avfoundation_device)}" selected>Current ${escapeHtml(camera.avfoundation_device)}</option>`
      );
    }
  }
  if (manualInput && document.activeElement !== manualInput) {
    manualInput.value = camera.avfoundation_device || "0";
  }
  if (button) {
    button.disabled = camera.id === state.active_camera_id;
    button.textContent = camera.id === state.active_camera_id ? "Using laptop camera" : "Use laptop camera";
  }
  connectCameraPreview(card, camera).catch(() => {});
}

function syncCards() {
  if (!initialRenderDone) return;
  for (const slot of slotDefinitions) {
    syncCameraCard(slot);
  }
  syncLaptopCard();
}

async function loadState({ rerender = false } = {}) {
  state = await request("/api/state");
  updateStatus();
  if (rerender || !initialRenderDone) {
    renderCameraGrid();
    renderLaptopCameraCard();
    syncCards();
  } else {
    syncCards();
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
    stream_url: streamUrl
  };
}

function readLaptopDevice() {
  const card = els.laptopCameraCard?.querySelector('[data-camera-id="laptop-camera"]');
  const deviceSelect = card?.querySelector('select[data-field="avfoundation_device"]');
  const manualInput = card?.querySelector('input[data-field="avfoundation_device_manual"]');
  return manualInput?.value?.trim() || deviceSelect?.value?.trim() || "0";
}

async function saveAndShow(cameraId) {
  const payload = readCameraForm(cameraId);
  if (!payload) return;
  await request(`/api/cameras/${cameraId}/activate`, {
    method: "POST",
    body: JSON.stringify(payload)
  });
  await loadState();
}

async function useLaptopCamera() {
  await request("/api/laptop-camera/activate", {
    method: "POST",
    body: JSON.stringify({
      avfoundation_device: readLaptopDevice()
    })
  });
  await loadState();
}

function bindControls() {
  els.cameraGrid.addEventListener("click", (event) => {
    const applyButton = event.target.closest("button.apply-camera");
    if (!applyButton) return;
    saveAndShow(applyButton.dataset.cameraId).catch(reportError);
  });

  els.laptopCameraCard?.addEventListener("click", (event) => {
    const refresh = event.target.closest("button.refresh-laptop-devices");
    if (refresh) {
      loadLaptopDevices()
        .then(() => loadState({ rerender: true }))
        .catch(reportError);
      return;
    }
    const button = event.target.closest("button.use-laptop-camera");
    if (!button) return;
    useLaptopCamera().catch(reportError);
  });

  els.laptopCameraCard?.addEventListener("change", (event) => {
    const select = event.target.closest('select[data-field="avfoundation_device"]');
    if (!select) return;
    useLaptopCamera().catch(reportError);
  });
}

function reportError(error) {
  alert(error.message);
}

bindControls();

async function init() {
  await loadState({ rerender: true });
  loadLaptopDevices()
    .then(() => {
      if (initialRenderDone) {
        syncLaptopCard();
      }
    })
    .catch(() => {
      laptopDevices = [];
      if (initialRenderDone) {
        syncLaptopCard();
      }
    });
  setInterval(() => {
    loadState().catch(() => {});
  }, 1500);
}

init().catch((error) => {
  console.error(error);
});
