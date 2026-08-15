import json
import os
from pathlib import Path
from types import SimpleNamespace

import structlog
from google import genai
from pydantic import BaseModel, Field
from tenacity import retry, stop_after_attempt, wait_exponential

from stages.base import Stage, StageResult, StageStatus
from stages.registry import register
from utils.cost_tracker import calc_cost
from utils.time_helpers import hms_to_sec, sec_to_hms

logger = structlog.get_logger(__name__)


class Segment(BaseModel):
    start: str
    end: str
    product_mentioned: str | None
    topic: str
    confidence: float = Field(ge=0.0, le=1.0)
    reason: str
    caption_text: str | None = None
    hook_score: int = Field(default=85, ge=0, le=100, description="Hook potential score from 0 to 100")
    virality_reason: str = Field(default="", description="Why this clip has viral potential")
    affiliate_caption: str = Field(default="", description="Ready-to-post short caption with call to action")
    hashtags: list[str] = Field(default_factory=list, description="Recommended TikTok/Shopee hashtags")


class AnalysisResult(BaseModel):
    segments: list[Segment]


class CaptionItem(BaseModel):
    idx: int
    caption: str


class CaptionBatch(BaseModel):
    captions: list[CaptionItem]


def load_transcript(path: Path) -> list[SimpleNamespace]:
    """Load JSON transkrip, return list objek dengan .start/.end/.text."""
    data = json.loads(path.read_text(encoding="utf-8"))
    return [SimpleNamespace(text=s["text"], start=s["start"], end=s["end"]) for s in data]


def chunk_transcript(transcript: list[SimpleNamespace], chunk_min: int = 20, overlap_min: int = 2) -> list[list[SimpleNamespace]]:
    """Split transkrip per chunk_min menit, overlap overlap_min menit di boundary.

    Guard: overlap >= chunk_min raise ValueError (jaga-jaga walau config.py
    sudah validasi). Transkrip kosong return [].
    """
    if not transcript:
        return []
    if overlap_min >= chunk_min:
        raise ValueError(
            f"chunk_overlap_min ({overlap_min}) harus < chunk_duration_min ({chunk_min})"
        )

    chunks = []
    chunk_start = 0.0
    total_end = transcript[-1].end
    step = (chunk_min - overlap_min) * 60  # selalu > 0

    while chunk_start < total_end:
        chunk_end = chunk_start + chunk_min * 60
        chunk = [s for s in transcript if chunk_start <= s.start < chunk_end]
        if chunk:
            chunks.append(chunk)
        chunk_start += step
    return chunks


def format_chunk_for_prompt(chunk: list[SimpleNamespace]) -> str:
    """Format chunk ke [HH:MM:SS] teks, tanpa label pembicara."""
    lines = []
    for s in chunk:
        lines.append(f"[{sec_to_hms(s.start)}] {s.text}")
    return "\n".join(lines)


def get_preset_prompt(preset: str = "affiliate") -> str:
    """Load system prompt for the specified niche preset from prompts/presets/<preset>.txt.
    Falls back to affiliate.txt if preset is missing or not found."""
    p_name = (preset or "affiliate").lower().strip()
    backend_dir = Path(__file__).resolve().parent.parent
    candidates = [
        Path("backend/prompts/presets") / f"{p_name}.txt",
        Path("prompts/presets") / f"{p_name}.txt",
        backend_dir / "prompts" / "presets" / f"{p_name}.txt",
        # Fallback to default affiliate preset
        Path("backend/prompts/presets/affiliate.txt"),
        Path("prompts/presets/affiliate.txt"),
        backend_dir / "prompts" / "presets" / "affiliate.txt",
    ]
    for c in candidates:
        if c.exists() and c.is_file():
            return c.read_text(encoding="utf-8")
    raise FileNotFoundError(f"Prompt preset '{preset}' and fallback affiliate preset not found")


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def analyze_chunk(client, system_prompt: str, chunk_text: str, model: str) -> tuple[list[Segment], dict]:
    """Call Gemini dengan response_schema Pydantic. Return (segments, usage).

    Exception di-propagate ke tenacity → retry 3x beneran jalan. Habis 3x,
    raise ke caller (AnalyzeStage.run) yang memutuskan skip chunk, bukan
    menggagalkan job (plan Section 11).
    """
    response = client.models.generate_content(
        model=model,
        contents=chunk_text,
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": AnalysisResult,
            "temperature": 0.1,
        },
    )
    result: AnalysisResult = response.parsed
    usage = {}
    if hasattr(response, "usage_metadata") and response.usage_metadata:
        usage = {
            "input_tokens": response.usage_metadata.prompt_token_count,
            "output_tokens": response.usage_metadata.candidates_token_count,
        }
    return result.segments, usage


