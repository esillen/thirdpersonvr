from __future__ import annotations

import shutil

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, STATE_FILE
from app.models import CameraUpsert, MarkerDetection, PersonUpdate, SeedPayload, SettingsUpdate, ZoneUpsert
from app.marker_scanner import MarkerScannerService
from app.store import StateStore
from app.streaming import PreviewManager, stream_mjpeg


app = FastAPI(title="Third Person View Prototype")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

store = StateStore(STATE_FILE)
preview_manager = PreviewManager()
marker_scanner = MarkerScannerService(store)

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


@app.get("/marker-sheet")
def marker_sheet():
    return FileResponse(STATIC_DIR / "marker-sheet.html")


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


@app.post("/api/marker-detection")
def marker_detection(payload: MarkerDetection):
    try:
        snapshot = store.detect_marker(payload, "api-marker")
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
    streamer = preview_manager.get(camera)
    return StreamingResponse(
        stream_mjpeg(streamer),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/api/active-camera/preview.mjpg")
def active_preview():
    active_camera = next((item for item in store.cameras if item.id == store.active_camera_id), None)
    if active_camera is None:
        raise HTTPException(status_code=404, detail="no active camera")
    if not active_camera.stream_url or not store.ffmpeg_available:
        raise HTTPException(status_code=409, detail="preview unavailable")
    streamer = preview_manager.get(active_camera)
    return StreamingResponse(
        stream_mjpeg(streamer),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.on_event("startup")
def startup_marker_scanner():
    marker_scanner.start()


@app.on_event("shutdown")
def shutdown_marker_scanner():
    marker_scanner.stop()
