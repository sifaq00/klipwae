import { lazy, Suspense, useCallback, useEffect, useState } from "react";
import { defaultStyle } from "./lib/captionDefaults";
const StyleEditor = lazy(() => import("./components/StyleEditor").then((m) => ({ default: m.StyleEditor })));
import { useConfirm } from "./components/ConfirmDialog";
import { JobsView } from "./components/JobsView";
import { JobDetail } from "./components/JobDetail";
import { UrlInput } from "./components/UrlInput";
import type { CaptionStyle, Job } from "./types";
import { createJob, deleteJob, getCaptionStyle, getJob, getSettings, listJobs, saveCaptionStyle } from "./lib/api";

export default function App() {
  const { confirm, dialog: confirmDialog } = useConfirm();
  const [jobs, setJobs] = useState<Job[]>([]);
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [activeJob, setActiveJob] = useState<Job | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [styleOpen, setStyleOpen] = useState(false);
  const [style, setStyle] = useState<CaptionStyle | null>(null);
  const [styleSaved, setStyleSaved] = useState(false);
  const [videoRes, setVideoRes] = useState<number | undefined>(undefined);

  const refresh = useCallback(() => listJobs().then(setJobs).catch(() => {}), []);

  useEffect(() => {
    getSettings().then((s) => setVideoRes(s.video_download_resolution)).catch(() => {});
  }, []);

  useEffect(() => {
    getCaptionStyle().then(setStyle).catch(() => setStyle(defaultStyle()));
  }, []);

  const handleSaveStyle = async () => {
    if (!style) return;
    try {
      await saveCaptionStyle(style);
      setStyleSaved(true);
      showToast("Gaya subtitle default tersimpan");
      setTimeout(() => setStyleSaved(false), 2000);
    } catch {
      showToast("Gagal menyimpan gaya");
    }
  };

  const showToast = useCallback((msg: string) => {
    setToast(msg);
    window.setTimeout(() => setToast((t) => (t === msg ? null : t)), 3000);
  }, []);

  useEffect(() => {
    refresh();
    const id = setInterval(refresh, 3000);
    return () => clearInterval(id);
  }, []);

  useEffect(() => {
    if (!activeJobId) {
      setActiveJob(null);
      return;
    }
    let alive = true;
    const load = () =>
      getJob(activeJobId)
        .then((j) => alive && setActiveJob(j))
        .catch(() => {});
    load();
    const id = setInterval(load, 3000);
    return () => {
      alive = false;
      clearInterval(id);
    };
  }, [activeJobId]);

  const handleSubmit = async (url: string, preset: string = "affiliate") => {
    const { job_id } = await createJob(url, preset);
    // Jangan auto-lock ke detail — user bebas scroll home sambil job jalan
    showToast(`Job ${job_id} (${preset}) dimulai — pantau dari kartu di bawah`);
    refresh();
  };

  const handleDelete = async (job: Job) => {
    if (!(await confirm(`Hapus episode "${job.title || job.id}"? Semua file (klip, transkrip, subtitle) ikut terhapus.`))) return;
    try {
      await deleteJob(job.id);
      if (activeJobId === job.id) setActiveJobId(null);
      showToast(`Episode ${job.id} dihapus`);
      refresh();
    } catch {
      showToast("Gagal menghapus episode");
    }
  };

  return (
    <div className="mx-auto max-w-6xl px-4 pb-16 pt-6 sm:pt-10">
      <header className="mb-8 flex items-center justify-between">
        <div className="flex items-center gap-3.5">
          <div className="group relative flex shrink-0 items-center justify-center transition-transform duration-200 hover:scale-105">
            <img src="/logo.png" alt="Klipwae Studio Logo" className="h-9 w-9 sm:h-10 sm:w-10 object-contain drop-shadow-[0_0_12px_rgba(0,242,254,0.4)]" />
          </div>
          <div>
            <h1 className="font-display text-xl font-bold tracking-tight">
              <span className="text-gradient">Klipwae</span> <span className="text-slate-400">Studio</span>
            </h1>
            <p className="text-[11px] text-slate-500">Podcast → klip produk → siap keranjang kuning</p>
          </div>
        </div>
        {jobs.some((j) => j.running) ? (
          <span className="chip border border-emerald-400/30 bg-emerald-400/10 text-emerald-300 shadow-sm shadow-emerald-500/10">
            <svg className="h-3.5 w-3.5 animate-spin text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
            </svg>
            Pipeline aktif
          </span>
        ) : (
          <span className="chip border border-slate-500/30 bg-slate-500/10 text-slate-400">
            <svg className="h-3.5 w-3.5 text-slate-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
            Idle
          </span>
        )}
      </header>

      {activeJob && activeJobId ? (
        <JobDetail
          job={activeJob}
          onBack={() => setActiveJobId(null)}
          onRefresh={refresh}
          onRejected={refresh}
          onDelete={handleDelete}
          videoRes={videoRes}
        />
      ) : (
        <div className="space-y-6">
          <UrlInput onSubmit={handleSubmit} />

          <div className="glass animate-fadeUp overflow-hidden">
            <button
              className="flex w-full items-center justify-between px-5 py-3.5 text-left"
              onClick={() => setStyleOpen((o) => !o)}
            >
              <span className="flex items-center gap-2 font-display text-sm font-semibold text-slate-200">
                <svg className="h-4 w-4 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 5h12M9 3v4m1 4h10m-6 4v4m3-2h3m-12-2h.01M6 15h.01" />
                </svg>
                Gaya subtitle default
                <span className="text-[11px] font-normal text-slate-500">— berlaku untuk semua episode baru</span>
              </span>
              <svg className={`h-4 w-4 text-slate-500 transition-transform ${styleOpen ? "rotate-180" : ""}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {styleOpen && style && (
              <div className="border-t border-edge px-5 py-4">
                <Suspense fallback={<div className="py-8 text-center text-xs text-slate-500">Muat editor gaya…</div>}>
                  <StyleEditor value={style} onChange={setStyle} previewSide="right" />
                </Suspense>
                <div className="mt-5 flex flex-wrap items-center gap-3 border-t border-edge pt-4">
                  <button className="btn-primary flex items-center gap-1.5 px-6 py-2.5 text-sm" onClick={handleSaveStyle}>
                    {styleSaved && (
                      <svg className="h-4 w-4 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                      </svg>
                    )}
                    <span>{styleSaved ? "Tersimpan" : "Simpan gaya default"}</span>
                  </button>
                  <p className="text-xs text-slate-500">
                    Berlaku untuk semua episode baru. Episode yang sudah selesai tidak terpengaruh —
                    ubah gayanya lewat halaman episode.
                  </p>
                </div>
              </div>
            )}
          </div>

          <JobsView jobs={jobs} activeJob={activeJobId} onOpen={setActiveJobId} onDelete={handleDelete} />
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
