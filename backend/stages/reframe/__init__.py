from pathlib import Path

import structlog
from stages.base import Stage, StageResult, StageStatus
from stages.registry import register
from utils.gpu_cleanup import clean_gpu_memory
from utils.video_info import get_video_info

logger = structlog.get_logger(__name__)


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
        import runtime
        for idx, clip in enumerate(raw_clips, 1):
            if runtime.stop_requested():
                break  # killed: jangan render klip tersisa
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
                fps, duration = get_video_info(clip)
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
                    if not _render_tracked(clip, camera_path, reframed_path, fps, clip_no, config=config):
                        render_split_screen(clip, camera_path, regions, reframed_path)
                else:
                    # single_shot: coba kamera follow orang dulu, fallback center crop
                    clip_no = f"{idx}/{total_clips}"
                    if not _render_tracked(clip, [], reframed_path, fps, clip_no, config=config):
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


def _render_tracked(clip, camera_path, reframed_path, fps, clip_no: str = "", config=None) -> bool:
    """Render kamera halus (YOLO track + EMA pan/zoom). False = gagal → fallback."""
    try:
        from stages.reframe.tracker import assign_zones, track_persons
        from stages.reframe.render_tracked import render_tracked
        cfg = {}
        if config is not None:
            cfg = {
                "smooth_alpha": getattr(config, "reframe_smooth_alpha", 0.08),
                "target_alpha": getattr(config, "reframe_target_alpha", 0.25),
                "deadband": getattr(config, "reframe_deadband", 0.012),
                "hold_sec": getattr(config, "reframe_hold_sec", 0.8),
                "head_bias": getattr(config, "reframe_head_bias", 0.22),
                "zoom_fit": getattr(config, "reframe_zoom_fit", 0.6),
                "zoom_min": getattr(config, "reframe_zoom_min", 1.15),
                "zoom_max": getattr(config, "reframe_zoom_max", 2.0),
                "zoom_idle": getattr(config, "reframe_zoom_idle", 1.05),
                "zoom_ease": getattr(config, "reframe_zoom_ease", 0.04),
                "zoom_deadband": getattr(config, "reframe_zoom_deadband", 0.05),
                "min_headroom_ratio": getattr(config, "reframe_min_headroom_ratio", 0.12),
            }
        boxes = track_persons(
            clip, clip_no=clip_no,
            step=getattr(config, "reframe_track_step", 3),
            use_cache=getattr(config, "reframe_track_cache", True),
            imgsz=getattr(config, "reframe_track_imgsz", 320),
        )
        if not boxes:
            return False
        zone_map = assign_zones(boxes)
        if not zone_map:
            return False
        return render_tracked(clip, camera_path, boxes, zone_map, fps, reframed_path,
                              clip_no=clip_no, **cfg)
    except Exception as e:
        logger.warning("render_tracked_fallback", error=str(e), clip=clip.name)
        return False
    finally:
        clean_gpu_memory()
