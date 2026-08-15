import { useCallback, useEffect, useRef, useState } from "react";
import type { CaptionStyle, Job, Segment } from "../types";
import { getJobCaptionStyle, getReburnStatus, getSegments, killJob, markSegment, rejectSegment, reburnCaptions, retryJob, saveJobCaptionStyle, streamLog } from "../lib/api";
import { formatCopyText } from "../lib/clipboard";
import { fmtDuration, STAGES, STATUS_TO_STAGE, statusMeta, renderStageIcon } from "../lib/stages";
import { useConfirm } from "./ConfirmDialog";
import { SegmentCard } from "./SegmentCard";
import { defaultStyle } from "../lib/captionDefaults";
import { lazy, Suspense } from "react";
const StyleEditor = lazy(() => import("./StyleEditor").then((m) => ({ default: m.StyleEditor })));

interface Props {
  job: Job;
  onBack: () => void;
  onRefresh: () => void;
  onRejected: (id: number) => void;
  onDelete: (job: Job) => void;
  videoRes?: number;
}

type SegFilter = "all" | "pending" | "reviewed" | "posted";

const FILTERS: { key: SegFilter; label: string }[] = [
  { key: "all", label: "Semua" },
  { key: "pending", label: "Belum review" },
  { key: "reviewed", label: "Reviewed" },
  { key: "posted", label: "Posted" },
];

