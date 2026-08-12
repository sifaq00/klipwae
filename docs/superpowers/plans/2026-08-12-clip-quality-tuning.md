# Clip Quality Tuning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Naikkan kualitas klip end-to-end (subtitle sync, framing kamera, potongan kalimat, deteksi produk) ke standar Opus Clip, terukur via A/B terhadap baseline `data/clips_final/`.

**Architecture:** Perubahan lokal per stage backend — tidak ada perubahan arsitektur. Fix bug (diarization fallback, wrap subtitle) → upgrade transkripsi (large-v3-turbo int8_float16, auto-language, initial prompt) → align potongan klip ke kalimat → parameter reframe jadi config untuk A/B tanpa edit kode → default caption aman TikTok UI → golden fixtures baru untuk deteksi produk. TDD per task.

**Tech Stack:** Python 3.11, FastAPI, faster-whisper, ffmpeg/NVENC, YOLO11n, PyAnnote, pydantic-settings, pytest. Frontend tidak berubah.

## Global Constraints

- Hardware: RTX 2050 4GB — whisper cuda WAJIB `compute_type="int8_float16"` (float16 OOM di 4GB).
- Semua perintah pytest dijalankan dari `backend/` dengan `.venv\Scripts\python.exe -m pytest`.
- Jangan ubah behavior stage ketika config default tidak diset (backward compatible).
- `.env` user TIDAK boleh di-commit; `.env.example` ikut berubah.
- Jangan sentuh frontend (`frontend/`) sama sekali.
- Model whisper path lokal sudah di-handle `transcribe.py:72-73` — jangan ubah logika itu.
- Git: repo baru di `auto-clipper-app/` (repo parent `D:\Project` berisi folder lain yang tidak relevan).
- Bahasa: semua test/komentar baru Bahasa Indonesia (konsisten codebase), commit message bahasa Inggris.

---

### Task 0: Repo sendiri + baseline commit

**Files:**
- Create: `.gitignore` (root proyek)
- Semua file proyek

**Interfaces:**
- Consumes: —
- Produces: repo git ter-isolasi untuk auto-clipper-app; baseline sebelum perubahan.

- [ ] **Step 1: Init repo + .gitignore root**

```bash
git init
```

Create `.gitignore` di root `D:\Project\auto-clipper-app\.gitignore`:

```gitignore
# Python
backend/.env
backend/data/
backend/models/
backend/logs/
backend/*.db
__pycache__/
*.pyc
.venv/
*.egg-info/
*.tmp
.pytest_cache/

# Node
frontend/node_modules/
frontend/dist/
frontend/tsconfig.tsbuildinfo

# OS
Thumbs.db
```

- [ ] **Step 2: Initial commit**

```bash
git add -A
git commit -m "chore: initial commit — auto-clipper studio + quality tuning spec/plan"
```

Expected: semua file (kecuali .env, data/, models/, node_modules/) ter-commit. Cek: `git status` bersih.

---

### Task 1: Fix diarization fallback — MAR gagal tidak boleh "left" semua

**Files:**
- Modify: `backend/stages/reframe/diarization.py:80-82`
- Test: `backend/tests/test_diarization.py` (baru)

**Interfaces:**
- Consumes: `map_speakers_to_sides(diar: list[tuple], mar: list[tuple]) -> list[tuple]` (eksisting)
- Produces: behavior fix — `mar` kosong/None → semua side `"previous"`.

- [ ] **Step 1: Write failing test**

Create `backend/tests/test_diarization.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from stages.reframe.diarization import map_speakers_to_sides


def test_mar_none_falls_back_to_previous():
    diar = [(0.0, 2.0, "SPEAKER_00"), (2.0, 4.0, "SPEAKER_01")]
    out = map_speakers_to_sides(diar, None)
    assert out == [(0.0, 2.0, "previous"), (2.0, 4.0, "previous")]


def test_mar_empty_falls_back_to_previous():
    diar = [(0.0, 2.0, "SPEAKER_00")]
    out = map_speakers_to_sides(diar, [])
    assert out == [(0.0, 2.0, "previous")]


def test_mar_normal_still_votes():
    diar = [(0.0, 3.0, "SPEAKER_00")]
    mar = [(0.0, 3.0, "left")]
    out = map_speakers_to_sides(diar, mar)
    assert out == [(0.0, 3.0, "left")]
```

