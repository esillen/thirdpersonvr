from __future__ import annotations

import concurrent.futures
import subprocess
import threading
import time
from dataclasses import dataclass
from functools import lru_cache

import numpy as np

from app.models import Camera
from app.store import StateStore


@dataclass
class MarkerResult:
    camera_id: str
    marker_id: str
    confidence: float
    centroid_x: float
    centroid_y: float
    frame_width: int
    frame_height: int
    detected_at: float
    source: str = "auto-scan"

    def as_dict(self) -> dict[str, object]:
        return {
            "camera_id": self.camera_id,
            "marker_id": self.marker_id,
            "confidence": self.confidence,
            "centroid": {"x": self.centroid_x, "y": self.centroid_y},
            "frame_size": {"width": self.frame_width, "height": self.frame_height},
            "detected_at": self.detected_at,
            "source": self.source,
        }


def capture_frame_gray8(stream_url: str, width: int = 640, height: int = 360, timeout_s: int = 8) -> tuple[bytes, int, int] | None:
    command = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-rtsp_transport",
        "tcp",
        "-i",
        stream_url,
        "-vf",
        f"scale={width}:{height},format=gray",
        "-frames:v",
        "1",
        "-f",
        "rawvideo",
        "pipe:1",
    ]
    try:
        completed = subprocess.run(
            command,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            timeout=timeout_s,
            check=False,
        )
    except (subprocess.SubprocessError, FileNotFoundError):
        return None

    frame = completed.stdout or b""
    expected = width * height
    if len(frame) < expected:
        return None
    return frame[:expected], width, height


@lru_cache(maxsize=8)
def load_detector(family: str):
    try:
        import apriltag
    except ImportError:
        return None

    options_cls = getattr(apriltag, "DetectorOptions", None)
    detector_cls = getattr(apriltag, "Detector", None)
    if detector_cls is not None:
        if options_cls is not None:
            try:
                options = options_cls(families=family)
                return detector_cls(options)
            except Exception:
                pass
        try:
            return detector_cls()
        except Exception:
            pass

    factory = getattr(apriltag, "apriltag", None)
    if factory is not None:
        return factory(family)
    return None


def get_detection_value(detection, name: str, default=None):
    if hasattr(detection, name):
        return getattr(detection, name)
    if isinstance(detection, dict):
        return detection.get(name, default)
    return default


def detect_marker_from_frame(
    frame: bytes,
    width: int,
    height: int,
    camera_id: str,
    family: str,
    min_decision_margin: float,
) -> MarkerResult | None:
    detector = load_detector(family)
    if detector is None:
        return None

    gray = np.frombuffer(frame, dtype=np.uint8).reshape((height, width))
    detections = detector.detect(gray)
    if not detections:
        return None

    best_detection = max(
        detections,
        key=lambda detection: float(get_detection_value(detection, "decision_margin", 0.0)),
    )
    decision_margin = float(get_detection_value(best_detection, "decision_margin", 0.0))
    if decision_margin < min_decision_margin:
        return None
    center = get_detection_value(best_detection, "center", (width / 2, height / 2))
    tag_id = get_detection_value(best_detection, "tag_id", get_detection_value(best_detection, "id", "head-marker"))
    confidence = decision_margin
    return MarkerResult(
        camera_id=camera_id,
        marker_id=f"tag-{tag_id}",
        confidence=max(0.0, min(1.0, confidence / 100.0)),
        centroid_x=float(center[0]),
        centroid_y=float(center[1]),
        frame_width=width,
        frame_height=height,
        detected_at=time.time(),
    )


def scan_camera_for_marker_with_settings(camera: Camera, settings) -> MarkerResult | None:
    if not camera.stream_url:
        return None
    frame = capture_frame_gray8(
        camera.stream_url,
        width=int(settings.apriltag_capture_width),
        height=int(settings.apriltag_capture_height),
    )
    if frame is None:
        return None
    raw, width, height = frame
    return detect_marker_from_frame(
        raw,
        width,
        height,
        camera.id,
        family=settings.apriltag_family,
        min_decision_margin=float(settings.apriltag_min_decision_margin),
    )


class MarkerScannerService:
    def __init__(self, store: StateStore, interval_s: float = 1.0):
        self.store = store
        self.interval_s = interval_s
        self.stop_event = threading.Event()
        self.thread: threading.Thread | None = None

    def start(self) -> None:
        if self.thread and self.thread.is_alive():
            return
        self.stop_event.clear()
        self.thread = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        self.stop_event.set()
        if self.thread and self.thread.is_alive():
            self.thread.join(timeout=2)

    def _loop(self) -> None:
        while not self.stop_event.is_set():
            cycle_started_at = time.time()
            cameras = [camera for camera in self.store.cameras if camera.stream_url]
            settings = self.store.settings
            self.store.set_marker_scan_status(
                {
                    "running": True,
                    "cycle_started_at": cycle_started_at,
                    "cycle_finished_at": None,
                    "camera_count": len(cameras),
                    "last_error": "",
                }
            )

            last_detection: MarkerResult | None = None
            try:
                self.interval_s = float(settings.apriltag_scan_interval_s)
                with concurrent.futures.ThreadPoolExecutor(max_workers=max(1, len(cameras))) as executor:
                    futures = {
                        executor.submit(scan_camera_for_marker_with_settings, camera, settings): camera.id
                        for camera in cameras
                    }
                    for future in concurrent.futures.as_completed(futures):
                        result = future.result()
                        if result is not None:
                            last_detection = result
                            self.store.record_marker_observation(result.as_dict())
            except Exception as error:  # pragma: no cover - defensive guard for the loop
                self.store.set_marker_scan_status(
                    {
                        "running": False,
                        "cycle_started_at": cycle_started_at,
                        "cycle_finished_at": time.time(),
                        "camera_count": len(cameras),
                        "last_error": str(error),
                        "last_detected_camera_id": getattr(last_detection, "camera_id", None),
                    }
                )
            else:
                self.store.set_marker_scan_status(
                    {
                        "running": False,
                        "cycle_started_at": cycle_started_at,
                        "cycle_finished_at": time.time(),
                        "camera_count": len(cameras),
                        "last_error": "",
                        "last_detected_camera_id": last_detection.camera_id if last_detection else None,
                    }
                )

            elapsed = time.time() - cycle_started_at
            remaining = max(0.0, self.interval_s - elapsed)
            self.stop_event.wait(remaining)
