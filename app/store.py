from __future__ import annotations

import copy
import json
import threading
import time
from pathlib import Path
from typing import Any

from app.defaults import default_cameras, default_person, default_settings, default_zones
from app.models import Camera, CameraSelect, CameraUpsert, Person, PersonUpdate, Settings, SettingsUpdate, Zone, ZoneUpsert


def _dump(model):
    return model.model_dump()


def _camera_from_upsert(payload: CameraUpsert) -> Camera:
    camera_id = payload.id or f"cam-{int(time.time() * 1000)}"
    return Camera(id=camera_id, name=payload.name, stream_url=payload.stream_url, preview_mode=payload.preview_mode)


def _zone_from_upsert(payload: ZoneUpsert) -> Zone:
    zone_id = payload.id or f"zone-{int(time.time() * 1000)}"
    return Zone(id=zone_id, name=payload.name, type=payload.type, cameras=list(payload.cameras), box=payload.box)


def _normalize_camera_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id", f"cam-{int(time.time() * 1000)}"),
        "name": payload.get("name", "Camera"),
        "stream_url": payload.get("stream_url", payload.get("streamUrl", "")),
        "preview_mode": payload.get("preview_mode", payload.get("previewMode", "placeholder")),
    }


def _normalize_box_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "min_x": payload.get("min_x", payload.get("minX", 0)),
        "max_x": payload.get("max_x", payload.get("maxX", 0)),
        "min_y": payload.get("min_y", payload.get("minY", 0)),
        "max_y": payload.get("max_y", payload.get("maxY", 0)),
        "min_z": payload.get("min_z", payload.get("minZ", 0)),
        "max_z": payload.get("max_z", payload.get("maxZ", 0)),
    }


def _normalize_zone_payload(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": payload.get("id", f"zone-{int(time.time() * 1000)}"),
        "name": payload.get("name", "Zone"),
        "type": payload.get("type", "exclusive"),
        "cameras": list(payload.get("cameras", [])),
        "box": _normalize_box_payload(payload.get("box", {})),
    }


