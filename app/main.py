from __future__ import annotations

import shutil
import time

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, STATE_FILE
from app.models import CameraSelect, CameraUpsert, PersonUpdate, SeedPayload, SettingsUpdate, ZoneUpsert
from app.store import StateStore
from app.streaming import PreviewManager, probe_stream_url, stream_mjpeg


app = FastAPI(title="Third Person View Prototype")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

STREAM_HEADERS = {
    "Cache-Control": "no-cache, no-store, must-revalidate",
    "Pragma": "no-cache",
    "X-Accel-Buffering": "no",
}

store = StateStore(STATE_FILE)
preview_manager = PreviewManager()

store.load()
store.set_ffmpeg_available(shutil.which("ffmpeg") is not None)


@app.get("/")
def index():
    return RedirectResponse(url="/monitor", status_code=307)


@app.get("/monitor")
def monitor():
    return FileResponse(STATIC_DIR / "monitor.html")


@app.get("/headset")
def headset():
    return FileResponse(STATIC_DIR / "headset.html")


@app.get("/manifest.webmanifest")
def manifest():
    return FileResponse(STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json")


@app.get("/sw.js")
def service_worker():
    return FileResponse(STATIC_DIR / "sw.js", media_type="application/javascript")


@app.get("/api/state")
def get_state():
    return JSONResponse(store.snapshot("read"))


@app.get("/api/active-camera")
def get_active_camera():
    active_camera = next((item for item in store.cameras if item.id == store.active_camera_id), None)
    if active_camera is None:
        raise HTTPException(status_code=404, detail="no active camera")
    return JSONResponse({"camera": active_camera.model_dump(), "active_camera_id": store.active_camera_id})


@app.post("/api/active-camera")
def set_active_camera(payload: CameraSelect):
    try:
        snapshot = store.select_camera(payload, "manual-select")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return JSONResponse(snapshot)


@app.post("/api/person")
def set_person(payload: PersonUpdate):
    return JSONResponse(store.update_person(payload, "api-person"))


@app.post("/api/simulate")
def simulate(payload: PersonUpdate):
    return JSONResponse(store.update_person(payload, "simulate"))


@app.post("/api/cameras")
def upsert_camera(payload: CameraUpsert):
    camera = store.upsert_camera(payload)
    return JSONResponse({"ok": True, "camera": camera.model_dump()})


@app.post("/api/cameras/{camera_id}/activate")
def activate_camera(camera_id: str, payload: CameraUpsert):
    camera_payload = payload.model_copy(update={"id": camera_id})
    probe = probe_stream_url(camera_payload.stream_url)
    store.set_camera_status(
        camera_id,
        {
            "reachable": bool(probe["reachable"]),
            "checked_at": time.time(),
            "error": probe.get("error", ""),
            "transport": probe.get("transport", ""),
        },
    )
    if not probe["reachable"] and camera_payload.stream_url:
        raise HTTPException(status_code=422, detail=f"camera stream not reachable: {probe.get('error', 'unknown error')}")
    camera = store.upsert_camera(camera_payload)
    try:
        snapshot = store.select_camera(CameraSelect(camera_id=camera.id), "manual-select")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return JSONResponse({"ok": True, "camera": camera.model_dump(), "probe": probe, "state": snapshot})


@app.post("/api/zones")
def upsert_zone(payload: ZoneUpsert):
    zone = store.upsert_zone(payload)
    return JSONResponse({"ok": True, "zone": zone.model_dump()})


@app.post("/api/settings")
def update_settings(payload: SettingsUpdate):
    settings = store.update_settings(payload)
    return JSONResponse({"ok": True, "settings": settings.model_dump()})


@app.post("/api/seed")
def seed(payload: SeedPayload):
    store.seed(payload.cameras, payload.zones)
    return JSONResponse({"ok": True})


@app.post("/api/reset")
def reset():
    store.reset()
    return JSONResponse({"ok": True, "state": store.snapshot("reset")})


@app.get("/api/cameras/{camera_id}/preview.mjpg")
def preview(camera_id: str):
    camera = next((item for item in store.cameras if item.id == camera_id), None)
    if camera is None:
        raise HTTPException(status_code=404, detail="camera not found")
    if not camera.stream_url or not store.ffmpeg_available:
        raise HTTPException(status_code=409, detail="preview unavailable")
    transport = store.camera_statuses.get(camera_id, {}).get("transport", "auto")
    streamer = preview_manager.get(camera, transport)
    return StreamingResponse(
        stream_mjpeg(streamer),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers=STREAM_HEADERS,
    )


@app.get("/api/active-camera/preview.mjpg")
def active_preview():
    active_camera = next((item for item in store.cameras if item.id == store.active_camera_id), None)
    if active_camera is None:
        raise HTTPException(status_code=404, detail="no active camera")
    if not active_camera.stream_url or not store.ffmpeg_available:
        raise HTTPException(status_code=409, detail="preview unavailable")
    transport = store.camera_statuses.get(active_camera.id, {}).get("transport", "auto")
    streamer = preview_manager.get(active_camera, transport)
    return StreamingResponse(
        stream_mjpeg(streamer),
        media_type="multipart/x-mixed-replace; boundary=frame",
        headers=STREAM_HEADERS,
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}
