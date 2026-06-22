from __future__ import annotations

from typing import Literal, Optional

from pydantic import BaseModel, Field


class Box(BaseModel):
    min_x: float
    max_x: float
    min_y: float
    max_y: float
    min_z: float
    max_z: float


class Camera(BaseModel):
    id: str
    name: str
    stream_url: str = ""
    preview_mode: Literal["placeholder", "mjpeg"] = "placeholder"
    position_x: float = 0
    position_y: float = 2.4
    position_z: float = 0
    color: str = "#78c8ff"


class Zone(BaseModel):
    id: str
    name: str
    type: Literal["exclusive", "overlap"] = "exclusive"
    cameras: list[str] = Field(default_factory=list)
    box: Box


class Person(BaseModel):
    x: float = 0
    y: float = 1.7
    z: float = 0
    confidence: float = 1
    source: str = "manual"


class Settings(BaseModel):
    switch_cooldown_ms: int = 700
    idle_fallback_camera_id: str = "cam-a"
    apriltag_family: str = "tagStandard41h12"
    apriltag_scan_interval_s: float = 1.0
    apriltag_capture_width: int = 640
    apriltag_capture_height: int = 360
    apriltag_min_decision_margin: float = 20.0


class PersonUpdate(BaseModel):
    x: float
    y: float
    z: float
    confidence: float = 1
    source: str = "manual"


class CameraUpsert(BaseModel):
    id: Optional[str] = None
    name: str = "Camera"
    stream_url: str = ""
    preview_mode: Literal["placeholder", "mjpeg"] = "placeholder"
    position_x: float = 0
    position_y: float = 2.4
    position_z: float = 0
    color: str = "#78c8ff"


class ZoneUpsert(BaseModel):
    id: Optional[str] = None
    name: str = "Zone"
    type: Literal["exclusive", "overlap"] = "exclusive"
    cameras: list[str] = Field(default_factory=list)
    box: Box


class SettingsUpdate(BaseModel):
    switch_cooldown_ms: Optional[int] = None
    idle_fallback_camera_id: Optional[str] = None
    apriltag_family: Optional[str] = None
    apriltag_scan_interval_s: Optional[float] = None
    apriltag_capture_width: Optional[int] = None
    apriltag_capture_height: Optional[int] = None
    apriltag_min_decision_margin: Optional[float] = None


class SeedPayload(BaseModel):
    cameras: list[CameraUpsert] = Field(default_factory=list)
    zones: list[ZoneUpsert] = Field(default_factory=list)


class MarkerDetection(BaseModel):
    camera_id: str
    marker_id: str = "head-marker"
    confidence: float = 1.0
    source: str = "camera"