- [ ] **Step 2: Run test to verify it fails**

Run (dari `backend/`): `.venv\Scripts\python.exe -m pytest tests/test_diarization.py -v`
Expected: `test_mar_none_falls_back_to_previous` FAIL — dapat `("left")` bukan `"previous"`.

- [ ] **Step 3: Implement fix**

`diarization.py:80-82` — ganti blok fallback:

```python
    if not diar:
        return mar
    if not mar:
        # MAR gagal — jangan tebak sisi. "previous" diserahkan ke
        # build_camera_path (lanjut sisi aktif).
        return [(s, e, "previous") for s, e, _ in diar]
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_diarization.py -v`
Expected: 3 PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/stages/reframe/diarization.py backend/tests/test_diarization.py
git commit -m "fix(reframe): diarization fallback maps all speakers to previous, not left"
```

---

### Task 2: Caption wrap dinamis — max_chars dari font size

**Files:**
- Modify: `backend/stages/caption.py:109-121` (`_wrap`), `:96-103` (pemanggil)
- Test: `backend/tests/test_caption.py`

**Interfaces:**
- Consumes: `_wrap(texts: list[str], max_chars: int) -> list[str]` (eksisting)
- Produces: `_wrap` tetap signature sama; pemanggil hitung `max_chars` dinamis: `max(12, int(1000 / (size * 0.5)))` (margin kiri+kanan 40px dari `_ass_header`).

- [ ] **Step 1: Write failing test**

Tambah di `backend/tests/test_caption.py`:

```python
def test_wrap_scales_with_font_size():
    words = [{"text": f"kata{i}", "start": i * 0.3, "end": i * 0.3 + 0.25} for i in range(30)]
    # size 96 → max_chars = 20; baris wrap tidak boleh melebihi 20 char
    ass = generate_ass(words, style="static", style_cfg=_cfg(size=96))
    for line in ass.splitlines():
        if line.startswith("Dialogue:"):
            text = line.split(",", 9)[-1]
            for visual_line in text.split("\\N"):
                assert len(visual_line.replace(" ", "")) <= 20, f"line too long: {visual_line}"
    # size 60 → max_chars = 33
    ass60 = generate_ass(words, style="static", style_cfg=_cfg(size=60))
    for line in ass60.splitlines():
        if line.startswith("Dialogue:"):
            text = line.split(",", 9)[-1]
            for visual_line in text.split("\\N"):
                assert len(visual_line.replace(" ", "")) <= 33, f"line too long: {visual_line}"
```

Catatan: word `kata{i}` 5 char — 30 kata = 30×5=150 char total; baris 20 char → ~8 baris visual. Assert tanpa spasi biar tidak kena padding.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_caption.py::test_wrap_scales_with_font_size -v`
Expected: FAIL — `_wrap` default 38 > 20 (baris visual 38-char ada).

- [ ] **Step 3: Implement**

Di `generate_ass` (static branch, `caption.py:174`) dan highlight branch (`caption.py:150`):

```python
    # Wrap dinamis: batas char disesuaikan ukuran font biar baris tidak
    # melebihi lebar 1080 (margin kiri/kanan 40px). 0.5 ≈ lebar char rata2.
    wrap_max_chars = max(12, int(1000 / (fs_default * 0.5)))
```

Highlight branch (`:150`): `for li, line in enumerate(wrapped):` — `wrapped` dihitung di `:138` dari `_wrap(texts)` → ubah jadi `_wrap(texts, wrap_max_chars)`.
Static branch (`:174`): `wrapped = _wrap([...], wrap_max_chars)`.
`_wrap` signature tidak berubah (default `max_chars=38` tetap aman untuk pemanggil lain).

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_caption.py -v`
Expected: semua PASS (termasuk test lama).

- [ ] **Step 5: Commit**

```bash
git add backend/stages/caption.py backend/tests/test_caption.py
git commit -m "feat(caption): wrap max_chars scales with font size to fit 1080 width"
```

---

### Task 3: Whisper — default large-v3-turbo + compute type aman 4GB

**Files:**
- Modify: `backend/config.py:9` (default model), `backend/stages/transcribe.py:78` (compute type), `backend/.env.example`, `backend/tests/test_config.py:17`, `backend/tests/test_transcribe.py`

**Interfaces:**
- Consumes: `Settings.whisper_model` (eksisting)
- Produces: helper baru `whisper_compute_type(device: str) -> str` di `stages/transcribe.py` — `"int8"` untuk cpu, `"int8_float16"` untuk lainnya.

- [ ] **Step 1: Write failing tests**

`test_config.py` — update `test_settings_defaults` (`:17`):

```python
        assert s.whisper_model == "large-v3-turbo"
