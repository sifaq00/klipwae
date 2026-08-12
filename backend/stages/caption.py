import json
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import structlog
from stages.base import Stage, StageResult, StageStatus
from stages.registry import register
from utils.ffmpeg_helpers import run_ffmpeg, video_encode_args
from utils.time_helpers import hms_to_sec

logger = structlog.get_logger(__name__)

CLIP_BUFFER_SEC = 1.5  # sama dengan clip.py â€” kata di ambang segmen ikut ke-subtitle


def _sanitize_ass_text(text: str) -> str:
    """Escape karakter special ASS: { } \\ harus di-escape."""
    return text.replace("\\", "\\\\").replace("{", "\\{").replace("}", "\\}")


def _sec_to_ass_time(sec: float) -> str:
    """Konversi detik ke format ASS time: H:MM:SS.cc (centisecond, 2 digit)."""
    if sec < 0:
        sec = 0
    h = int(sec // 3600)
    m = int((sec % 3600) // 60)
    s = int(sec % 60)
    cs = int((sec - int(sec)) * 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def _hex_to_bgr(hex_color: str) -> str:
    """#RRGGBB â†’ ASS &H00BBGGRR (primary/secondary) atau &HBBGGRR (override \c)."""
    h = hex_color.lstrip("#")
    if len(h) != 6:
        h = "FFFFFF"
    return f"{h[4:6]}{h[2:4]}{h[0:2]}"


def _ass_header(style: dict, karaoke: bool = True) -> str:
    bold = "-1" if style.get("bold", True) else "0"
    italic = "-1" if style.get("italic", False) else "0"
    spacing = int(style.get("spacing", 0) or 0)
    outline = max(0, int(style.get("outline", 6) or 0))
    shadow = max(0, int(style.get("shadow", 3) or 0))
    border_style = 3 if style.get("border_style") == "box" else 1
    alignment = 8 if style.get("position") == "top" else 2
    margin_v = int(style.get("margin_v", 100) or 100)
    # Konvensi karaoke libass: kata AKTIF = PrimaryColour, kata lain = SecondaryColour.
    # Untuk highlight TikTok (kata sekarang kuning, sisanya putih) kita animasi
    # warna per kata via \t, jadi default style = warna teks.
    if karaoke:
        primary = _hex_to_bgr(style.get("text_color", "#FFFFFF"))
        secondary = _hex_to_bgr(style.get("highlight_color", "#FFFF00"))
    else:
        primary = _hex_to_bgr(style.get("text_color", "#FFFFFF"))
        secondary = _hex_to_bgr(style.get("highlight_color", "#FFFF00"))
    outline_col = _hex_to_bgr(style.get("outline_color", "#000000"))
    back_col = _hex_to_bgr(style.get("shadow_color", "#000000"))
    return f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{style.get('font', 'Segoe UI')},{int(style.get('size', 96) or 96)},&H00{primary},&H00{secondary},&H00{outline_col},&H00{back_col},{bold},{italic},0,0,100,100,{spacing},0,{border_style},{outline},{shadow},{alignment},40,40,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""


def generate_ass(words: list[dict], style: str = "highlight",
                 style_cfg: dict | None = None) -> str:
    """Generate file .ass dari word-level timestamps.

    style='highlight': kata yang sedang diucapkan berwarna beda (karaoke style,
    umum di TikTok). style='static': satu baris kalimat muncul-hilang biasa.
    style_cfg: dict konfigurasi gaya (font/ukuran/warna/dll) â€” kalau None,
    pakai default global dari utils.caption_style.

    words: list of {"text": str, "start": float, "end": float}
    """
    if style_cfg is None:
        from utils.caption_style import load_global
        style_cfg = load_global()
    header = _ass_header(style_cfg, karaoke=(style == "highlight"))

    if not words:
        return header

    lines = [header]
    to_upper = bool(style_cfg.get("uppercase", False))
    # Line spacing: sisip baris kosong ber-{\fsN} antar baris visual â€” libass
    # nggak support field LineSpacing, trik ini kasih gap â‰ˆ N px.
    # {\fsN} harus di-reset ke ukuran asli setelahnya, kalau tidak baris
    # berikutnya ikut mengecil (override \fs nempel sampai akhir block).
    ls = max(0, int(style_cfg.get("line_spacing", 0) or 0))
    fs_default = int(style_cfg.get("size", 96) or 96)
    line_sep = "\\N" if ls == 0 else f"\\N{{\\fs{ls}}} {{\\fs{fs_default}}}\\N"
    # Wrap dinamis: batas char disesuaikan ukuran font biar baris tidak
    # melebihi lebar 1080 (margin kiri/kanan 40px). 0.5 ≈ lebar char rata-rata.
    wrap_max_chars = max(12, int(1000 / (fs_default * 0.5)))

    def _text(w: dict) -> str:
        t = w["text"]
        return t.upper() if to_upper else t

    def _wrap(texts: list[str], max_chars: int = 38) -> list[str]:
        """Bungkus kata jadi baris visual â€” konsisten antar dialogue."""
        out = []
        cur = ""
        for t in texts:
            if cur and len(cur) + len(t) + 1 > max_chars:
                out.append(cur)
                cur = t
            else:
                cur = f"{cur} {t}" if cur else t
        if cur:
            out.append(cur)
        return out

    if style == "highlight":
        # Style TikTok: cuma kata yang SEDANG diucapkan yang kuning, sisanya
        # putih. Dikerjakan sebagai N baris dialogue (satu per kata aktif):
        # tiap baris = kalimat penuh, kata ke-i dibungkus {\c highlight}.
        # Baris i tampil tepat di timing kata i â†’ libass gambar baris terbaru
        # di atas (z-order), jadi efeknya kata aktif kuning, sisanya putih.
        # TIDAK pakai \k (warna terkunci) dan TIDAK pakai \t (animasi rusak
        # di libass build ini â€” end-state nempel dari awal).
        sentences = _group_sentences(words)
        hl = _hex_to_bgr(style_cfg.get("highlight_color", "#FFFF00"))
        txt = _hex_to_bgr(style_cfg.get("text_color", "#FFFFFF"))
        pop = bool(style_cfg.get("pop", False))
        active_scale = "\\fscx112\\fscy112" if pop else ""
        for sent in sentences:
            texts = [_text(w) for w in sent]
            wrapped = _wrap(texts, wrap_max_chars)
            for i, w in enumerate(sent):
                line_start = w["start"]
                if i + 1 < len(sent):
                    line_end = sent[i + 1]["start"]
                else:
                    line_end = w["end"]
                if line_end <= line_start:
                    line_end = line_start + 0.01
                # Bangun ulang baris visual dengan kata aktif di-highlight
                parts = []
                wi = 0
                for li, line in enumerate(wrapped):
                    if li > 0:
                        parts.append(line_sep)
                    line_parts = []
                    for word in line.split(" "):
                        w_safe = _sanitize_ass_text(word)
                        if wi == i:
                            line_parts.append("{\\c&H" + hl + active_scale + "}" + w_safe + "{\\c&H" + txt + "}")
                        else:
                            line_parts.append(w_safe)
                        wi += 1
                    parts.append(" ".join(line_parts))
                lines.append(
                    f"Dialogue: 0,{_sec_to_ass_time(line_start)},{_sec_to_ass_time(line_end)},"
                    f"Default,,0,0,0,,{''.join(parts)}"
                )
    else:
        # Static: satu baris kalimat, muncul-hilang
        sentences = _group_sentences(words)
        for sent in sentences:
            start = sent[0]["start"]
            end = sent[-1]["end"]
            # Sanitize per kata DULU â€” line_sep berisi tag \N/{\fs} yang
            # jangan ikut di-escape.
            wrapped = _wrap([_sanitize_ass_text(_text(w)) for w in sent], wrap_max_chars)
            lines.append(
                f"Dialogue: 0,{_sec_to_ass_time(start)},{_sec_to_ass_time(end)},"
                f"Default,,0,0,0,,{line_sep.join(wrapped)}"
            )

    return "\n".join(lines) + "\n"


def _make_thumb(final_path: Path):
    """Thumbnail poster 1 frame buat kartu review UI â€” hindari UI load video
    penuh (10+ video sekaligus bikin backend pegang handle file terus)."""
    thumb = final_path.with_suffix(".jpg")
    if thumb.exists():
        return
    try:
        run_ffmpeg([
            "-ss", "1.0", "-i", str(final_path),
            "-frames:v", "1", "-q:v", "4",
            str(thumb),
        ], timeout=30)
    except Exception:
        pass


def _group_sentences(words: list[dict], max_words: int = 10, gap_sec: float = 1.5) -> list[list[dict]]:
    """Group word list jadi kalimat pendek buat subtitle TikTok (max ~10 kata
    atau jeda > 1.5s antar kata). Non-overlapping."""
    if not words:
        return []
    sentences = []
    current = [words[0]]
    for prev, cur in zip(words, words[1:]):
        if len(current) >= max_words or (cur["start"] - prev["end"]) > gap_sec:
            sentences.append(current)
            current = [cur]
        else:
            current.append(cur)
    if current:
        sentences.append(current)
    return sentences


@register
class CaptionStage(Stage):
    name = "caption"
    depends_on = ["reframe"]

    def is_complete(self, job_id: str, db) -> bool:
        # DB-driven: semua segmen yang punya clip sudah punya caption final.
        # Guard: segments file ada tapi DB kosong (state korup, lihat bug
        # upsert e2e) â†’ anggap belum selesai, biar stage jalan dan repair.
        if Path(f"data/segments/{job_id}.json").exists():
            try:
                if json.loads(Path(f"data/segments/{job_id}.json").read_text(encoding="utf-8")):
                    if db is not None and not db.get_job_segments(job_id):
                        return False
            except (json.JSONDecodeError, OSError):
                pass
        if db is None:
            return True
        rows = db.get_job_segments(job_id)
        if not rows:
            return True
        for row in rows:
            if not row.get("clip_path"):
                continue
            final = Path("data/clips_final") / Path(row["clip_path"]).name
            if not final.exists():
                return False
        return True

    def run(self, job_id: str, db, config):
        if db is None:
            return StageResult(status=StageStatus.DONE, metadata={"clips_captioned": 0})
        rows = db.get_job_segments(job_id)
        rows = [r for r in rows if r.get("clip_path")]
        if not rows:
            return StageResult(status=StageStatus.DONE, metadata={"clips_captioned": 0})

        # Gaya subtitle: global default + override per job (kalau ada)
        from utils.caption_style import style_for_job
        style_cfg = style_for_job(db.get_job_style(job_id))
        ass_style = style_cfg.get("style", "highlight")

        final_dir = Path(__file__).parent.parent / "data" / "clips_final"
        final_dir.mkdir(parents=True, exist_ok=True)

        # Load transcript untuk word-level timestamps
        transcript_path = Path(f"data/transcripts/{job_id}.json")
        if not transcript_path.exists():
            return StageResult(status=StageStatus.FAILED, error=f"Transcript not found: {transcript_path}")
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))

        clips_captioned = 0
        errors = []
        errors_lock = threading.Lock()
        total_rows = len(rows)
        done_rows = 0
        done_lock = threading.Lock()

        def _burn(row):
            clip = Path(row["clip_path"])
            # Prefer reframed (vertikal 9:16) â€” fallback ke raw kalau reframe skip
            reframed = clip.with_name(clip.stem + "_reframed.mp4")
            source = reframed if reframed.exists() else clip
            final_path = final_dir / source.name.replace("_reframed", "")
            if final_path.exists():
                return 1, None
            try:
                # Ambil kata yang overlap dengan segmen ini (pakai buffer clip)
                seg_start = hms_to_sec(row["start_time"]) - CLIP_BUFFER_SEC
                seg_end = hms_to_sec(row["end_time"]) + CLIP_BUFFER_SEC

                # Filter kata yang ada di range segmen
                clip_words = []
                for seg in transcript:
                    for w in seg.get("words", []):
                        if seg_start <= w["start"] <= seg_end:
                            clip_words.append({
                                "text": w["text"],
                                "start": w["start"] - seg_start,
                                "end": w["end"] - seg_start,
                            })

                # Generate .ass
                ass_content = generate_ass(clip_words, style=ass_style, style_cfg=style_cfg)
                ass_path = final_dir / Path(final_path).with_suffix(".ass").name
                ass_path.write_text(ass_content, encoding="utf-8")

                # Burn-in subtitle ke video final
                # Plan Section 10.6: output final ke clips_final/
                # ffmpeg: -vf subtitles=path.ass
                # Path RELATIF ke backend + cwd: menghindari escape colon
                # (D\:) yang rusak di filter subtitles, dan wajib dipakai
                # biar fontsdir (font bundle) ikut ke-resolve.
                backend_dir = Path(__file__).parent.parent
                source_abs = source if source.is_absolute() else backend_dir / source
                result = run_ffmpeg([
                    "-i", str(source_abs.relative_to(backend_dir).as_posix()),
                    "-vf", f"subtitles={ass_path.relative_to(backend_dir).as_posix()}:fontsdir=fonts",
                    *video_encode_args(),
                    "-c:a", "copy",
                    str(final_path.relative_to(backend_dir).as_posix()),
                ], timeout=600, cwd=str(backend_dir))
                if result.returncode != 0:
                    raise RuntimeError(f"ffmpeg burn-in failed: {result.stderr[-500:]}")

                db.update_segment_by_id(row["id"], caption_path=str(final_path))
                _make_thumb(final_path)
                return 1, None
            except Exception as e:
                logger.warning("caption_skip", clip=clip.name, error=str(e))
                return 0, {"clip": clip.name, "error": str(e)}

        # Burn paralel â€” re-encode 1080x1920 itu CPU-bound, 3 worker berasa
        # 2-3x lebih cepat daripada serial (re-burn 10 klip: ~10mnt â†’ ~4mnt).
        workers = max(1, min(3, (os.cpu_count() or 2) // 2))
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for ok, err in pool.map(_burn, rows):
                if ok:
                    clips_captioned += 1
                elif err:
                    with errors_lock:
                        errors.append(err)
                with done_lock:
                    done_rows += 1
                print(f"    caption {done_rows}/{total_rows}")

        return StageResult(
            status=StageStatus.DONE,
            metadata={"clips_captioned": clips_captioned, "errors": len(errors)},
        )
