def hms_to_sec(ts: str | float | int) -> float:
    """"HH:MM:SS[.cc]" / "MM:SS" / "SS" → detik. Tak ter-parse → 0.0.

    (sebelumnya crash di int() untuk format tak terduga dari Gemini:
    timestamp aneh bisa menggagalkan seluruh stage.)"""
    if isinstance(ts, (int, float)):
        return float(max(0, ts))
    try:
        parts = str(ts).strip().split(":")
        if len(parts) == 2:
            return int(parts[0]) * 60 + float(parts[1])
        if len(parts) == 3:
            return int(parts[0]) * 3600 + int(parts[1]) * 60 + float(parts[2])
        return float(parts[0])
    except (ValueError, IndexError, TypeError):
        return 0.0


def sec_to_hms(sec: float) -> str:
    if sec < 0:
        sec = 0
    h, rem = divmod(int(sec), 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"