```

Tambah di `test_transcribe.py`:

```python
def test_whisper_compute_type():
    from stages.transcribe import whisper_compute_type
    assert whisper_compute_type("cpu") == "int8"
    assert whisper_compute_type("cuda") == "int8_float16"
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_transcribe.py -v`
Expected: `test_settings_defaults` FAIL (masih "medium"), `test_whisper_compute_type` FAIL (ImportError).

- [ ] **Step 3: Implement**

`config.py:9`: `whisper_model: str = "large-v3-turbo"`

`transcribe.py` — tambah helper + pakai di `run_whisper`:

```python
def whisper_compute_type(device: str) -> str:
    """int8_float16 untuk cuda: RTX 2050 4GB tidak muat float16 penuh,
    int8_float16 kualitas hampir setara dengan VRAM ~1.3GB."""
    return "int8" if device == "cpu" else "int8_float16"
```

`transcribe.py:78`:

```python
    model = WhisperModel(model_path, device=device, compute_type=whisper_compute_type(device))
```

`.env.example`: `WHISPER_MODEL=large-v3-turbo` + catatan komentar:

```
# MAX_CONCURRENT_JOBS=1  # kalau 2 job transcribe bareng OOM di GPU 4GB
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_config.py tests/test_transcribe.py -v`
Expected: semua PASS.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/stages/transcribe.py backend/.env.example backend/tests/test_config.py backend/tests/test_transcribe.py
git commit -m "feat(transcribe): default large-v3-turbo with int8_float16 for 4GB GPU"
```

---

### Task 4: Whisper — auto language + initial prompt produk

**Files:**
- Modify: `backend/stages/transcribe.py:81-86` (panggil `model.transcribe`), `:56` (panggil `run_whisper`), `backend/config.py` (field baru), `backend/.env.example`, `backend/tests/test_transcribe.py`

**Interfaces:**
- Consumes: `Settings.whisper_initial_prompt: str = ""` (baru)
- Produces: `run_whisper(audio_path, model_size, device, initial_prompt: str = "") -> list[dict]` — signature berubah, tambah param ke-4 dengan default.

- [ ] **Step 1: Write failing test**

Tambah di `test_transcribe.py`:

```python
def test_run_whisper_language_auto_and_initial_prompt(tmp_path):
    from types import SimpleNamespace
    from unittest.mock import MagicMock, patch

    audio = tmp_path / "a.wav"
    audio.write_bytes(b"x")
    model = MagicMock()
    seg = SimpleNamespace(text="halo", start=0.0, end=1.0, words=[])
    info = SimpleNamespace(duration=10.0)
    model.transcribe.return_value = (iter([seg]), info)

    with patch("faster_whisper.WhisperModel", return_value=model):
        from stages.transcribe import run_whisper
        run_whisper(audio, "large-v3-turbo", "cpu", initial_prompt="Somethinc Creatine")

    kwargs = model.transcribe.call_args.kwargs
    assert kwargs["language"] is None
    assert kwargs["initial_prompt"] == "Somethinc Creatine"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcribe.py::test_run_whisper_language_auto_and_initial_prompt -v`
Expected: FAIL — TypeError `run_whisper()` unexpected keyword `initial_prompt` (atau language masih "id").

- [ ] **Step 3: Implement**

`config.py` — tambah field:

```python
    whisper_initial_prompt: str = ""
```

`transcribe.py` — `TranscribeStage.run` panggil:

```python
        segments = run_whisper(
            audio_path, config.whisper_model, config.whisper_device,
            initial_prompt=getattr(config, "whisper_initial_prompt", ""),
        )
```

`run_whisper` signature + panggil transcribe:

