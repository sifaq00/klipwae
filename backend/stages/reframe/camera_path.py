def build_camera_path(
    raw_activity: list[tuple[float, float, str]],
    min_hold_sec: float = 1.2,
) -> list[tuple[float, float, str]]:
    if not raw_activity:
        return []

    active_side = raw_activity[0][2]
    if active_side == "previous":
        active_side = "left"

    segments: list[dict] = [{"side": active_side, "start": raw_activity[0][0], "end": raw_activity[0][1]}]
    pending_side = None
    pending_start = 0.0

    for start, end, side in raw_activity[1:]:
        resolved = active_side if side == "previous" else side

        if resolved == active_side:
            pending_side = None
            segments[-1]["end"] = end
            continue

        if pending_side != resolved:
            pending_side = resolved
            pending_start = start

        if end - pending_start >= min_hold_sec:
            segments.append({"side": resolved, "start": start, "end": end})
            active_side = resolved
            pending_side = None
        else:
            segments[-1]["end"] = end

    return [(s["start"], s["end"], s["side"]) for s in segments]
