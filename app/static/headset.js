const els = {
  cameraName: document.getElementById("cameraName"),
  cameraState: document.getElementById("cameraState"),
  streamFrame: document.getElementById("streamFrame"),
  streamShell: document.getElementById("streamShell"),
  streamFallback: document.getElementById("streamFallback"),
  zoneHint: document.getElementById("zoneHint"),
  fullscreenButton: document.getElementById("fullscreenButton")
};

let activeCameraId = null;
let activeCameraName = null;
let activeCameraStreamUrl = null;

async function request(path) {
  const response = await fetch(path);
  if (!response.ok) {
    throw new Error(`${response.status} ${response.statusText}`);
  }
  return response.json();
}

function setStream(camera) {
  if (!camera) return;
  const cacheBuster = Date.now();
  const source = camera.stream_url
    ? `/api/cameras/${camera.id}/preview.mjpg?ts=${cacheBuster}`
    : "";
  activeCameraId = camera.id;
  activeCameraName = camera.name;
  activeCameraStreamUrl = camera.stream_url || "";
  els.cameraName.textContent = camera.name;
  els.cameraState.textContent = camera.stream_url ? "Live" : "No stream";
  els.zoneHint.textContent = `Showing ${camera.name} from the server-selected camera.`;
  if (camera.stream_url) {
    els.streamFrame.src = source;
    els.streamFrame.style.display = "block";
    els.streamFallback.style.display = "none";
  } else {
    els.streamFrame.removeAttribute("src");
    els.streamFrame.style.display = "none";
    els.streamFallback.style.display = "grid";
  }
}

async function loadActiveCamera() {
  try {
    const payload = await request("/api/active-camera");
    const camera = payload.camera;
    if (!camera) {
      els.cameraState.textContent = "No camera";
      return;
    }
    if (
      camera.id !== activeCameraId ||
      camera.name !== activeCameraName ||
      (camera.stream_url || "") !== activeCameraStreamUrl
    ) {
      setStream(camera);
    }
    if (!camera.stream_url) {
      els.cameraState.textContent = "No stream";
    }
  } catch (error) {
    els.cameraState.textContent = "Disconnected";
    els.zoneHint.textContent = error.message;
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
