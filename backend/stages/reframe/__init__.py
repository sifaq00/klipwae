import subprocess
from pathlib import Path

import structlog
from stages.base import Stage, StageResult, StageStatus
from stages.registry import register

logger = structlog.get_logger(__name__)


def _get_video_info(video_path: Path) -> tuple[float, float]:
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "v:0",
         "-show_entries", "stream=r_frame_rate,duration",
         "-of", "csv=p=0", str(video_path)],
        capture_output=True, text=True, timeout=30,
    )
    parts = result.stdout.strip().split(",")
    if len(parts) < 2:
        return 30.0, 0.0
    fps_str = parts[0]
    if "/" in fps_str:
        num, den = fps_str.split("/")
        fps = float(num) / float(den)
    else:
        fps = float(fps_str)
    duration = float(parts[1])
    return fps, duration


@register
class ReframeStage(Stage):
    name = "reframe"
    depends_on = ["clip"]

    def is_complete(self, job_id: str, db) -> bool:
        raw_dir = Path("data/clips_raw")
        raw_clips = [c for c in raw_dir.glob(f"{job_id}_*.mp4") if "_reframed" not in c.name]
        if not raw_clips:
            return True
        return all(
            clip.with_name(clip.stem + "_reframed.mp4").exists()
            for clip in raw_clips
        )

    def run(self, job_id: str, db, config):
        raw_dir = Path("data/clips_raw")
        raw_clips = sorted(c for c in raw_dir.glob(f"{job_id}_*.mp4") if "_reframed" not in c.name)
        if not raw_clips:
            return StageResult(status=StageStatus.DONE, metadata={"clips_reframed": 0})

        from stages.reframe.layout_detector import detect_layout
        from stages.reframe.face_regions import compute_face_regions
        from stages.reframe.render import render_center_crop, render_split_screen
        from stages.reframe.speaker_activity import compute_speaker_activity
        from stages.reframe.camera_path import build_camera_path

        reframed_count = 0
        errors = []
        layouts = set()
        total_clips = len(raw_clips)
        for idx, clip in enumerate(raw_clips, 1):
            print(f"    reframe {idx}/{total_clips}")
            reframed_path = clip.with_name(clip.stem + "_reframed.mp4")
            if reframed_path.exists():
                reframed_count += 1
                continue

            # Deteksi PER KLIP — tiap segmen bisa beda setup kamera
            # (1 orang close-up vs 2+ orang face-to-face).
            layout = "single_shot"
            regions = None
            try:
                layout = detect_layout(clip)
                if layout == "split_screen":
                    regions = compute_face_regions(clip)
                    if regions is None:
                        logger.warning("reframe_fallback_center", reason="regions_not_found", job=job_id, clip=clip.name)
                        layout = "single_shot"
            except Exception as e:
                logger.warning("reframe_layout_fallback", error=str(e), job=job_id, clip=clip.name)
                layout = "single_shot"
            layouts.add(layout)

            try:
                fps, duration = _get_video_info(clip)
                if duration <= 0:
                    raise RuntimeError("invalid video duration")
                if layout == "split_screen" and regions:
                    activity = compute_speaker_activity(clip, fps, duration)
                    # Aktivitas speaker: PyAnnote (audio) dulu, MAR (bibir) fallback
                    from stages.reframe.diarization import diarize, map_speakers_to_sides
                    diar = diarize(clip)
                    if diar:
                        activity = map_speakers_to_sides(diar, activity)
                    camera_path = build_camera_path(activity, config.min_hold_sec)
                    # Jalur baru: YOLO track + kamera halus mengikuti pembicara.
                    # Gagal → fallback render_split_screen (crop statis + zoom).
                    clip_no = f"{idx}/{total_clips}"
                    if not _render_tracked(clip, camera_path, reframed_path, fps, clip_no):
                        render_split_screen(clip, camera_path, regions, reframed_path)
                else:
                    # single_shot: coba kamera follow orang dulu, fallback center crop
                    clip_no = f"{idx}/{total_clips}"
                    if not _render_tracked(clip, [], reframed_path, fps, clip_no):
                        render_center_crop(clip, reframed_path)
                reframed_count += 1
            except Exception as e:
                logger.warning("reframe_skip", clip=clip.name, error=str(e))
                errors.append({"clip": clip.name, "error": str(e)})

        # Layout per-klip bisa beda — simpan yang dominan ke DB untuk info UI
        db.conn.execute(
            "UPDATE segments SET layout_type=? WHERE job_id=?",
            ("split_screen" if "split_screen" in layouts else "single_shot", job_id),
        )
        db.conn.commit()

        return StageResult(
            status=StageStatus.DONE,
            metadata={"clips_reframed": reframed_count, "layout": ",".join(sorted(layouts)), "errors": len(errors)},
        )


def _render_tracked(clip, camera_path, reframed_path, fps, clip_no: str = "") -> bool:
    """Render kamera halus (YOLO track + EMA pan/zoom). False = gagal → fallback."""
    try:
        from stages.reframe.tracker import assign_zones, track_persons
        from stages.reframe.render_tracked import render_tracked
        boxes = track_persons(clip, clip_no=clip_no)
        if not boxes:
            return False
        zone_map = assign_zones(boxes)
        if not zone_map:
            return False
        return render_tracked(clip, camera_path, boxes, zone_map, fps, reframed_path, clip_no=clip_no)
    except Exception as e:
        logger.warning("render_tracked_fallback", error=str(e), clip=clip.name)
        return False