class StateStore:
    def __init__(self, state_file: Path):
        self.state_file = state_file
        self.lock = threading.RLock()
        self.cameras: list[Camera] = default_cameras()
        self.zones: list[Zone] = default_zones()
        self.person: Person = default_person()
        self.settings: Settings = default_settings()
        self.active_camera_id: str = self.cameras[0].id if self.cameras else ""
        self.last_switch_at: float = 0.0
        self.last_switch_reason: str = "initial"
        self.camera_statuses: dict[str, dict[str, Any]] = {}
        self.history: list[dict[str, Any]] = []
        self.ffmpeg_available: bool = False

    def load(self) -> None:
        if not self.state_file.exists():
            self.save()
            return
        with self.state_file.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
        with self.lock:
            camera_items = payload.get("cameras")
            if camera_items is None:
                camera_items = _dump_list(default_cameras())
            self.cameras = [Camera(**_normalize_camera_payload(item)) for item in camera_items]

            zone_items = payload.get("zones")
            if zone_items is None:
                zone_items = _dump_list(default_zones())
            self.zones = [Zone(**_normalize_zone_payload(item)) for item in zone_items]

            person_payload = payload.get("person", _dump(default_person()))
            self.person = Person(**person_payload)

            settings_payload = payload.get("settings", _dump(default_settings()))
            self.settings = Settings(
                switch_cooldown_ms=settings_payload.get("switch_cooldown_ms", settings_payload.get("switchCooldownMs", 700)),
                idle_fallback_camera_id=settings_payload.get(
                    "idle_fallback_camera_id", settings_payload.get("idleFallbackCameraId", "cam-a")
                ),
            )
            self.active_camera_id = payload.get("active_camera_id", payload.get("activeCameraId", self.active_camera_id))
            self.last_switch_at = float(payload.get("last_switch_at", payload.get("lastSwitchAt", self.last_switch_at)))
            self.last_switch_reason = payload.get(
                "last_switch_reason", payload.get("lastSwitchReason", self.last_switch_reason)
            )
            self.camera_statuses = dict(payload.get("camera_statuses", payload.get("cameraStatuses", {})))
            self.history = list(payload.get("history", self.history))[-200:]

    def save(self) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        with self.lock:
            payload = {
                "cameras": [_dump(camera) for camera in self.cameras],
                "zones": [_dump(zone) for zone in self.zones],
                "person": _dump(self.person),
                "settings": _dump(self.settings),
                "active_camera_id": self.active_camera_id,
                "last_switch_at": self.last_switch_at,
                "last_switch_reason": self.last_switch_reason,
                "camera_statuses": copy.deepcopy(self.camera_statuses),
                "history": self.history[-200:],
            }
        with self.state_file.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, indent=2)

    def snapshot(self, reason: str = "read") -> dict[str, Any]:
        with self.lock:
            return {
                "reason": reason,
                "cameras": [_dump(camera) for camera in self.cameras],
                "zones": [_dump(zone) for zone in self.zones],
                "person": _dump(self.person),
                "settings": _dump(self.settings),
                "active_camera_id": self.active_camera_id,
                "last_switch_at": self.last_switch_at,
                "last_switch_reason": self.last_switch_reason,
                "camera_statuses": copy.deepcopy(self.camera_statuses),
                "history": copy.deepcopy(self.history[-100:]),
                "ffmpeg_available": self.ffmpeg_available,
            }

    def record(self, event: dict[str, Any]) -> None:
        event = {"id": f"evt-{int(time.time() * 1000)}", "at": time.time(), **event}
        self.history.append(event)
        self.history = self.history[-200:]

    def set_ffmpeg_available(self, available: bool) -> None:
        with self.lock:
            self.ffmpeg_available = available

    def set_camera_status(self, camera_id: str, status: dict[str, Any]) -> None:
        with self.lock:
            self.camera_statuses[camera_id] = {"camera_id": camera_id, **status}
            self.save()

    def update_person(self, payload: PersonUpdate, reason: str = "manual") -> dict[str, Any]:
        with self.lock:
            self.person = Person(**payload.model_dump())
            self.record({"type": "person", "reason": reason, "position": _dump(self.person)})
            self.save()
            return self.snapshot(reason)

    def upsert_camera(self, payload: CameraUpsert) -> Camera:
        camera = _camera_from_upsert(payload)
        with self.lock:
            index = next((i for i, existing in enumerate(self.cameras) if existing.id == camera.id), None)
            if index is None:
                self.cameras.append(camera)
            else:
                self.cameras[index] = camera
            self.record({"type": "camera", "reason": "upsert", "camera_id": camera.id, "camera": _dump(camera)})
            self.save()
            return camera

    def upsert_zone(self, payload: ZoneUpsert) -> Zone:
        zone = _zone_from_upsert(payload)
        with self.lock:
            index = next((i for i, existing in enumerate(self.zones) if existing.id == zone.id), None)
            if index is None:
                self.zones.append(zone)
            else:
                self.zones[index] = zone
            self.record({"type": "zone", "reason": "upsert", "zone_id": zone.id, "zone": _dump(zone)})
            self.save()
            return zone

    def update_settings(self, payload: SettingsUpdate) -> Settings:
        with self.lock:
            updates = payload.model_dump(exclude_none=True)
            data = self.settings.model_dump()
            data.update(updates)
            self.settings = Settings(**data)
            self.save()
            return self.settings

    def seed(self, cameras: list[CameraUpsert], zones: list[ZoneUpsert]) -> None:
        with self.lock:
            self.cameras = [_camera_from_upsert(camera) for camera in cameras] or default_cameras()
            self.zones = [_zone_from_upsert(zone) for zone in zones] or default_zones()
            if self.active_camera_id not in {camera.id for camera in self.cameras} and self.cameras:
                self.active_camera_id = self.cameras[0].id
            self.camera_statuses = {camera.id: self.camera_statuses.get(camera.id, {}) for camera in self.cameras}
            self.record({"type": "seed", "reason": "seed"})
            self.save()

    def reset(self) -> None:
        with self.lock:
            self.cameras = default_cameras()
            self.zones = default_zones()
            self.person = default_person()
            self.settings = default_settings()
            self.active_camera_id = self.cameras[0].id if self.cameras else ""
            self.last_switch_at = 0.0
            self.last_switch_reason = "reset"
            self.camera_statuses = {}
            self.history = []
            self.save()

    def select_camera(self, payload: CameraSelect, reason: str = "manual-select") -> dict[str, Any]:
        with self.lock:
            camera = next((item for item in self.cameras if item.id == payload.camera_id), None)
            if camera is None:
                raise ValueError(f"Unknown camera: {payload.camera_id}")
            self.active_camera_id = camera.id
            self.last_switch_at = time.time() * 1000
            self.last_switch_reason = reason
            self.record(
                {
                    "type": "switch",
                    "reason": reason,
                    "camera_id": camera.id,
                    "camera_name": camera.name,
                }
            )
            self.save()
            return self.snapshot(reason)


def _dump_list(items):
    return [item.model_dump() for item in items]