```python
def run_whisper(audio_path: Path, model_size: str = "medium", device: str = "cpu",
                initial_prompt: str = "") -> list[dict]:
    ...
    segments, info = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        language=None,  # auto-detect: nama produk Inggris tidak jadi fonetik Indonesia
        vad_filter=True,
        initial_prompt=initial_prompt or None,
    )
```

`.env.example`: `WHISPER_INITIAL_PROMPT=` (isi: daftar istilah produk yang sering muncul, dipisah koma).

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_transcribe.py -v`
Expected: semua PASS. Cek `test_transcribe_atomic_write` mock (`:32`) — update signature kalau error:

```python
            transcribe.run_whisper = lambda audio, m, d, ip="": fake_segments
```

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/stages/transcribe.py backend/.env.example backend/tests/test_transcribe.py
git commit -m "feat(transcribe): auto language detection with product initial prompt"
```

---

### Task 5: Clip — align potongan ke kalimat (jeda bicara)

**Files:**
- Modify: `backend/stages/clip.py` (fungsi baru `align_boundary` + pemakaian di `ClipStage.run`), `backend/config.py` (field baru), `backend/.env.example`, `backend/tests/test_clip.py`

**Interfaces:**
- Consumes: `_load_words(job_id) -> list[dict]` (eksisting), `split_segment_ranges(...)` (eksisting)
- Produces: `align_boundary(words: list[dict], sec: float, direction: str, window: float = 3.0, min_gap: float = 0.5) -> float` — geser boundary ke awal kata setelah jeda bicara ≥ min_gap dalam window; tak ada jeda → return `sec`. `Settings.clip_align_sentence: bool = True`.

- [ ] **Step 1: Write failing test**

Tambah di `test_clip.py`:

```python
from stages.clip import align_boundary


def test_align_start_moves_back_to_gap():
    # jeda 0.8s di 8.2 → kata berikut mulai 9.0; sec=10 di tengah kalimat
    words = [{"text": f"w{i}", "start": float(i) * 1.0, "end": float(i) * 1.0 + 0.8} for i in range(12)]
    # buat gap: hilangkan kata 8..8.9, lanjut di 10.0? sederhananya:
    words = [
        {"text": "a", "start": 0.0, "end": 0.8},
        {"text": "b", "start": 1.0, "end": 1.8},
        {"text": "c", "start": 2.0, "end": 2.8},
        {"text": "d", "start": 5.0, "end": 5.8},   # gap 2.2s sebelum d
        {"text": "e", "start": 6.0, "end": 6.8},
    ]
    # sec=6.5 di tengah kalimat d-e → mundur ke awal d (5.0)
    assert align_boundary(words, 6.5, "start") == 5.0


def test_align_start_no_gap_in_window():
    words = [
        {"text": "a", "start": 0.0, "end": 0.9},
        {"text": "b", "start": 1.0, "end": 1.9},
        {"text": "c", "start": 2.0, "end": 2.9},
    ]
    assert align_boundary(words, 2.5, "start") == 2.5


def test_align_end_moves_forward_to_next_sentence():
    words = [
        {"text": "a", "start": 0.0, "end": 0.8},
        {"text": "b", "start": 1.0, "end": 1.8},
        {"text": "c", "start": 2.0, "end": 2.8},
        {"text": "d", "start": 6.0, "end": 6.8},   # gap 3.2s sebelum d
    ]
    # sec=3 di tengah jeda, kalimat lanjut di 6.0 → end = 6.0 (mulai kalimat baru)
    assert align_boundary(words, 3.0, "end") == 6.0


def test_align_end_no_gap_in_window():
    words = [
        {"text": "a", "start": 0.0, "end": 0.8},
        {"text": "b", "start": 1.0, "end": 1.8},
    ]
    assert align_boundary(words, 1.5, "end") == 1.5


def test_align_empty_words():
    assert align_boundary([], 5.0, "start") == 5.0
    assert align_boundary([], 5.0, "end") == 5.0
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_clip.py -v`
Expected: ImportError `align_boundary` (belum ada).

- [ ] **Step 3: Implement**

`clip.py` — fungsi baru (di bawah `split_segment_ranges`):

```python
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
```

