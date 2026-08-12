import json
from pathlib import Path
from types import SimpleNamespace

import structlog
from stages.base import Stage, StageResult, StageStatus
from stages.registry import register
from utils.ffmpeg_helpers import run_ffmpeg, video_encode_args
from utils.time_helpers import hms_to_sec, sec_to_hms

logger = structlog.get_logger(__name__)

# Buffer 1-2 detik di awal/akhir biar tidak terpotong mendadak (plan 10.4)
CLIP_BUFFER_SEC = 1.5
# Ponytail: split internal pakai buffer kecil biar antar-chunk tidak duplikat audio
SPLIT_BUFFER_SEC = 0.3
MAX_CLIP_SEC = 60.0
MIN_CLIP_SEC = 25.0


def load_segments(path: Path) -> list[SimpleNamespace]:
    """Load segments JSON ke objek dengan .start/.end/.product_mentioned/.confidence/.topic.
    Kalau file ada tapi kosong, return []."""
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return [
        SimpleNamespace(
            start=s["start"],
            end=s["end"],
            product_mentioned=s.get("product_mentioned"),
            topic=s.get("topic"),
            confidence=s.get("confidence", 0.0),
        )
        for s in data
    ]


def split_segment_ranges(start: float, end: float, words: list[dict],
                         max_sec: float = MAX_CLIP_SEC,
                         min_sec: float = MIN_CLIP_SEC) -> list[tuple[float, float]]:
    """Pecah segmen panjang jadi chunk 30-60 detik.

    Potong di jeda bicara (gap >= 0.6s antar kata) dalam jendela 15 detik
    terakhir dari tiap window. Kalau tidak ada jeda bagus, potong tepat di
    max_sec. Deterministik â€” retry menghasilkan chunk yang sama.
    """
    if end - start <= max_sec:
        return [(start, end)]
    ws = sorted(
        (w for w in words if start <= w["start"] < end),
        key=lambda w: w["start"],
    )
    result = []
    cursor = start
    while end - cursor > max_sec:
        window_end = cursor + max_sec
        cut = window_end
        # Jendela cari jeda: MIN_CLIP_SEC..window_end (biar chunk pertama tidak kepotong)
        best_gap = 0.6
        for prev, nxt in zip(ws, ws[1:]):
            if nxt["start"] > window_end:
                break
            if nxt["start"] < cursor + min_sec:
                continue
            gap = nxt["start"] - prev["end"]
            if gap >= best_gap:
                best_gap = gap
                cut = nxt["start"]
        result.append((cursor, cut))
        cursor = cut
    result.append((cursor, end))
    return result


def align_boundary(words: list[dict], sec: float, direction: str,
                   window: float = 3.0, min_gap: float = 0.5) -> float:
    """Geser boundary potongan ke awal kalimat (awal kata setelah jeda ≥ min_gap).

    direction="start": mundur ke jeda TERAKHIR dalam [sec-window, sec).
    direction="end": maju ke jeda PERTAMA dalam (sec, sec+window].
    Tidak ada jeda → return sec. Kata kosong → return sec.
    """
    if not words:
        return sec
    ws = sorted(words, key=lambda w: w["start"])
    best = None
    for prev, nxt in zip(ws, ws[1:]):
        gap = nxt["start"] - prev["end"]
        if gap < min_gap:
            continue
        if direction == "start":
            if sec - window <= nxt["start"] < sec:
                best = nxt["start"]  # overwrite → ambil jeda terakhir
        else:
            if sec < nxt["start"] <= sec + window:
                return nxt["start"]  # jeda pertama setelah sec
    return best if best is not None else sec


