# Third Person View Prototype

Local prototype for picking one of two camera feeds in a monitor client and showing it in a headset view.

## Run

```bash
uv venv
uv sync
uv run uvicorn app.main:app --host 127.0.0.1 --port 3000 --reload
```

Open `http://localhost:3000/monitor` for the control dashboard.
Open `http://localhost:3000/headset` for the headset-only PWA view.

## What it does

- Lets the monitor client preview two camera feeds and manually select which one the headset should show
- Lets you paste a stream URL when discovery does not find the camera automatically
- Provides a separate headset-only view that only shows the currently selected camera stream
- Uses `ffmpeg` on the server for RTSP browser previews
- Backend is Python/FastAPI, with the browser UI kept in static files under `app/static`

## Camera setup

- Add or edit the two camera slots from the monitor page
- Paste an RTSP or MJPEG stream URL if the stream is not discovered automatically, then click `Save & show on headset`
- Install `ffmpeg` on the machine running the server; live previews depend on it
- The headset page registers a service worker and manifest so it can act as a PWA

## Editing the prototype

- The two camera slots are seeded from `app/defaults.py`
- Camera streams are edited directly in the monitor client
- State persists to `data/state.json`