@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=30))
def _caption_batch(client, system_prompt: str, batch: list[Segment], model: str) -> dict[int, str]:
    """SATU call Gemini utk 1 batch segmen. Retry 3x via tenacity."""
    payload = [
        {"idx": i, "start": s.start, "end": s.end,
         "product": s.product_mentioned, "topic": s.topic,
         "virality_reason": getattr(s, "virality_reason", ""),
         "affiliate_caption": getattr(s, "affiliate_caption", "")}
        for i, s in enumerate(batch)
    ]
    response = client.models.generate_content(
        model=model,
        contents=json.dumps(payload, ensure_ascii=False),
        config={
            "system_instruction": system_prompt,
            "response_mime_type": "application/json",
            "response_schema": CaptionBatch,
            "temperature": 0.7,
        },
    )
    if not response.parsed:
        return {}
    return {c.idx: c.caption for c in response.parsed.captions}


# Max segmen per call Gemini — episode panjang bisa 15-30 segmen; batch
# besar = kalau 1 call gagal, SEMUA caption hilang. Pecah → kegagalan
# cuma ngebunuh 1 batch (retry 3x per batch tetap jalan).
CAPTION_BATCH_SIZE = 8


def generate_captions(client, system_prompt: str, segments: list[Segment], model: str) -> dict[int, str]:
    """Generate caption TikTok per segmen, batch per 8. Kegagalan satu batch
    tidak menghapus caption batch lain (yang berhasil tetap dipakai)."""
    all_caps: dict[int, str] = {}
    for start in range(0, len(segments), CAPTION_BATCH_SIZE):
        batch = segments[start:start + CAPTION_BATCH_SIZE]
        try:
            batch_caps = _caption_batch(client, system_prompt, batch, model)
            for local_idx, cap in batch_caps.items():
                all_caps[start + local_idx] = cap
        except Exception as e:
            logger.warning("caption_batch_skipped", start=start, error=str(e))
    return all_caps


def fallback_caption(seg: Segment) -> str:
    """Caption cadangan kalau Gemini gagal — datanya sudah ada, tinggal
    dibungkus biar tetap bisa di-copy-paste ke TikTok."""
    if seg.affiliate_caption:
        tags = " ".join(seg.hashtags) if seg.hashtags else ""
        return f"{seg.affiliate_caption}\n\n{tags}".strip() if tags else seg.affiliate_caption
    parts = [p for p in (seg.product_mentioned, seg.topic) if p]
    base = " — ".join(parts) if parts else "Klip produk"
    tags = " ".join(seg.hashtags) if seg.hashtags else ""
    return f"{base}\n\n{tags}".strip() if tags else base


def overlap_ratio(a: Segment, b: Segment) -> float:
    """Rasio overlap terhadap segmen LEBIH PENDEK — supaya segmen pendek yang
    termuat di segmen panjang tetap kedeteksi sebagai duplikat."""
    a_start, a_end = hms_to_sec(a.start), hms_to_sec(a.end)
    b_start, b_end = hms_to_sec(b.start), hms_to_sec(b.end)
    overlap = max(0.0, min(a_end, b_end) - max(a_start, b_start))
    shorter = min(a_end - a_start, b_end - b_start)
    return overlap / shorter if shorter > 0 else 0.0