`ClipStage.run` — setelah `ranges = split_segment_ranges(...)` (`:133`):

```python
            ranges = split_segment_ranges(start_sec, end_sec, words)
            if getattr(config, "clip_align_sentence", False) and words:
                # Kalimat utuh: mundur ke awal kalimat, maju ke awal kalimat berikut.
                s0, e0 = ranges[0]
                ranges[0] = (align_boundary(words, s0, "start"), e0)
                sL, eL = ranges[-1]
                ranges[-1] = (sL, align_boundary(words, eL, "end"))
```

Catatan: DB `start_time`/`end_time` di-`upsert_clip_segment` memakai nilai s/e hasil align (pre-buffer) — konsisten dengan window subtitle `caption.py` yang mengurangi `CLIP_BUFFER_SEC`; tidak perlu ubah caption.

`config.py`:

```python
    clip_align_sentence: bool = True
```

`.env.example`: `CLIP_ALIGN_SENTENCE=true`

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_clip.py -v`
Expected: semua PASS (test lama tidak berubah karena align digate config).

- [ ] **Step 5: Commit**

```bash
git add backend/stages/clip.py backend/config.py backend/.env.example backend/tests/test_clip.py
git commit -m "feat(clip): align cuts to sentence boundaries using speech gaps"
```

---

### Task 6: Reframe — konstanta jadi config untuk A/B

**Files:**
- Modify: `backend/config.py` (10 field baru), `backend/stages/reframe/render_tracked.py` (parameter), `backend/stages/reframe/__init__.py` (`_render_tracked` + `ReframeStage.run`), `backend/.env.example`, `backend/tests/test_reframe.py` (default test kecil)

**Interfaces:**
- Consumes: `Settings.reframe_*` (baru)
- Produces: `render_tracked(input_path, camera_path, boxes_by_frame, zone_map, fps, output_path, target_w=1080, target_h=1920, clip_no="", **cfg)` — menerima `cfg` dict opsional berisi param kamera; default = nilai konstanta baru.

- [ ] **Step 1: Write failing test**

Tambah di `test_reframe.py` (jangan kena skip marker — marker module-level skip video; test ini tanpa video):

```python
class TestRenderTrackedDefaults:
    def test_default_params_preserved(self):
        from stages.reframe.render_tracked import render_tracked
        import inspect
        sig = inspect.signature(render_tracked)
        assert sig.parameters["head_bias"].default == 0.30
        assert sig.parameters["zoom_min"].default == 1.15
        assert sig.parameters["zoom_max"].default == 2.0
        assert sig.parameters["zoom_fit"].default == 0.6
```

Note: `pytestmark` module-level skip jika `TEST_VIDEO` tidak ada — pastikan `TEST_VIDEO.exists()` (`backend/data/raw/DkPEGUUnJGE.mp4`) — kalau tidak ada, test ini ikut skip. Pindahkan class ini ke file baru `test_render_tracked.py` tanpa skip marker:

Create `backend/tests/test_render_tracked.py`:

```python
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))


def test_default_params_preserved():
    from stages.reframe.render_tracked import render_tracked
    import inspect
    sig = inspect.signature(render_tracked)
    assert sig.parameters["head_bias"].default == 0.30
    assert sig.parameters["zoom_min"].default == 1.15
    assert sig.parameters["zoom_max"].default == 2.0
    assert sig.parameters["zoom_fit"].default == 0.6
    assert sig.parameters["smooth_alpha"].default == 0.12
```

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv\Scripts\python.exe -m pytest tests/test_render_tracked.py -v`
Expected: FAIL — param `head_bias` tidak ada di signature.

- [ ] **Step 3: Implement**

`config.py` — 10 field baru:

```python
    reframe_zoom_min: float = 1.15
    reframe_zoom_max: float = 2.0
    reframe_zoom_fit: float = 0.6
    reframe_head_bias: float = 0.30
    reframe_smooth_alpha: float = 0.12
    reframe_target_alpha: float = 0.35
    reframe_deadband: float = 0.006
    reframe_hold_sec: float = 0.5
    reframe_zoom_idle: float = 1.05
    reframe_zoom_ease: float = 0.06
```

`render_tracked.py` — ubah signature + semua referensi konstanta jadi variabel lokal:

