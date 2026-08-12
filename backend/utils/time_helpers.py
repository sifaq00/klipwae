def hms_to_sec(ts: str) -> float:
    parts = ts.split(":")
    if len(parts) == 2:
        m, s = parts
        return int(m) * 60 + float(s)
    h, m, s = parts[0], parts[1], parts[2]
    return int(h) * 3600 + int(m) * 60 + float(s)


def sec_to_hms(sec: float) -> str:
    if sec < 0:
        sec = 0
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
