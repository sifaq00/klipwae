def smooth_rapid_speaker_turns(
    camera_path: list[tuple[float, float, str]],
    min_turn_sec: float = 2.0,
    window_sec: float = 6.0,
    max_turns_in_window: int = 3,
) -> list[tuple[float, float, str]]:
    """Smooth camera path when speaker turns occur faster than min_turn_sec
    repeatedly (> max_turns_in_window in window_sec).

    When rapid turns (> 3 speaker turns in 6 seconds) occur, merges or smooths
    the camera path to prevent dizzying rapid pan-swapping.
    """
    if not camera_path or len(camera_path) <= 1:
        return list(camera_path)

    # First merge adjacent segments with identical side
    merged: list[dict] = []
    for s, e, side in camera_path:
        if merged and merged[-1]["side"] == side:
            merged[-1]["end"] = max(merged[-1]["end"], e)
        else:
            merged.append({"start": s, "end": e, "side": side})

    if len(merged) <= max_turns_in_window:
        return [(m["start"], m["end"], m["side"]) for m in merged]

    n = len(merged)
    in_rapid_zone = [False] * n

    for i in range(n):
        w_start = merged[i]["start"]
        w_end = w_start + window_sec
        window_indices = []
        for j in range(i, n):
            if merged[j]["start"] < w_end:
                window_indices.append(j)
            else:
                break

        rapid_count = sum(
            1 for idx in window_indices if (merged[idx]["end"] - merged[idx]["start"]) < min_turn_sec
        )
        if len(window_indices) > max_turns_in_window and rapid_count >= 3:
            for idx in window_indices:
                if (merged[idx]["end"] - merged[idx]["start"]) < min_turn_sec:
                    in_rapid_zone[idx] = True

    result: list[dict] = []
    for i, seg in enumerate(merged):
        if not result:
            result.append(dict(seg))
            continue

        if in_rapid_zone[i]:
            result[-1]["end"] = seg["end"]
        else:
            if seg["side"] == result[-1]["side"]:
                result[-1]["end"] = seg["end"]
            else:
                result.append(dict(seg))

    return [(r["start"], r["end"], r["side"]) for r in result]


def build_camera_path(
    raw_activity: list[tuple[float, float, str]],
    min_hold_sec: float = 1.2,
    enable_rapid_turn_smoothing: bool = True,
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

    path = [(s["start"], s["end"], s["side"]) for s in segments]
    if enable_rapid_turn_smoothing:
        path = smooth_rapid_speaker_turns(path)
    return path