```python
def render_tracked(
    input_path: Path,
    camera_path: list[tuple[float, float, str]],
    boxes_by_frame: list[dict],
    zone_map: dict[int, int],
    fps: float,
    output_path: Path,
    target_w: int = 1080,
    target_h: int = 1920,
    clip_no: str = "",
    smooth_alpha: float = 0.12,
    target_alpha: float = 0.35,
    deadband: float = 0.006,
    hold_sec: float = 0.5,
    head_bias: float = 0.30,
    zoom_fit: float = 0.6,
    zoom_min: float = 1.15,
    zoom_max: float = 2.0,
    zoom_idle: float = 1.05,
    zoom_ease: float = 0.06,
):
```

Ganti di dalam body: `SMOOTH_ALPHA`→`smooth_alpha`, `TARGET_ALPHA`→`target_alpha`, `DEADBAND`→`deadband`, `HOLD_SEC`→`hold_sec` (dan `hold_frames = int(hold_sec * fps)`), `HEAD_BIAS`→`head_bias`, `ZOOM_FIT`→`zoom_fit`, `ZOOM_MIN`→`zoom_min`, `ZOOM_MAX`→`zoom_max`, `ZOOM_IDLE`→`zoom_idle`, `ZOOM_EASE`→`zoom_ease`. Hapus konstanta module yang sudah jadi param (sisakan kalau dipakai render lain — cek `render.py` dulu; `CONF_MIN` dipakai `tracker.py` import? tracker.py punya CONF_MIN sendiri — aman hapus dari render_tracked).

`__init__.py` — `_render_tracked` terima config:

```python
def _render_tracked(clip, camera_path, reframed_path, fps, clip_no: str = "", config=None) -> bool:
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
        cfg = {}
        if config is not None:
            cfg = {
                "smooth_alpha": getattr(config, "reframe_smooth_alpha", 0.12),
                "target_alpha": getattr(config, "reframe_target_alpha", 0.35),
                "deadband": getattr(config, "reframe_deadband", 0.006),
                "hold_sec": getattr(config, "reframe_hold_sec", 0.5),
                "head_bias": getattr(config, "reframe_head_bias", 0.30),
                "zoom_fit": getattr(config, "reframe_zoom_fit", 0.6),
                "zoom_min": getattr(config, "reframe_zoom_min", 1.15),
                "zoom_max": getattr(config, "reframe_zoom_max", 2.0),
                "zoom_idle": getattr(config, "reframe_zoom_idle", 1.05),
                "zoom_ease": getattr(config, "reframe_zoom_ease", 0.06),
            }
        return render_tracked(clip, camera_path, boxes, zone_map, fps, reframed_path,
                              clip_no=clip_no, **cfg)
    except Exception as e:
        logger.warning("render_tracked_fallback", error=str(e), clip=clip.name)
        return False
```

`ReframeStage.run` — dua pemanggilan `_render_tracked` tambah argumen `config=config` (`:100`, `:105`).

`.env.example` — 10 baris (nama env = field pydantic uppercase):

```
REFRAME_ZOOM_MIN=1.15
REFRAME_ZOOM_MAX=2.0
REFRAME_ZOOM_FIT=0.6
REFRAME_HEAD_BIAS=0.30
REFRAME_SMOOTH_ALPHA=0.12
REFRAME_TARGET_ALPHA=0.35
REFRAME_DEADBAND=0.006
REFRAME_HOLD_SEC=0.5
REFRAME_ZOOM_IDLE=1.05
REFRAME_ZOOM_EASE=0.06
```

- [ ] **Step 4: Run tests to verify pass**

Run: `.venv\Scripts\python.exe -m pytest tests/test_render_tracked.py tests/test_reframe.py -v`
Expected: PASS. Kalau `TEST_VIDEO` ada, smoke render tetap jalan dengan default baru.

- [ ] **Step 5: Commit**

```bash
git add backend/config.py backend/stages/reframe/render_tracked.py backend/stages/reframe/__init__.py backend/.env.example backend/tests/test_render_tracked.py
git commit -m "feat(reframe): camera params as config for A/B tuning without code edits"
```

---

### Task 7: Caption — margin TikTok safe zone + pop scale halus

