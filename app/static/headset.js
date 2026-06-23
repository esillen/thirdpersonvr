const els = {
  cameraName: document.getElementById("cameraName"),
  cameraState: document.getElementById("cameraState"),
  streamFrame: document.getElementById("streamFrame"),
  streamFallback: document.getElementById("streamFallback"),
  zoneHint: document.getElementById("zoneHint"),
  fullscreenButton: document.getElementById("fullscreenButton")
};

let activeCameraId = null;
let activeCameraName = null;
let activeCameraSignature = null;
let activePeerConnection = null;

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

function cameraSignature(camera) {
  return `${camera.id}:${camera.source_kind}:${camera.camera_backend || ""}:${camera.stream_url || ""}:${camera.avfoundation_device || ""}`;
}

function setFallback(message) {
  els.streamFrame.srcObject = null;
  els.streamFallback.textContent = message;
  els.streamFallback.style.display = "grid";
  els.cameraState.textContent = message === "Waiting for the selected camera stream." ? "Connecting" : "Disconnected";
}

async function connectActiveCamera(camera) {
  const signature = cameraSignature(camera);
  if (
    signature === activeCameraSignature &&
    activePeerConnection &&
    (activePeerConnection.connectionState === "connecting" || activePeerConnection.connectionState === "connected")
  ) {
    return;
  }

  if (activePeerConnection) {
    activePeerConnection.close();
    activePeerConnection = null;
  }

  activeCameraId = camera.id;
  activeCameraName = camera.name;
  activeCameraSignature = signature;
  els.cameraName.textContent = camera.name;
  els.zoneHint.textContent = `Showing ${camera.name} from the server-selected camera.`;
  setFallback("Waiting for the selected camera stream.");

  const pc = new RTCPeerConnection();
  activePeerConnection = pc;
  pc.addTransceiver("video", { direction: "recvonly" });

  pc.ontrack = (event) => {
    const [stream] = event.streams;
    els.streamFrame.srcObject = stream ?? new MediaStream([event.track]);
    els.streamFrame.play().catch(() => {});
    els.streamFallback.style.display = "none";
    els.cameraState.textContent = "Live";
  };

  pc.onconnectionstatechange = () => {
    if (pc.connectionState === "connecting") {
      els.cameraState.textContent = "Connecting";
    } else if (pc.connectionState === "connected") {
      els.cameraState.textContent = "Live";
      els.streamFallback.style.display = "none";
    } else if (pc.connectionState === "failed" || pc.connectionState === "disconnected") {
      activePeerConnection = null;
      setFallback("Stream lost");
    } else if (pc.connectionState === "closed") {
      activePeerConnection = null;
      setFallback("Stream closed");
    }
  };

  try {
    const offer = await pc.createOffer();
    await pc.setLocalDescription(offer);
    const answer = await request("/api/webrtc/active-camera/offer", {
      method: "POST",
      body: JSON.stringify({
        sdp: pc.localDescription.sdp,
        type: pc.localDescription.type
      })
    });
    await pc.setRemoteDescription(answer);
  } catch (error) {
    if (activePeerConnection === pc) {
      activePeerConnection = null;
    }
    setFallback(error.message);
    throw error;
  }
}

async function loadActiveCamera() {
  try {
    const payload = await request("/api/active-camera");
    const camera = payload.camera;
    if (!camera) {
      els.cameraState.textContent = "No camera";
      setFallback("No active camera selected.");
      return;
    }
    const signature = cameraSignature(camera);
    if (camera.id !== activeCameraId || camera.name !== activeCameraName || signature !== activeCameraSignature) {
      await connectActiveCamera(camera);
    }
  } catch (error) {
    els.cameraState.textContent = "Disconnected";
    els.zoneHint.textContent = error.message;
    setFallback(error.message);
  }
}

async function goFullscreen() {
  if (document.fullscreenElement) {
    return document.exitFullscreen();
  }
  return document.documentElement.requestFullscreen?.();
}

els.fullscreenButton.addEventListener("click", () => {
  goFullscreen().catch(() => {});
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

async function init() {
  await loadActiveCamera();
  setInterval(() => {
    loadActiveCamera().catch(() => {});
  }, 1500);
}

init().catch((error) => {
  console.error(error);
});
