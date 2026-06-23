from __future__ import annotations

import platform

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.config import STATIC_DIR, STATE_FILE
from app.models import CameraSelect, CameraUpsert, LaptopCameraUpdate, PersonUpdate, SeedPayload, SettingsUpdate, ZoneUpsert
from app.store import StateStore
from app.webrtc import WebRTCManager, WebRTCOffer


app = FastAPI(title="Third Person View Prototype")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

store = StateStore(STATE_FILE)
webrtc_manager = WebRTCManager()

store.load()
store.set_webrtc_available(True)


@app.on_event("shutdown")
async def shutdown():
    await webrtc_manager.close_all()


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
    camera = store.upsert_camera(camera_payload)
    try:
        snapshot = store.select_camera(CameraSelect(camera_id=camera.id), "manual-select")
    except ValueError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    return JSONResponse({"ok": True, "camera": camera.model_dump(), "state": snapshot})


@app.post("/api/laptop-camera/activate")
def activate_laptop_camera(payload: LaptopCameraUpdate | None = None):
    backend = payload.camera_backend if payload else (
        "dshow" if platform.system() == "Windows" else "v4l2" if platform.system() == "Linux" else "avfoundation"
    )
    device = (payload.avfoundation_device if payload else "0") or "0"
    camera_payload = CameraUpsert(
        id="laptop-camera",
        name="Laptop Camera",
        source_kind="laptop",
        camera_backend=backend,
        avfoundation_device=device,
        stream_url="",
    )
    camera = store.upsert_camera(camera_payload)
    snapshot = store.select_camera(CameraSelect(camera_id=camera.id), "laptop-camera")
    return JSONResponse({"ok": True, "camera": camera.model_dump(), "state": snapshot})


@app.post("/api/webrtc/cameras/{camera_id}/offer")
async def camera_webrtc_offer(camera_id: str, payload: WebRTCOffer):
    camera = next((item for item in store.cameras if item.id == camera_id), None)
    if camera is None:
        raise HTTPException(status_code=404, detail="camera not found")
    try:
        answer = await webrtc_manager.create_answer(camera, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return JSONResponse({"ok": True, "camera_id": camera_id, **answer})


@app.post("/api/webrtc/active-camera/offer")
async def active_camera_webrtc_offer(payload: WebRTCOffer):
    active_camera = next((item for item in store.cameras if item.id == store.active_camera_id), None)
    if active_camera is None:
        raise HTTPException(status_code=404, detail="no active camera")
    try:
        answer = await webrtc_manager.create_answer(active_camera, payload)
    except RuntimeError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    return JSONResponse({"ok": True, "camera_id": active_camera.id, **answer})


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


@app.get("/healthz")
def healthz():
    return {"ok": True}
