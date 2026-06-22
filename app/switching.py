from __future__ import annotations

from app.models import Camera, Person, Zone


def point_in_box(x: float, y: float, z: float, box) -> bool:
    return (
        x >= box.min_x
        and x <= box.max_x
        and y >= box.min_y
        and y <= box.max_y
        and z >= box.min_z
        and z <= box.max_z
    )


def evaluate_zones(person: Person, zones: list[Zone]) -> dict:
    containing = [zone for zone in zones if point_in_box(person.x, person.y, person.z, zone.box)]
    exclusive = [zone for zone in containing if zone.type == "exclusive"]
    overlap = [zone for zone in containing if zone.type == "overlap"]
    candidates: list[str] = []
    for zone in containing:
        for camera_id in zone.cameras:
            if camera_id not in candidates:
                candidates.append(camera_id)
    return {
        "containing": containing,
        "exclusive": exclusive,
        "overlap": overlap,
        "candidates": candidates,
    }


def choose_camera(
    person: Person,
    zones: list[Zone],
    active_camera_id: str | None,
    fallback_camera_id: str | None,
    cameras: list[Camera],
) -> tuple[str | None, str, dict]:
    evaluation = evaluate_zones(person, zones)
    candidates = evaluation["candidates"]

    if active_camera_id and active_camera_id in candidates:
        reason = "stay-in-overlap" if evaluation["overlap"] else "stay-in-zone"
        return active_camera_id, reason, evaluation

    exclusive_candidates: list[str] = []
    for zone in evaluation["exclusive"]:
        for camera_id in zone.cameras:
            if camera_id not in exclusive_candidates:
                exclusive_candidates.append(camera_id)
    if len(exclusive_candidates) == 1:
        return exclusive_candidates[0], "exclusive-zone", evaluation

    overlap_candidates: list[str] = []
    for zone in evaluation["overlap"]:
        for camera_id in zone.cameras:
            if camera_id not in overlap_candidates:
                overlap_candidates.append(camera_id)
    if overlap_candidates:
        return active_camera_id or overlap_candidates[0], "overlap-default", evaluation

    if fallback_camera_id:
        return fallback_camera_id, "fallback", evaluation
    if active_camera_id:
        return active_camera_id, "fallback", evaluation
    return cameras[0].id if cameras else None, "fallback", evaluation
