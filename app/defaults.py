from app.models import Box, Camera, Person, Settings, Zone


def default_cameras() -> list[Camera]:
    return [
        Camera(
            id="cam-a",
            name="Camera A",
            source_kind="rtsp",
            camera_backend="avfoundation",
            stream_url="",
            avfoundation_device="0",
        ),
        Camera(
            id="cam-b",
            name="Camera B",
            source_kind="rtsp",
            camera_backend="avfoundation",
            stream_url="",
            avfoundation_device="0",
        ),
    ]


def default_zones() -> list[Zone]:
    return [
        Zone(
            id="zone-a-exclusive",
            name="Camera A exclusive",
            type="exclusive",
            cameras=["cam-a"],
            box=Box(min_x=-4, max_x=1.5, min_y=0, max_y=3, min_z=-2.5, max_z=2.5),
        ),
        Zone(
            id="zone-ab-overlap",
            name="A/B overlap",
            type="overlap",
            cameras=["cam-a", "cam-b"],
            box=Box(min_x=1.5, max_x=4.5, min_y=0, max_y=3, min_z=-2.5, max_z=2.5),
        ),
        Zone(
            id="zone-b-exclusive",
            name="Camera B exclusive",
            type="exclusive",
            cameras=["cam-b"],
            box=Box(min_x=4.5, max_x=10, min_y=0, max_y=3, min_z=-2.5, max_z=2.5),
        ),
    ]


def default_person() -> Person:
    return Person()


def default_settings() -> Settings:
    return Settings()