@register
class ClipStage(Stage):
    name = "clip"
    depends_on = ["analyze"]

    def is_complete(self, job_id: str, db) -> bool:
        # Segments file ada, dan setiap row segmen di DB sudah punya clip
        # yang file-nya benar-benar ada. Row tanpa clip_path (gagal clip /
        # induk yang belum di-split) = belum selesai.
        segments_path = Path(f"data/segments/{job_id}.json")
        if not segments_path.exists():
            return False
        segments = load_segments(segments_path)
        if not segments:
            return True  # tidak ada segmen = tidak ada yang di-clip = selesai
        if db is None:
            return True
        rows = db.get_job_segments(job_id)
        if not rows:
            return False
        for row in rows:
            if not row.get("clip_path"):
                return False
            if not Path(row["clip_path"]).exists():
                return False
        return True

    def run(self, job_id: str, db, config):
        segments_path = Path(f"data/segments/{job_id}.json")
        if not segments_path.exists():
            return StageResult(status=StageStatus.FAILED, error=f"Segments not found: {segments_path}")

        raw_video = Path(f"data/raw/{job_id}.mp4")
        if not raw_video.exists():
            return StageResult(status=StageStatus.FAILED, error=f"Raw video not found: {raw_video}")

        segments = load_segments(segments_path)
        if not segments:
            return StageResult(status=StageStatus.DONE, metadata={"clips_created": 0})

        clips_dir = Path("data/clips_raw")
        clips_dir.mkdir(parents=True, exist_ok=True)

        # Word timestamps untuk split di jeda bicara (opsional â€” kalau
        # transcript hilang, split tetap jalan di batas max_sec)
        words = _load_words(job_id)

        clips_created = 0
        errors = []
        total_chunks = sum(len(split_segment_ranges(max(0.0, hms_to_sec(seg.start)), hms_to_sec(seg.end), words)) for seg in segments)
        done_chunks = 0
        # Kumpulin dulu semua work item (flush chunk yang sudah ada)
        work = []
        for i, seg in enumerate(segments):
            start_sec = max(0.0, hms_to_sec(seg.start))
            end_sec = hms_to_sec(seg.end)
            if end_sec <= start_sec:
                errors.append({"segment": i, "error": "invalid timestamps"})
                continue
            ranges = split_segment_ranges(start_sec, end_sec, words)
            if getattr(config, "clip_align_sentence", False) and words:
                # Kalimat utuh: mundur ke awal kalimat, maju ke awal kalimat berikut.
                s0, e0 = ranges[0]
                ranges[0] = (align_boundary(words, s0, "start"), e0)
                sL, eL = ranges[-1]
                ranges[-1] = (sL, align_boundary(words, eL, "end"))
            for k, (s, e) in enumerate(ranges):
                clip_idx = i * 100 + k
                clip_path = self._clip_path(job_id, clip_idx, seg)
                if clip_path.exists():
                    clips_created += 1
                    done_chunks += 1
                    continue
                first = k == 0
                last = k == len(ranges) - 1
                buf = CLIP_BUFFER_SEC if (first or last) else SPLIT_BUFFER_SEC
                work.append((seg, clip_idx, s, e, clip_path, buf))

        # ffmpeg per klip independen → jalan paralel (bukan guillotine 1-by-1)
        def _do(item):
            seg, clip_idx, s, e, clip_path, buf = item
            self._clip_one(raw_video, s, e, clip_path, buf)
            return seg, clip_idx, s, e, clip_path

        import sqlite3
        from concurrent.futures import ThreadPoolExecutor, as_completed
        with ThreadPoolExecutor(max_workers=getattr(config, "clip_parallel", 3)) as pool:
            futs = {pool.submit(_do, w): w for w in work}
            for fut in as_completed(futs):
                try:
                    seg, clip_idx, s, e, clip_path = fut.result()
                    db.upsert_clip_segment(
                        job_id, clip_idx,
                        sec_to_hms(s), sec_to_hms(e), seg,
                        str(clip_path),
                    )
                    clips_created += 1
                    done_chunks += 1
                    print(f"    clip {done_chunks}/{total_chunks}")
                except Exception as e:
                    # Plan Section 11: timestamp invalid → skip segmen (bukan gagalkan job).
                    # TAPI error DB = bug sistemik, jangan ditelan: fail stage supaya
                    # retry benar-benar memperbaiki state (bukan artefak yatim).
                    if isinstance(e, sqlite3.Error):
                        raise
                    logger.warning("clip_skip", error=str(e))
                    errors.append({"chunk": str(e)})

        # Buang row segmen induk yang sudah digantikan sub-klip / gagal di-clip
        if db is not None:
            db.delete_unclipped(job_id)

        return StageResult(
            status=StageStatus.DONE,
            metadata={"clips_created": clips_created, "errors": len(errors)},
        )

    def _clip_path(self, job_id: str, idx: int, seg) -> Path:
        # Nama file: {job_id}_{idx}_{product_slug}_conf{score}.mp4
        product = (seg.product_mentioned or "unknown").lower()
        # Sanitize: ambil 30 char pertama, ganti spasi/special dengan _
        slug = "".join(c if c.isalnum() else "_" for c in product)[:30].strip("_")
        score = int(seg.confidence * 100) if hasattr(seg, "confidence") else 0
        return Path(f"data/clips_raw/{job_id}_{idx:03d}_{slug}_conf{score}.mp4")

    def _clip_one(self, raw_video: Path, start_sec: float, end_sec: float, output: Path, buf: float):
        start = max(0.0, start_sec - buf)
        end = end_sec + buf
        # ffmpeg -ss sebelum -i = fast seek, tapi kurang akurat frame-exact.
        # -ss setelah -i = slow seek, akurat. Pakai -ss sebelum -i untuk kecepatan
        # (plan Section 10.4 eksplisit: ffmpeg -ss {start} -to {end}).
        # ponytail: re-encode (NVENC) supaya cut akurat, biarpun lebih lambat
        # dari stream copy. Upgrade ke -c copy kalau speed bottleneck dan akurasi
        # frame-exact tidak kritis.
        dur = max(0.2, end - start)
        result = run_ffmpeg([
            "-ss", f"{start:.3f}",
            "-to", f"{end:.3f}",
            "-i", str(raw_video),
            # Fade in/out 150ms biar potongan tidak hard-cut (video + audio)
            "-vf", f"fade=t=in:st=0:d=0.15,fade=t=out:st={dur - 0.15:.3f}:d=0.15",
            *video_encode_args(),
            "-c:a", "aac", "-b:a", "128k",
            "-af", f"afade=t=in:d=0.15,afade=t=out:st={dur - 0.15:.3f}:d=0.15",
            str(output),
        ], timeout=120)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg failed: {result.stderr[-500:]}")


def _load_words(job_id: str) -> list[dict]:
    transcript_path = Path(f"data/transcripts/{job_id}.json")
    if not transcript_path.exists():
        return []
    try:
        data = json.loads(transcript_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    return [
        {"text": w["text"], "start": w["start"], "end": w["end"]}
        for seg in data
        for w in seg.get("words", [])
    ]
