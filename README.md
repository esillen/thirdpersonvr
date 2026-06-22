# Third Person View Prototype

Local prototype for switching between static cameras based on 3D zones with overlap-aware handoff.

## Run

```bash
uv venv
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload
```

Open `http://localhost:3000/monitor` for the control dashboard.
Open `http://localhost:3000/headset` for the headset-only PWA view.

## What it does

- Tracks a single person position in 3D space
- Every second, the server samples each camera stream and looks for the visual marker
- Switches camera selection based on the last camera that reports the visual marker
- Shows a monitoring dashboard with room map, active camera, and event log
- Provides a separate headset-only view that only shows the currently selected camera stream
- Uses `ffmpeg` on the server for RTSP browser previews and AprilTag scanning
- Backend is Python/FastAPI, with the browser UI kept in static files under `app/static`

## Camera setup

- Add RTSP URLs in the camera JSON editor
- Install `ffmpeg` on the machine running the server; the monitor previews and marker scanner both depend on it
- The current prototype expects RTSP feeds and local browser monitoring
- The headset page registers a service worker and manifest so it can act as a PWA
- The monitor page shows the latest marker detection per camera and the current scanner status
- The monitor page also exposes AprilTag scanner settings like family, scan interval, capture size, and decision margin
- Use the `Print marker` button on the monitor page to open the AprilTag print sheet
- Print the official `tagStandard41h12` AprilTag image on matte white paper at 100 percent scale
- Mount it on stiff card or foam board so it stays flat
- Put the marker on the top of the headset, a cap, or a headband so rooms can see it from above
- Keep the black border fully visible and avoid glossy paper or curved placement

## Editing the prototype

- Camera and zone definitions live in the UI JSON editors
- The default layout is seeded from `app/defaults.py`
- State persists to `data/state.json`