def deduplicate_overlapping_segments(segments: list[Segment], max_overlap: float = 0.65) -> list[Segment]:
    """Remove candidate segments that heavily overlap with a higher-priority segment.
    Keeps segment with higher hook_score / confidence."""
    if not segments:
        return []
    # Sort by hook_score (if available) then confidence desc
    sorted_segs = sorted(
        segments,
        key=lambda s: (getattr(s, "hook_score", 0) or 0, getattr(s, "confidence", 0.0)),
        reverse=True
    )
    kept: list[Segment] = []
    for s in sorted_segs:
        s_start = hms_to_sec(s.start)
        s_end = hms_to_sec(s.end)
        s_dur = max(0.1, s_end - s_start)
        overlaps = False
        for k in kept:
            k_start = hms_to_sec(k.start)
            k_end = hms_to_sec(k.end)
            k_dur = max(0.1, k_end - k_start)
            # Calculate overlap interval
            overlap_start = max(s_start, k_start)
            overlap_end = min(s_end, k_end)
            if overlap_end > overlap_start:
                overlap_dur = overlap_end - overlap_start
                ratio = overlap_dur / min(s_dur, k_dur)
                if ratio > max_overlap:
                    overlaps = True
                    break
        if not overlaps:
            kept.append(s)
    # Restore chronological order
    return sorted(kept, key=lambda s: hms_to_sec(s.start))


def merge_and_dedupe(all_segments: list[Segment], overlap_threshold: float = 0.7) -> list[Segment]:
    """Gabung + buang duplikat: kalau overlap > threshold, ambil confidence
    lebih tinggi."""
    ordered = sorted(all_segments, key=lambda s: hms_to_sec(s.start))
    kept: list[Segment] = []
    for seg in ordered:
        duplicate_of = None
        for i, existing in enumerate(kept):
            if overlap_ratio(seg, existing) > overlap_threshold:
                duplicate_of = i
                break
        if duplicate_of is None:
            kept.append(seg)
        elif seg.confidence > kept[duplicate_of].confidence:
            kept[duplicate_of] = seg
    return kept


