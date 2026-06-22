from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
import anyio

from app.models import Camera


def _build_ffprobe_command(ffprobe: str, stream_url: str, transport: str | None) -> list[str]:
    command = [
        ffprobe,
        "-hide_banner",
        "-loglevel",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name:format=duration,format_name",
        "-of",
        "json",
    ]
    if transport:
        command.extend(["-rtsp_transport", transport])
    command.extend(["-i", stream_url])
    return command


def probe_stream_url(stream_url: str, timeout_s: float = 6.0) -> dict[str, object]:
    ffprobe = shutil.which("ffprobe")
    if not stream_url:
        return {"reachable": False, "error": "empty stream URL"}
    if ffprobe is None:
        return {"reachable": False, "error": "ffprobe missing"}

    attempts: list[dict[str, str]] = []
    for transport in (None, "udp", "tcp"):
        command = _build_ffprobe_command(ffprobe, stream_url, transport)
        try:
            result = subprocess.run(command, capture_output=True, text=True, timeout=timeout_s, check=False)
        except subprocess.TimeoutExpired:
            attempts.append({"transport": transport or "auto", "error": f"timed out after {timeout_s:.0f}s"})
            continue

        if result.returncode == 0:
            return {"reachable": True, "error": "", "stdout": result.stdout, "transport": transport or "auto"}

        attempts.append(
            {
                "transport": transport or "auto",
                "error": (result.stderr or result.stdout or "stream probe failed").strip(),
            }
        )

    error = "; ".join(f"{attempt['transport']}: {attempt['error']}" for attempt in attempts) or "stream probe failed"
    return {"reachable": False, "error": error, "attempts": attempts}


@dataclass
class CameraStreamer:
    camera: Camera
    transport: str = "auto"
    subscribers: set[queue.Queue] = field(default_factory=set)
    proc: subprocess.Popen | None = None
    thread: threading.Thread | None = None
    stop_event: threading.Event = field(default_factory=threading.Event)
    lock: threading.Lock = field(default_factory=threading.Lock)

    def subscribe(self) -> queue.Queue:
        client_queue: queue.Queue = queue.Queue(maxsize=2)
        with self.lock:
            self.subscribers.add(client_queue)
            if self.proc is None:
                self._start_locked()
        return client_queue

    def unsubscribe(self, client_queue: queue.Queue) -> None:
        with self.lock:
            self.subscribers.discard(client_queue)
            if not self.subscribers:
                self._stop_locked()

    def _start_locked(self) -> None:
        if not self.camera.stream_url or shutil.which("ffmpeg") is None:
            return
        self.stop_event.clear()
        command = [
            "ffmpeg",
            "-hide_banner",
            "-loglevel",
            "error",
            "-fflags",
            "nobuffer",
            "-flags",
            "low_delay",
            "-probesize",
            "32",
            "-analyzeduration",
            "0",
        ]
        if self.transport and self.transport != "auto":
            command.extend(["-rtsp_transport", self.transport])
        command.extend(
            [
                "-i",
                self.camera.stream_url,
                "-an",
                "-vf",
                "scale=640:-1",
                "-q:v",
                "5",
                "-f",
                "mpjpeg",
                "-boundary_tag",
                "frame",
                "pipe:1",
            ]
        )
        self.proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        self.thread = threading.Thread(target=self._reader_loop, daemon=True)
        self.thread.start()

    def _stop_locked(self) -> None:
        self.stop_event.set()
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()
        self.proc = None

    def _broadcast(self, frame: bytes | None) -> None:
        stale: list[queue.Queue] = []
        for client_queue in list(self.subscribers):
            try:
                client_queue.put_nowait(frame)
            except queue.Full:
                stale.append(client_queue)
        for client_queue in stale:
            self.subscribers.discard(client_queue)

    def _reader_loop(self) -> None:
        if not self.proc or self.proc.stdout is None:
            return
        while not self.stop_event.is_set():
            chunk = self.proc.stdout.read(4096)
            if not chunk:
                break
            self._broadcast(chunk)
        self._broadcast(None)
        with self.lock:
            self.proc = None


class PreviewManager:
    def __init__(self) -> None:
        self.streamers: dict[str, CameraStreamer] = {}
        self.lock = threading.Lock()

    def get(self, camera: Camera, transport: str = "auto") -> CameraStreamer:
        with self.lock:
            key = f"{camera.id}:{transport or 'auto'}"
            streamer = self.streamers.get(key)
            if streamer is None or streamer.camera.stream_url != camera.stream_url or streamer.transport != (transport or "auto"):
                streamer = CameraStreamer(camera=camera, transport=transport or "auto")
                self.streamers[key] = streamer
            return streamer


async def stream_mjpeg(streamer: CameraStreamer):
    client_queue = streamer.subscribe()
    try:
        while True:
            chunk = await anyio.to_thread.run_sync(client_queue.get)
            if chunk is None:
                break
            yield chunk
    finally:
        streamer.unsubscribe(client_queue)
