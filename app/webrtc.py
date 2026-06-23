from __future__ import annotations

import asyncio
import platform
import threading
import time
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Literal

from aiortc import MediaStreamError, MediaStreamTrack, RTCPeerConnection, RTCSessionDescription
from aiortc.contrib.media import MediaPlayer, MediaRelay
from av import VideoFrame
from pydantic import BaseModel

from app.models import Camera

VIDEO_WIDTH = 854
VIDEO_HEIGHT = 480
VIDEO_FPS = 10


class WebRTCOffer(BaseModel):
    sdp: str
    type: Literal["offer"] = "offer"


class ThrottledResizeVideoTrack(MediaStreamTrack):
    kind = "video"

    def __init__(self, source: MediaStreamTrack, width: int = VIDEO_WIDTH, height: int = VIDEO_HEIGHT, fps: int = VIDEO_FPS):
        super().__init__()
        self.source = source
        self.width = width
        self.height = height
        self.fps = fps
        self.interval = 1.0 / fps
        self.next_frame_at = time.monotonic()
        self.sequence = 0

    async def recv(self):
        if self.readyState != "live":
            raise MediaStreamError

        frame = await self.source.recv()

        now = time.monotonic()
        if now < self.next_frame_at:
            await asyncio.sleep(self.next_frame_at - now)
        self.next_frame_at = max(self.next_frame_at + self.interval, time.monotonic() + self.interval)

        if isinstance(frame, VideoFrame):
            if frame.width != self.width or frame.height != self.height:
                frame = frame.reformat(width=self.width, height=self.height)
            frame.pts = self.sequence
            frame.time_base = Fraction(1, self.fps)
            self.sequence += 1
        return frame


def _camera_source_key(camera: Camera) -> str:
    if camera.source_kind == "laptop":
        return f"{camera.id}:laptop:{camera.camera_backend}:{camera.avfoundation_device or '0'}"
    return f"{camera.id}:rtsp:{camera.stream_url}"


def _default_laptop_backend() -> str:
    system = platform.system()
    if system == "Windows":
        return "dshow"
    if system == "Linux":
        return "v4l2"
    return "avfoundation"


def _camera_player(camera: Camera) -> MediaPlayer:
    if camera.source_kind == "laptop":
        backend = camera.camera_backend or _default_laptop_backend()
        device = camera.avfoundation_device or "0"
        options = {"video_size": f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}", "framerate": str(VIDEO_FPS)}
        if backend == "avfoundation":
            attempts = [f"{device}:none", device, "default:none"]
        elif backend == "dshow":
            normalized = device if device.startswith("video=") else f"video={device}"
            attempts = [normalized, device]
        elif backend == "v4l2":
            attempts = [device]
        else:
            raise RuntimeError(f"unsupported laptop camera backend: {backend}")
        last_error: Exception | None = None
        for input_name in attempts:
            try:
                return MediaPlayer(input_name, format=backend, options=options, timeout=5)
            except Exception as error:  # noqa: BLE001
                last_error = error
        raise RuntimeError(
            "laptop camera unavailable on the server. "
            f"Use the {backend} backend with a valid device selector. "
            f"Last error: {last_error}"
        )

    try:
        return MediaPlayer(
            camera.stream_url,
            options={
                "rtsp_transport": "tcp",
                "fflags": "nobuffer",
                "flags": "low_delay",
                "probesize": "32",
                "analyzeduration": "0",
            },
            timeout=5,
        )
    except Exception as error:  # noqa: BLE001
        raise RuntimeError(f"camera stream unavailable: {error}") from error


@dataclass
class CameraWebRTCSource:
    camera: Camera
    player: MediaPlayer = field(init=False)
    source_track: MediaStreamTrack | None = field(init=False, default=None)
    relay: MediaRelay = field(default_factory=MediaRelay)
    throttled_track: ThrottledResizeVideoTrack = field(init=False)

    def __post_init__(self) -> None:
        self.player = _camera_player(self.camera)
        self.source_track = self.player.video
        if self.source_track is None:
            raise RuntimeError("camera does not expose a video track")
        self.throttled_track = ThrottledResizeVideoTrack(self.source_track)

    def create_track(self) -> MediaStreamTrack:
        return self.relay.subscribe(self.throttled_track)

    def close(self) -> None:
        if self.throttled_track is not None:
            self.throttled_track.stop()
        if self.source_track is not None:
            self.source_track.stop()


class WebRTCManager:
    def __init__(self) -> None:
        self.sources: dict[str, CameraWebRTCSource] = {}
        self.camera_keys: dict[str, str] = {}
        self.peer_connections: set[RTCPeerConnection] = set()
        self.lock = threading.Lock()

    def _get_source(self, camera: Camera) -> CameraWebRTCSource:
        key = _camera_source_key(camera)
        with self.lock:
            previous_key = self.camera_keys.get(camera.id)
            if previous_key and previous_key != key:
                previous_source = self.sources.pop(previous_key, None)
                if previous_source is not None:
                    previous_source.close()

            source = self.sources.get(key)
            if source is None:
                try:
                    source = CameraWebRTCSource(camera)
                except Exception as error:  # noqa: BLE001
                    raise RuntimeError(str(error)) from error
                self.sources[key] = source
            self.camera_keys[camera.id] = key
            return source

    async def create_answer(self, camera: Camera, offer: WebRTCOffer) -> dict[str, str]:
        pc = RTCPeerConnection()
        try:
            source = self._get_source(camera)
            pc.addTrack(source.create_track())
        except Exception:
            await self.close_peer(pc)
            raise

        with self.lock:
            self.peer_connections.add(pc)

        @pc.on("connectionstatechange")
        async def on_connection_state_change() -> None:
            if pc.connectionState in {"failed", "closed", "disconnected"}:
                await self.close_peer(pc)

        try:
            await pc.setRemoteDescription(RTCSessionDescription(offer.sdp, offer.type))
            answer = await pc.createAnswer()
            await pc.setLocalDescription(answer)
            return {"sdp": pc.localDescription.sdp, "type": pc.localDescription.type}
        except Exception:
            await self.close_peer(pc)
            raise

    async def close_peer(self, pc: RTCPeerConnection) -> None:
        with self.lock:
            self.peer_connections.discard(pc)
        if pc.connectionState != "closed":
            await pc.close()

    async def close_all(self) -> None:
        with self.lock:
            peers = list(self.peer_connections)
            self.peer_connections.clear()
            sources = list(self.sources.values())
            self.sources.clear()
            self.camera_keys.clear()
        for pc in peers:
            if pc.connectionState != "closed":
                await pc.close()
        for source in sources:
            source.close()