**Files:**
- Modify: `backend/utils/caption_style.py:11` (`margin_v` default), `backend/stages/caption.py:135` (pop scale), `backend/tests/test_caption.py`

**Interfaces:**
- Consumes: `DEFAULT_STYLE` (eksisting)
- Produces: default baru `margin_v=240`, pop `\fscx106\fscy106`.

- [ ] **Step 1: Write failing test**

Update `test_caption.py::test_generate_ass_highlight_karaoke_lines` (`:119`):

```python
    assert "\\fscx106\\fscy106" in ass
```

Tambah:

```python
def test_default_style_margin_safe_for_tiktok():
    from utils.caption_style import DEFAULT_STYLE
    assert DEFAULT_STYLE["margin_v"] == 240
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `.venv\Scripts\python.exe -m pytest tests/test_caption.py -v`
Expected: `test_generate_ass_highlight_karaoke_lines` FAIL (112), `test_default_style_margin_safe_for_tiktok` FAIL (100).

- [ ] **Step 3: Implement**

`utils/caption_style.py:11`: `"margin_v": 240,  # TikTok UI safe zone (~300px bawah) — subtitle tidak ketutup`

`stages/caption.py:135`: `active_scale = "\\fscx106\\fscy106" if pop else ""`

Catatan deploy: kalau `backend/data/caption_style.json` ada (gaya global tersimpan), nilai lamanya menimpa default — update manual atau hapus file biar ke-reset (satu baris di `.env`? tidak — instruksi manual di step 4).

- [ ] **Step 4: Run tests + reset global style**

Run: `.venv\Scripts\python.exe -m pytest tests/test_caption.py -v`
Expected: PASS.

Reset gaya global (kalau file ada): `Remove-Item backend\data\caption_style.json` — konfirmasi dengan user dulu kalau dia punya style custom yang ingin disimpan.

- [ ] **Step 5: Commit**

```bash
git add backend/utils/caption_style.py backend/stages/caption.py backend/tests/test_caption.py
git commit -m "feat(caption): TikTok-safe bottom margin and softer pop scale"
```

---

### Task 8: Golden fixtures baru — deteksi produk edge cases

**Files:**
- Create: `backend/tests/fixtures/golden_transcripts/006_daftar_cepat.json`, `007_promo_read.json`, `008_bandingkan_dua.json`

**Interfaces:**
- Consumes: harness `test_golden.py` (auto-glob `FIXTURES_DIR/*.json`, mock `analyze_chunk` return `expected_segments`)
- Produces: 3 fixture sesuai format: `{"transcript": [{text,start,end}], "expected_segments": [{start, end, min_confidence?}]}` — start/end transkrip = detik (float), expected = `HH:MM:SS`.

- [ ] **Step 1: Create fixtures**

`006_daftar_cepat.json` — host sebut 3 produk cepat dalam 1 daftar, cuma 1 yang diulas:

```json
{
  "transcript": [
    {"text": "kali ini aku mau kasih rekomendasi produk skincare", "start": 0.0, "end": 3.0},
    {"text": "ada serum vitamin c, toner, dan moisturizer", "start": 3.0, "end": 6.0},
    {"text": "yang paling aku suka serum vitamin c dari brand lokal", "start": 6.0, "end": 9.0},
    {"text": "dipakai dua minggu wajah kelihatan lebih cerah", "start": 9.0, "end": 12.0}
  ],
  "expected_segments": [
    {"start": "00:00:06", "end": "00:00:12", "min_confidence": 0.75}
  ]
}
```

`007_promo_read.json` — host baca naskah iklan monoton (negatif — harus 0 segmen):

```json
{
  "transcript": [
    {"text": "produk ini bagus sekali", "start": 0.0, "end": 2.0},
    {"text": "pesan sekarang juga dapatkan diskon lima puluh persen", "start": 2.0, "end": 5.0},
    {"text": "kunjungi website kami di link deskripsi", "start": 5.0, "end": 7.0}
  ],
  "expected_segments": []
}
```

`008_bandingkan_dua.json` — bandingkan 2 produk, keduanya jelas (2 segmen):