export function JobDetail({ job, onBack, onRefresh, onRejected, onDelete, videoRes }: Props) {
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [logs, setLogs] = useState<string[]>([]);
  const [segments, setSegments] = useState<Segment[]>([]);
  const [loadingSegs, setLoadingSegs] = useState(true);
  const [filter, setFilter] = useState<SegFilter>("all");
  const [player, setPlayer] = useState<{ seg: Segment; index: number } | null>(null);
  const [progress, setProgress] = useState<{ stage: string; pct: number; detail: string } | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [styleOpen, setStyleOpen] = useState(false);
  const [style, setStyle] = useState<CaptionStyle | null>(null);
  const [reburning, setReburning] = useState(false);
  const [reburnDone, setReburnDone] = useState(0);
  const [reburnTotal, setReburnTotal] = useState(0);
  const logBox = useRef<HTMLDivElement>(null);
  const reburnPollRef = useRef<number | null>(null);
  const [atBottom, setAtBottom] = useState(true);

  // B10: cleanup reburn polling on unmount
  useEffect(() => () => {
    if (reburnPollRef.current) window.clearInterval(reburnPollRef.current);
  }, []);

  const onLogScroll = () => {
    const el = logBox.current;
    if (!el) return;
    setAtBottom(el.scrollHeight - el.scrollTop - el.clientHeight < 40);
  };

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 2400);
  }, []);

  useEffect(() => {
    setLogs([]);
    setSegments([]);
    setProgress(null);
    setLoadingSegs(true);
    getSegments(job.id).then((s) => setSegments(s)).catch(() => {}).finally(() => setLoadingSegs(false));

    // SSE bisa putus diam-diam (network blip, server sibuk) — wajib auto-reconnect,
    // kalau nggak progress/log stuck sampai di-refresh manual.
    let es: EventSource | null = null;
    let closed = false;
    let retry: number | null = null;
    let since = 0; // cursor baris; reconnect lanjut dari sini (tidak duplikat)

    const connect = () => {
      const logBuffer: string[] = [];
      let flushTimer: number | null = null;
      let replaying = true; // skip progress selama replay buffer (hard refresh)
      const flushLogs = () => {
        if (logBuffer.length > 0) {
          const batch = logBuffer.splice(0);
          setLogs((p) => [...p, ...batch]);
        }
        flushTimer = null;
      };
      const clearFlush = () => {
        if (flushTimer) {
          window.clearTimeout(flushTimer);
          flushTimer = null;
        }
        flushLogs(); // flush batch tersisa biar gak hilang
      };
      es = streamLog(job.id, (line) => {
        since += 1;
        logBuffer.push(line);
        if (!flushTimer) flushTimer = window.setTimeout(flushLogs, 100);
        // Fix glitch: baris progress LAMA dari replay (hard refresh, since=0)
        // bikin bar menari download→transcribe→…→reframe. Baris LIVE dimulai
        // setelah event replay-done dari server.
        if (replaying) return;
        const p = parseProgress(line);
        if (p) setProgress(p);
      }, () => {
        // "done" bisa datang dari replay job yang kelar — atau server restart
        // di tengah job. Kalau job masih running, sambung ulang dari awal.
        getSegments(job.id).then(setSegments).catch(() => {});
        onRefresh();
        if (job.running) {
          clearFlush();
          since = 0;
          es = null;
          connect();
          return;
        }
        closed = true;
        clearFlush();
      }, since, () => {
        replaying = false;
      });
      es.onerror = () => {
        es?.close();
        es = null;
        clearFlush();
        if (!closed && !job.running) return; // job kelar, stop reconnect
        if (!closed) {
          retry = window.setTimeout(connect, 2500);
        }
      };
    };
    connect();

    const onVis = () => {
      if (!document.hidden && !closed && !es) {
        retry = window.setTimeout(connect, 500);
      }
    };
    document.addEventListener("visibilitychange", onVis);

    return () => {
      closed = true;
      es?.close();
      if (retry) window.clearTimeout(retry);
      document.removeEventListener("visibilitychange", onVis);
    };
  }, [job.id, onRefresh]);

  useEffect(() => {
    // Reset progress kalau stage berubah (job.status dari poll) — bar jadi
    // indeterminate dengan label stage baru sampai data % masuk.
    // Fix bug: download selesai → transcribe, bar nempel 92% download.
    setProgress((p) => (p && p.stage !== job.status ? null : p));
  }, [job.status]);

  useEffect(() => {
    // Auto-scroll cuma di dalam box log — JANGAN scroll page
    if (atBottom && logBox.current) {
      logBox.current.scrollTop = logBox.current.scrollHeight;
    }
  }, [logs, atBottom]);

  // ── Keyboard review (B) ─────────────────────────────────────────
  useEffect(() => {
    if (!player) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") { setPlayer(null); return; }
      if (e.key === "ArrowRight") movePlayer(1);
      if (e.key === "ArrowLeft") movePlayer(-1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [player, segments, filter]);

  const movePlayer = (delta: number) => {
    if (!player) return;
    const list = filtered(segments, filter);
    const cur = list.findIndex((s) => s.id === player.seg.id);
    const next = list[cur + delta];
    if (next) setPlayer({ seg: next, index: cur + delta });
    else showToast(delta > 0 ? "Sudah klip terakhir" : "Sudah klip pertama");
  };

  const meta = statusMeta(job.status);

  const openStyleModal = async () => {
    try {
      const s = await getJobCaptionStyle(job.id);
      setStyle(s);
    } catch {
      setStyle(defaultStyle());
    }
    setStyleOpen(true);
  };

  const handleApplyStyle = async () => {
    if (!style) return;
    setReburning(true);
    setReburnDone(0);
    setReburnTotal(segments.length);
    // #20: reburn NON-blocking (backend return cepat). Poll status + progres
    // per klip (caption_url ke-set cuma kalau file final BENERAN ada).
    const poll = () => window.setInterval(async () => {
      try {
        const [s, st] = await Promise.all([getSegments(job.id), getReburnStatus(job.id)]);
        setReburnTotal(s.length);
        setReburnDone(s.filter((x) => x.caption_url).length);
        if (st.status === "done" || st.status === "killed" || st.status === "skipped" || st.status === "failed") {
          if (reburnPollRef.current) window.clearInterval(reburnPollRef.current);
          reburnPollRef.current = null;
          setReburning(false);
          setStyleOpen(false);
          setSegments(s);
          showToast(st.status === "done" ? "Subtitle di-re-burn dengan gaya baru"
            : st.status === "skipped" ? "Subtitle nonaktif — tidak ada yang di-burn"
            : "Reburn dihentikan");
        }
      } catch { /* ignore */ }
    }, 2000);
    try {
      await saveJobCaptionStyle(job.id, style);
      await reburnCaptions(job.id);
      reburnPollRef.current = poll();
    } catch {
      showToast("Gagal re-burn subtitle");
      setReburning(false);
      setStyleOpen(false);
    }
  };

  const handleKill = async () => {
    if (!(await confirm("Hentikan job ini? Proses yang sedang berjalan akan dimatikan."))) return;
    try { await killJob(job.id); showToast("Job dihentikan"); } catch { /* ignore */ }
    onRefresh();
  };

  const handleRetry = async () => {
    if (!(await confirm("Proses ulang pipeline? Stage yang sudah selesai akan di-skip; file yang kurang di-repair."))) return;
    try { await retryJob(job.id); showToast("Job dilanjutkan"); } catch { /* ignore */ }
    onRefresh();
  };

  const handleReject = async (seg: Segment) => {
    if (!(await confirm(`Buang klip "${seg.product_mentioned || seg.topic || "tanpa label"}"? File akan dihapus.`))) return;
    try {
      await rejectSegment(seg.id);
      setSegments((prev) => prev.filter((s) => s.id !== seg.id));
      onRejected(seg.id);
      showToast("Klip dibuang + file dihapus");
    } catch { /* ignore */ }
  };

  const toggle = async (seg: Segment, field: "reviewed" | "posted") => {
    try {
      await markSegment(seg.id, field);
      setSegments((prev) => prev.map((x) => (x.id === seg.id ? { ...x, [field]: x[field] ? 0 : 1 } : x)));
      showToast(field === "reviewed" ? (seg.reviewed ? "Batal review" : "Tandai reviewed") : seg.posted ? "Batal posted" : "Tandai posted");
    } catch { /* ignore */ }
  };

  const shown = filtered(segments, filter);
  // Log cuma ditampilkan saat job belum selesai — kalau done, hilang & segmen full width
  const showLog = job.status !== "done";

  return (
    <div className="space-y-5">
      <div className="flex items-center justify-between gap-3">
        <button className="btn-ghost flex items-center gap-1 px-3 py-1.5 text-xs" onClick={onBack}>
          <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            <path strokeLinecap="round" strokeLinejoin="round" d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          <span>Semua episode</span>
        </button>
        <div className="flex gap-2">
          {job.status === "done" && (
            <button className="btn-ghost px-3 py-1.5 text-xs" onClick={openStyleModal} title="Ubah gaya subtitle episode ini">
              Gaya subtitle
            </button>
          )}
          {job.status === "done" && (
            <button
              className="btn-ghost px-3 py-1.5 text-xs"
              onClick={handleRetry}
              title="Jalankan ulang pipeline — stage selesai di-skip, work item yang ketinggalan (mis. caption_text) di-repair"
            >
              Proses ulang
            </button>
          )}
          {job.running && (
            <button className="btn-ghost border-red-500/40 px-3 py-1.5 text-xs text-red-300 hover:border-red-400" onClick={handleKill}>Hentikan</button>
          )}
          {job.status !== "done" && !job.running && (
            <button className="btn-ghost px-3 py-1.5 text-xs" onClick={handleRetry}>Lanjutkan</button>
          )}
          <button
            className="btn-ghost px-3 py-1.5 text-xs text-slate-500 hover:border-red-500/50 hover:text-red-400"
            onClick={() => onDelete(job)}
          >
            Hapus episode
          </button>
        </div>
      </div>

      <div className="glass animate-fadeUp p-4 sm:p-4.5">
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
          <span className={`chip border ${meta.color} gap-1.5`}>
            {renderStageIcon(job.status, "h-3.5 w-3.5 shrink-0")}
            {meta.label}
          </span>
          <span className="font-mono text-xs text-slate-500">{job.id}</span>
          {job.duration_sec ? <span className="text-xs text-slate-500">{fmtDuration(job.duration_sec)} · episode asli</span> : null}
        </div>
        <div className="mt-3 flex items-start gap-4">
          <img
            src={`https://i.ytimg.com/vi/${job.id}/mqdefault.jpg`}
            alt=""
            loading="lazy"
            className="h-12 w-20 shrink-0 rounded-xl object-cover"
            onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
          />
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-xl font-bold leading-snug text-slate-100">{job.title || "Episode tanpa judul"}</h1>
            {job.channel && <p className="mt-1 text-sm text-slate-400">{job.channel}</p>}
          </div>
        </div>
        {job.status === "failed" && job.error_message && (
          <p className="mt-3 rounded-lg border border-red-500/30 bg-red-500/10 px-3 py-2 text-xs text-red-300">{job.error_message}</p>
        )}
        {job.notice && (
          <p className="mt-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-300">{job.notice}</p>
        )}

        {/* ── Progress bar live ── */}
        {job.running && (
          <div className="mt-4">
            <div className="mb-1.5 flex items-center justify-between text-xs">
              <span className="flex items-center gap-1.5 font-semibold text-cyan-300">
                {renderStageIcon(progress ? progress.stage : job.status, "h-3.5 w-3.5 animate-pulse text-cyan-400 shrink-0")}
                {progress ? `${stageLabel(progress.stage)} · ${progress.pct.toFixed(0)}%` : `${stageLabel(job.status)}…`}
              </span>
              <span className="font-mono text-slate-500">
                {progress?.detail ?? (progress ? `${progress.pct.toFixed(0)}%` : "")}
              </span>
            </div>
            {progress ? (
              <div className="flex h-3.5 gap-[3px]">
                {Array.from({ length: 20 }).map((_, i) => {
                  const filled = (i / 20) * 100 <= progress.pct;
                  return (
                    <div
                      key={i}
                      className={`flex-1 rounded-[3px] transition-all duration-300 ${
                        filled
                          ? "bg-gradient-to-b from-accent via-teal-400 to-neon shadow-[0_0_8px_rgba(34,211,238,0.45)]"
                          : "bg-edge/50"
                      }`}
                      style={filled && i === Math.floor(progress.pct / 5) ? { boxShadow: "0 0 12px rgba(34,211,238,0.8)" } : undefined}
                    />
                  );
                })}
              </div>
            ) : (
              <div className="flex h-3.5 gap-[3px]">
                {Array.from({ length: 20 }).map((_, i) => (
                  <div
                    key={i}
                    className="flex-1 animate-pulseGlow rounded-[3px] bg-gradient-to-b from-accent/70 to-neon/70"
                    style={{ animationDelay: `${i * 90}ms`, opacity: 0.25 + (i % 5) * 0.15 }}
                  />
                ))}
              </div>
            )}
          </div>
        )}

        {!player && <PipelineRail stages={job.stages ?? []} jobStatus={job.status} videoRes={videoRes} />}
      </div>

        <div className={`grid gap-5 ${showLog ? "lg:grid-cols-3" : ""}`}>
          <div className={showLog ? "lg:col-span-2" : ""}>
          <div className="mb-3 flex items-center justify-between gap-2">
            <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-slate-400">
              Klip siap review <span className="text-accent">· {segments.length}</span>
            </h2>
            <div className="flex gap-1">
              {FILTERS.map((f) => (
                <button
                  key={f.key}
                  onClick={() => setFilter(f.key)}
                  className={`rounded-lg px-2.5 py-1 text-[11px] font-semibold transition-all ${
                    filter === f.key
                      ? "bg-accent/20 text-accent"
                      : "text-slate-500 hover:bg-raise hover:text-slate-300"
                  }`}
                >
                  {f.label}
                  {f.key !== "all" && (
                    <span className="ml-1 opacity-60">
                      {segments.filter((s) => f.key === "reviewed" ? s.reviewed : f.key === "posted" ? s.posted : !s.reviewed && !s.posted).length}
                    </span>
                  )}
                </button>
              ))}
            </div>
          </div>

          {loadingSegs ? (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {[0, 1, 2, 3].map((i) => (
                <div key={i} className="glass animate-pulse overflow-hidden">
                  <div className="aspect-[9/12] bg-raise" />
                  <div className="space-y-2 p-3.5">
                    <div className="h-3 w-3/4 rounded bg-raise" />
                    <div className="h-3 w-1/2 rounded bg-raise" />
                  </div>
                </div>
              ))}
            </div>
          ) : segments.length === 0 ? (
            <div className="glass animate-fadeUp p-8 text-center text-sm text-slate-500">
              {job.running ? "Pipeline sedang bekerja — klip akan muncul di sini…" : "Belum ada klip untuk episode ini."}
            </div>
          ) : shown.length === 0 ? (
            <div className="glass animate-fadeUp p-8 text-center text-sm text-slate-500">
              Tidak ada klip di filter ini.
            </div>
          ) : (
            <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
              {shown.map((s, i) => (
                <SegmentCard
                  key={s.id}
                  seg={s}
                  index={i}
                  onPlay={() => setPlayer({ seg: s, index: i })}
                  onReject={() => handleReject(s)}
                  onToggle={(field) => toggle(s, field)}
                  onToast={showToast}
                />
              ))}
            </div>
          )}
        </div>

        {showLog && (
          <div className="space-y-4">
            <h2 className="font-display text-sm font-semibold uppercase tracking-wider text-slate-400">Log pipeline</h2>
            <div className="glass relative overflow-hidden">
              <div className="pointer-events-none absolute inset-x-0 top-0 z-10 h-6 bg-gradient-to-b from-panel to-transparent" />
              <div ref={logBox} onScroll={onLogScroll} className="font-mono h-[460px] overflow-y-auto p-4 text-[11px] leading-relaxed">
{logs.length === 0 ? (
                  <span className="text-slate-600">— menunggu log —</span>
                ) : (
                  logs.map((line, i) => (
                    <div key={i} className={lineColor(line)}>
                      {line.trimStart()}
                    </div>
                  ))
                )}
              </div>
              <div className="pointer-events-none absolute inset-x-0 bottom-0 z-10 h-6 bg-gradient-to-t from-panel to-transparent" />
            </div>
          </div>
        )}
      </div>

      {player && (
        <PlayerModal
          key={player.seg.id}
          seg={player.seg}
          index={player.index}
          total={shown.length}
          onClose={() => setPlayer(null)}
          onPrev={() => movePlayer(-1)}
          onNext={() => movePlayer(1)}
          onToggle={(field) => toggle(player.seg, field)}
          onReject={() => handleReject(player.seg)}
          onToast={showToast}
        />
      )}

      {styleOpen && style && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/85 p-4 backdrop-blur-sm" onClick={() => !reburning && setStyleOpen(false)}>
          <div className="animate-fadeUp max-h-[88vh] w-full max-w-5xl overflow-y-auto rounded-2xl border border-edge bg-panel p-6" onClick={(e) => e.stopPropagation()}>
            <div className="mb-4 flex items-center justify-between">
              <h3 className="font-display text-lg font-bold text-slate-100">Gaya subtitle — episode ini</h3>
              <button className="btn-ghost flex h-8 w-8 items-center justify-center rounded-full p-0 text-xs" onClick={() => setStyleOpen(false)}>
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>
            <Suspense fallback={<div className="py-8 text-center text-xs text-slate-500">Muat editor gaya…</div>}>
              <StyleEditor value={style} onChange={setStyle} previewSide="right" />
            </Suspense>
            <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-edge pt-4">
              <button
                className="btn-primary px-6 py-2.5 text-sm disabled:opacity-50"
                onClick={handleApplyStyle}
                disabled={reburning}
              >
                {reburning ? (
                  <span className="flex items-center gap-2">
                    <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                      <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                    </svg>
                    Re-burn subtitle… {reburnDone}/{reburnTotal} klip
                  </span>
                ) : (
                  "Terapkan & re-burn semua klip"
                )}
              </button>
              <p className="text-xs text-slate-500">
                Mengubah gaya episode ini tanpa menyentuh gaya default. Re-burn ±3-5 menit
                (10 klip paralel, ffmpeg ulang semua klip).
              </p>
            </div>
          </div>
        </div>
      )}

      {toast && (
        <div className="fixed bottom-6 left-1/2 z-[60] -translate-x-1/2 animate-fadeUp">
          <div className="rounded-full border border-edge bg-raise/95 px-4 py-2 text-xs text-slate-200 shadow-2xl backdrop-blur">
            {toast}
          </div>
        </div>
      )}
      {confirmDialog}
    </div>
  );
}