def _write_segments_atomic(job_id: str, segments: list[Segment]):
    """Tulis ke .tmp dulu, rename ke final — supaya is_complete tidak pernah
    lihat file setengah-jadi (plan Section 4.1 bug trap)."""
    final_path = Path(f"data/segments/{job_id}.json")
    final_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = final_path.with_suffix(".json.tmp")
    tmp_path.write_text(
        json.dumps([s.model_dump() for s in segments], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    os.replace(str(tmp_path), str(final_path))


@register
class AnalyzeStage(Stage):
    name = "analyze"
    depends_on = ["transcribe"]

    def is_complete(self, job_id: str, db) -> bool:
        # Plan Section 4.1 bug trap: cek file AND sinyal DB (metrics entry).
        # File ada (atomic write) + metrics recorded = stage beneran selesai.
        if not Path(f"data/segments/{job_id}.json").exists():
            return False
        if db is None:
            return True
        row = db.conn.execute(
            "SELECT 1 FROM metrics WHERE job_id=? AND stage='analyze' LIMIT 1",
            (job_id,),
        ).fetchone()
        return row is not None

    def run(self, job_id: str, db, config):
        transcript_path = Path(f"data/transcripts/{job_id}.json")
        if not transcript_path.exists():
            return StageResult(status=StageStatus.FAILED, error=f"Transcript not found: {transcript_path}")

        transcript = load_transcript(transcript_path)

        try:
            chunks = chunk_transcript(
                transcript,
                chunk_min=config.chunk_duration_min,
                overlap_min=config.chunk_overlap_min,
            )
        except ValueError as e:
            return StageResult(status=StageStatus.FAILED, error=str(e))

        if not chunks:
            _write_segments_atomic(job_id, [])
            db.record_metric(job_id, stage="analyze", cost_usd=0.0, extra={"segments_found": 0, "chunks_processed": 0})
            return StageResult(status=StageStatus.DONE, metadata={"segments_found": 0})

        preset = "affiliate"
        if db is not None:
            try:
                job = db.get_job(job_id) if hasattr(db, "get_job") else None
                if job and isinstance(job, dict) and job.get("preset"):
                    preset = job["preset"]
            except Exception as e:
                logger.warning("failed_to_get_job_preset", job_id=job_id, error=str(e))

        client = genai.Client(api_key=config.google_api_key)
        system_prompt = get_preset_prompt(preset)

        all_segments: list[Segment] = []
        total_cost = 0.0
        chunks_processed = 0
        total_chunks = len(chunks)

        def _analyze_one(chunk) -> tuple[list[Segment], dict]:
            chunk_text = format_chunk_for_prompt(chunk)
            # analyze_chunk sudah retry 3x sendiri — exception di sini = beneran
            # gagal; skip chunk, JANGAN gagalkan job (plan Section 11).
            try:
                return analyze_chunk(client, system_prompt, chunk_text, config.analyze_model)
            except Exception as e:
                logger.warning("analyze_chunk_skipped", error=str(e))
                return [], {"input_tokens": 0, "output_tokens": 0}

        # Chunk independen satu sama lain → parallel call Gemini (3 worker).
        # Retry total per chunk tetap 3x (tenacity), hanya wall-clock yang turun.
        import runtime
        from concurrent.futures import ThreadPoolExecutor, as_completed
        pool = ThreadPoolExecutor(max_workers=getattr(config, "analyze_parallel", 3))
        futs = {pool.submit(_analyze_one, c): c for c in chunks}
        killed = False
        for i, fut in enumerate(as_completed(futs), 1):
            if runtime.stop_requested():
                killed = True
                break  # killed: jangan menunggu chunk tersisa (hemat biaya API)
            print(f"    analyze {i}/{total_chunks} chunks")
            segments, usage = fut.result()
            all_segments.extend(segments)
            total_cost += calc_cost(usage, config.analyze_model)
            chunks_processed += 1
        if killed or runtime.stop_requested(job_id):
            return StageResult(status=StageStatus.FAILED, error="Killed")

        all_segments = deduplicate_overlapping_segments(all_segments)
        merged = merge_and_dedupe(all_segments)
        final = [s for s in merged if s.confidence >= config.confidence_threshold]

        if final:
            caption_prompt_path = Path("prompts/caption_generator.txt")
            if caption_prompt_path.exists():
                caption_prompt = caption_prompt_path.read_text(encoding="utf-8")
                try:
                    captions = generate_captions(client, caption_prompt, final, config.analyze_model)
                except Exception as e:
                    logger.warning("caption_generation_skipped", error=str(e))
                    captions = {}
                for i, seg in enumerate(final):
                    seg.caption_text = captions.get(i) or fallback_caption(seg)
                    if not seg.affiliate_caption:
                        seg.affiliate_caption = seg.caption_text
                    if not seg.hashtags:
                        extracted = [w for w in (seg.caption_text or "").split() if w.startswith("#")]
                        seg.hashtags = extracted if extracted else ["#racuntiktok", "#affiliate"]
            else:
                for seg in final:
                    seg.caption_text = fallback_caption(seg)
                    if not seg.affiliate_caption:
                        seg.affiliate_caption = seg.caption_text
                    if not seg.hashtags:
                        seg.hashtags = ["#racuntiktok", "#affiliate"]

        _write_segments_atomic(job_id, final)
        db.insert_segments(job_id, final)
        db.record_metric(
            job_id,
            stage="analyze",
            cost_usd=total_cost,
            extra={"segments_found": len(final), "chunks_processed": chunks_processed},
        )

        return StageResult(
            status=StageStatus.DONE,
            output_path=f"data/segments/{job_id}.json",
            metadata={"segments_found": len(final), "cost_usd": total_cost},
        )