```json
{
  "transcript": [
    {"text": "banyak yang tanya bedanya creatine dan protein", "start": 0.0, "end": 3.0},
    {"text": "creatine buat power saat latihan angkat beban", "start": 3.0, "end": 6.0},
    {"text": "sedangkan whey protein buat pemulihan otot", "start": 6.0, "end": 9.0}
  ],
  "expected_segments": [
    {"start": "00:00:03", "end": "00:00:06", "min_confidence": 0.75},
    {"start": "00:00:06", "end": "00:00:09", "min_confidence": 0.75}
  ]
}
```

- [ ] **Step 2: Run golden tests**

Run: `.venv\Scripts\python.exe -m pytest tests/test_golden.py -v`
Expected: PASS — output menyebut 8 fixtures (`test_fixture_format`).

- [ ] **Step 3: Commit**

```bash
git add backend/tests/fixtures/golden_transcripts/006_daftar_cepat.json backend/tests/fixtures/golden_transcripts/007_promo_read.json backend/tests/fixtures/golden_transcripts/008_bandingkan_dua.json
git commit -m "test(analyze): golden fixtures for product listing, promo read, and product comparison"
```

---

### Task 9: Validasi penuh + A/B reframe

**Files:**
- Tidak ada perubahan kode — verifikasi + sesi A/B manual.

**Interfaces:**
- Consumes: semua task 0-8.

- [ ] **Step 1: Full test suite**

Run (dari `backend/`): `.venv\Scripts\python.exe -m pytest tests -q`
Expected: semua PASS.

- [ ] **Step 2: Frontend sanity (tidak diubah, cek tidak rusak)**

Run (dari `frontend/`): `npm run build`
Expected: build sukses.

- [ ] **Step 3: Sesi A/B reframe manual**

- Pilih 2-3 klip dari `backend/data/clips_raw/` (1 solo + 1 split-screen).
- Render versi lama (nilai lama: zoom_min 1.1, zoom_max 1.8, zoom_fit 0.62, head_bias 0.32) vs baru (default baru) — render manual via snippet Python atau set `.env` + restart + re-run job.
- Kriteria: framing kepala (head_bias), ukuran orang di frame (zoom_fit), kecepatan pan (smooth_alpha), switch sisi saat ganti pembicara (split-screen).
- Set angka final di `backend/.env` (env `REFRAME_*`).
- Kalau `large-v3-turbo` OOM / salah transkrip: cek `WHISPER_INITIAL_PROMPT` dulu, baru turun ke `medium`.

- [ ] **Step 4: E2E 1 episode**

- POST `/api/jobs` dengan URL YouTube podcast pendek (~10-20 menit).
- Review klip final vs baseline: subtitle sync, framing, sisi split-screen, kalimat tidak terpotong.
- Kalau `MAX_CONCURRENT_JOBS` default 2 dan OOM: set 1 di `.env` + dokumentasi.

- [ ] **Step 5: Commit**

```bash
git add -A
git commit -m "docs: tuning validation results"
```

(Commit hanya jika ada perubahan — kalau tidak, skip.)

---

## Self-Review Checklist (dijalankan setelah implementasi)

1. **Spec coverage:** §1a→Task 1, §1b→Task 2, §2a→Task 3, §2b→Task 4, §3→Task 5, §4a→Task 6, §4b→Task 9, §5a/5b→Task 7, §6→Task 8, §7→Task 9. Lengkap.
2. **Placeholder scan:** semua step punya kode konkret; tidak ada "TBD/TODO".
3. **Type consistency:** `align_boundary(words, sec, direction, window=3.0, min_gap=0.5)` konsisten antara Task 5 test & impl; `render_tracked` param `head_bias/zoom_*` konsisten Task 6; `run_whisper(..., initial_prompt="")` konsisten Task 4; `whisper_compute_type(device)` Task 3.
4. **Catatan khusus:** `test_settings_defaults` mengubah asersi model default (Task 3) — jangan lupa; `.env` user berisi `WHISPER_MODEL=medium` — env user menimpa default config (pydantic-settings). **PENTING:** `.env` user harus di-update manual ke `large-v3-turbo` + hapus `WHISPER_MODEL` atau set `WHISPER_MODEL=large-v3-turbo`, kalau tidak default config tidak terpakai (env lebih tinggi prioritasnya). Tambahkan ke Task 9 Step 4.
