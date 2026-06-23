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
    source_kind: Literal["rtsp", "laptop"] = "rtsp"
    camera_backend: Literal["avfoundation", "dshow", "v4l2"] = "avfoundation"
    stream_url: str = ""
    avfoundation_device: str = "0"


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


class PersonUpdate(BaseModel):
    x: float
    y: float
    z: float
    confidence: float = 1
    source: str = "manual"


class CameraUpsert(BaseModel):
    id: Optional[str] = None
    name: str = "Camera"
    source_kind: Literal["rtsp", "laptop"] = "rtsp"
    camera_backend: Literal["avfoundation", "dshow", "v4l2"] = "avfoundation"
    stream_url: str = ""
    avfoundation_device: str = "0"


class ZoneUpsert(BaseModel):
    id: Optional[str] = None
    name: str = "Zone"
    type: Literal["exclusive", "overlap"] = "exclusive"
    cameras: list[str] = Field(default_factory=list)
    box: Box


class SettingsUpdate(BaseModel):
    switch_cooldown_ms: Optional[int] = None
    idle_fallback_camera_id: Optional[str] = None


class SeedPayload(BaseModel):
    cameras: list[CameraUpsert] = Field(default_factory=list)
    zones: list[ZoneUpsert] = Field(default_factory=list)


class CameraSelect(BaseModel):
    camera_id: str


class WebRTCOffer(BaseModel):
    sdp: str
    type: Literal["offer"] = "offer"


class LaptopCameraUpdate(BaseModel):
    camera_backend: Literal["avfoundation", "dshow", "v4l2"] = "avfoundation"
    avfoundation_device: str = "0"