function filtered(segs: Segment[], f: SegFilter): Segment[] {
  if (f === "reviewed") return segs.filter((s) => s.reviewed);
  if (f === "posted") return segs.filter((s) => s.posted);
  if (f === "pending") return segs.filter((s) => !s.reviewed && !s.posted);
  return segs;
}

function stageLabel(key: string): string {
  // #16: status backend ("downloading") → key stage ("ingest") → label
  const k = STATUS_TO_STAGE[key] ?? key;
  return STAGES.find((s) => s.key === k)?.label ?? key;
}

function PipelineRail({ stages, jobStatus, videoRes }: { stages: Job["stages"]; jobStatus: string; videoRes?: number }) {
  const byStage: Record<string, string> = {};
  for (const s of stages ?? []) byStage[s.stage] = s.status;

  return (
    <div className="mt-3.5 grid grid-cols-2 gap-2 sm:grid-cols-3 lg:grid-cols-6">
      {STAGES.map((s, i) => {
        const st = byStage[s.key] ?? (i === 0 && (jobStatus === "pending" || jobStatus === "downloading") ? "running" : "pending");
        const isActive = st === "running";
        const isDone = st === "done";
        const isFailed = st === "failed";
        const run = (stages ?? []).find((r) => r.stage === s.key);
        return (
          <div
            key={s.key}
            className={`relative rounded-xl border px-3 py-2 transition-all duration-200 ${
              isActive
                ? "border-accent/60 bg-accent/10 shadow-[0_0_14px_rgba(20,184,166,0.15)]"
                : isDone
                ? "border-emerald-500/30 bg-emerald-500/5"
                : isFailed
                ? "border-red-500/40 bg-red-500/5"
                : "border-edge/60 bg-raise/40"
            }`}
          >
            <div className="flex items-center justify-between gap-1.5">
              <div className={`flex items-center gap-1.5 font-display text-xs font-semibold truncate ${isActive ? "text-white" : isDone ? "text-emerald-300" : isFailed ? "text-red-300" : "text-slate-400"}`}>
                {renderStageIcon(s.key, `h-3.5 w-3.5 shrink-0 ${isActive ? "text-accent animate-pulse" : isDone ? "text-emerald-400" : isFailed ? "text-red-400" : "text-slate-500"}`)}
                <span className="truncate">{s.label}</span>
              </div>
              <div className="flex items-center shrink-0">
                {isActive && (
                  <svg className="h-3 w-3 animate-spin text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
                  </svg>
                )}
                {isDone && <svg className="h-3.5 w-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" /></svg>}
                {isFailed && <svg className="h-3.5 w-3.5 text-red-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={3}><path strokeLinecap="round" d="M6 18L18 6M6 6l12 12" /></svg>}
                {!isActive && !isDone && !isFailed && (
                  <span className="font-mono text-[10px] text-slate-500">{String(i + 1).padStart(2, "0")}</span>
                )}
              </div>
            </div>
            <div className="mt-1 flex items-center justify-between text-[10px] text-slate-500">
              <span className="truncate">{s.key === "ingest" && videoRes ? `${videoRes}p` : s.hint}</span>
              {isDone && run?.started_at && run?.finished_at && (
                <span className="text-emerald-400/80 font-mono font-medium ml-1 shrink-0">{fmtStageDur(run.started_at, run.finished_at)}</span>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function fmtStageDur(start: string, end: string): string {
  const s = new Date(start + "Z").getTime();
  const e = new Date(end + "Z").getTime();
  if (isNaN(s) || isNaN(e)) return "";
  const sec = Math.round((e - s) / 1000);
  if (sec < 60) return `${sec}s`;
  return `${Math.floor(sec / 60)}m ${sec % 60}s`;
}

function PlayerModal({ seg, index, total, onClose, onPrev, onNext, onToggle, onReject, onToast }: {
  seg: Segment;
  index: number;
  total: number;
  onClose: () => void;
  onPrev: () => void;
  onNext: () => void;
  onToggle: (field: "reviewed" | "posted") => void;
  onReject: () => void;
  onToast?: (msg: string) => void;
}) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [copiedCaption, setCopiedCaption] = useState(false);

  const spaceToggle = (e: React.KeyboardEvent) => {
    if (e.key === " " && videoRef.current) {
      e.preventDefault();
      const v = videoRef.current;
      if (v.paused) v.play(); else v.pause();
    }
  };

  const handleCopyCaption = async () => {
    const textToCopy = formatCopyText(seg);
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedCaption(true);
      onToast?.("Caption tersalin ke clipboard");
      setTimeout(() => setCopiedCaption(false), 1600);
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-3 bg-black/85 p-4 backdrop-blur-sm" onClick={onClose}>
      <div className="animate-fadeUp relative flex flex-col items-center" onClick={(e) => e.stopPropagation()} onKeyDown={spaceToggle} tabIndex={0} autoFocus>
        <div className="relative">
          <video
            ref={videoRef}
            src={seg.preview_url ?? undefined}
            controls
            autoPlay
            className="max-h-[52vh] w-auto rounded-lg border border-edge/50 bg-black shadow-2xl sm:max-h-[76vh]"
            style={{ aspectRatio: "9/16" }}
          />
          <div className="absolute left-2.5 top-2.5 flex flex-wrap items-center gap-1.5 max-w-[65%]">
            {seg.product_mentioned && (
              <span className="chip max-w-full truncate border border-gold/40 bg-black/60 px-2 py-0.5 text-[10px] text-gold backdrop-blur inline-flex items-center gap-1">
                <svg className="h-2.5 w-2.5 text-gold shrink-0" fill="currentColor" viewBox="0 0 24 24">
                  <path d="M12 2l2.4 7.2H22l-6 4.4 2.3 7.1-6.3-4.5-6.3 4.5L8 13.6 2 9.2h7.6z" />
                </svg>
                <span>{seg.product_mentioned}</span>
              </span>
            )}
          </div>
          <div className="absolute right-2.5 top-2.5 flex gap-1.5">
            <button onClick={onPrev} disabled={index === 0} className="btn-ghost flex h-8 w-8 items-center justify-center rounded-full p-0 text-xs disabled:opacity-30" title="Klip sebelumnya">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M15 19l-7-7 7-7" />
              </svg>
            </button>
            <button onClick={onNext} disabled={index >= total - 1} className="btn-ghost flex h-8 w-8 items-center justify-center rounded-full p-0 text-xs disabled:opacity-30" title="Klip berikutnya">
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
              </svg>
            </button>
            <button onClick={onClose} className="btn-ghost flex h-8 w-8 items-center justify-center rounded-full p-0 text-xs" title="Tutup (Esc)">
              <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          </div>
        </div>
        <div className="mt-3 flex w-full flex-wrap items-center gap-1.5 rounded-xl border border-edge/60 bg-raise/80 px-2.5 py-2 backdrop-blur">
          <span className="mr-1.5 font-mono text-[11px] text-slate-500">{index + 1}/{total}</span>
          <button
            onClick={() => onToggle("reviewed")}
            role="switch"
            aria-checked={!!seg.reviewed}
            className={`flex-1 flex items-center justify-center gap-1 rounded-lg border px-2 py-1.5 text-[11px] font-semibold transition-all active:scale-[0.97] ${
              seg.reviewed
                ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                : "border-edge bg-raise/50 text-slate-400 hover:border-emerald-500/40 hover:text-emerald-300"
            }`}
          >
            {seg.reviewed && (
              <svg className="h-3.5 w-3.5 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
              </svg>
            )}
            <span>{seg.reviewed ? "Reviewed" : "Review"}</span>
          </button>
          <button
            onClick={() => onToggle("posted")}
            role="switch"
            aria-checked={!!seg.posted}
            className={`flex-1 flex items-center justify-center gap-1 rounded-lg border px-2 py-1.5 text-[11px] font-semibold transition-all active:scale-[0.97] ${
              seg.posted
                ? "border-gold/60 bg-gold/15 text-gold"
                : "border-edge bg-raise/50 text-slate-400 hover:border-gold/50 hover:text-gold"
            }`}
            title="Posting ke TikTok dengan keranjang kuning"
          >
            <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
            </svg>
            <span>{seg.posted ? "Posted" : "Keranjang"}</span>
          </button>
          {(seg.affiliate_caption || seg.caption_text) && (
            <button
              onClick={handleCopyCaption}
              className={`flex h-8 w-8 items-center justify-center rounded-lg border text-[11px] font-semibold transition-all active:scale-[0.97] ${
                copiedCaption
                  ? "border-emerald-500/50 bg-emerald-500/15 text-emerald-300"
                  : "border-amber-500/40 bg-amber-500/15 text-amber-300 hover:bg-amber-500/25"
              }`}
              title="Salin caption & hashtag"
            >
              {copiedCaption ? (
                <svg className="h-4 w-4 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="h-4 w-4 text-amber-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              )}
            </button>
          )}
          <button onClick={onReject} className="rounded-lg border border-edge bg-raise/50 px-2 py-1.5 text-[11px] font-semibold text-slate-500 transition-all hover:border-red-500/50 hover:text-red-400 active:scale-[0.97]">Buang</button>
          {seg.preview_url && (
            <a
              href={seg.preview_url}
              download
              className="flex items-center gap-1.5 rounded-lg border border-edge bg-raise/50 px-2.5 py-1.5 text-[11px] font-semibold text-slate-400 transition-all hover:border-teal-400/50 hover:text-teal-300 active:scale-[0.97]"
              title="Download klip final (vertikal + subtitle)"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
              <span>Download</span>
            </a>
          )}
        </div>
        {seg.virality_reason && (
          <p className="mt-1 text-center text-[10px] italic text-amber-300/80 flex items-center justify-center gap-1">
            <svg className="h-3 w-3 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
            <span>{seg.virality_reason}</span>
          </p>
        )}
        <p className="mt-1 text-[10px] text-slate-600">
          Gunakan tombol panah untuk ganti klip · Spasi play/pause · Esc tutup
        </p>
      </div>
    </div>
  );
}

function parseProgress(line: string): { stage: string; pct: number; detail: string } | null {
  // whisper: "    Transcribing |####----|  45.2%  1234s/3200s"
  const m = line.match(/Transcribing\s+\|.{1,40}\|\s+(\d+(?:\.\d+)?)%\s+(\d+)s\/(\d+)s/);
  if (m) return { stage: "transcribe", pct: Number(m[1]), detail: `${m[2]}s / ${m[3]}s` };
  // yt-dlp: "[download]  45.2% of  276.00MiB at  5.20MiB/s"
  const d = line.match(/\[download\]\s+(\d+(?:\.\d+)?)%\s+of\s+~?([\d.]+)(MiB|GiB)/);
  if (d) return { stage: "download", pct: Number(d[1]), detail: `${d[2]} ${d[3]}` };
  // stage per-item: "analyze 2/4 chunks", "clip 5/10", "reframe 3/10", "caption 7/10"
  const s = line.match(/(analyze|clip|reframe|caption)\s+(\d+)\/(\d+)/);
  if (s) return { stage: s[1], pct: (Number(s[2]) / Number(s[3])) * 100, detail: `${s[2]}/${s[3]}` };
  // sub-proses reframe: "reframe track 3/8 43%" / "reframe render 7/8 70%"
  const t = line.match(/reframe\s+(track|render)\s+(\d+)\/(\d+)\s+(\d+(?:\.\d+)?)%/);
  if (t) return { stage: "reframe", pct: Number(t[4]), detail: `${t[2]}/${t[3]} · ${t[1]}` };
  return null;
}

function lineColor(line: string): string {
  const t = line.trimStart();
  if (t.includes("FAILED") || t.includes("Error") || t.includes("error:")) return "text-red-400";
  if (t.includes("killed")) return "text-orange-400";
  if (t.includes("done")) return "text-emerald-400";
  if (t.includes("starting")) return "text-cyan-300";
  if (t.startsWith("[download]")) return "text-cyan-300/80";
  if (t.startsWith("[youtube]") || t.startsWith("[info]") || t.startsWith("[MergeMux]") || t.startsWith("[ExtractAudio]")) return "text-slate-500";
  if (t.includes("cleaned")) return "text-slate-500";
  if (/Transcribing|analyze \d|clip \d|reframe \d|caption \d/.test(t)) return "text-emerald-400/80";
  return "text-slate-400";
}
