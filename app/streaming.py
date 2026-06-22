from __future__ import annotations

import queue
import shutil
import subprocess
import threading
from dataclasses import dataclass, field
from typing import Iterable

import anyio

from app.models import Camera


@dataclass
class CameraStreamer:
    camera: Camera
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
        self.proc = subprocess.Popen(
            [
                "ffmpeg",
                "-hide_banner",
                "-loglevel",
                "error",
                "-rtsp_transport",
                "tcp",
                "-i",
                self.camera.stream_url,
                "-an",
                "-vf",
                "scale=640:-1",
                "-f",
                "image2pipe",
                "-vcodec",
                "mjpeg",
                "pipe:1",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
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
        buffer = bytearray()
        while not self.stop_event.is_set():
            chunk = self.proc.stdout.read(4096)
            if not chunk:
                break
            buffer.extend(chunk)
            while True:
                start = buffer.find(b"\xff\xd8")
                if start == -1:
                    buffer.clear()
                    break
                end = buffer.find(b"\xff\xd9", start + 2)
                if end == -1:
                    if start > 0:
                        del buffer[:start]
                    break
                frame = bytes(buffer[start : end + 2])
                del buffer[: end + 2]
                self._broadcast(frame)
        self._broadcast(None)
        with self.lock:
            self.proc = None


class PreviewManager:
    def __init__(self) -> None:
        self.streamers: dict[str, CameraStreamer] = {}
        self.lock = threading.Lock()

    def get(self, camera: Camera) -> CameraStreamer:
        with self.lock:
            streamer = self.streamers.get(camera.id)
            if streamer is None or streamer.camera.stream_url != camera.stream_url:
                streamer = CameraStreamer(camera=camera)
                self.streamers[camera.id] = streamer
            return streamer


async def stream_mjpeg(streamer: CameraStreamer):
    client_queue = streamer.subscribe()
    boundary = b"--frame\r\nContent-Type: image/jpeg\r\n\r\n"
    try:
        while True:
            frame = await anyio.to_thread.run_sync(client_queue.get)
            if frame is None:
                break
            yield boundary + frame + b"\r\n"
    finally:
        streamer.unsubscribe(client_queue)

