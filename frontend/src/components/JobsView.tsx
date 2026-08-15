import type { Job } from "../types";
import { fmtDate, fmtDuration, STAGES, statusMeta, renderStageIcon } from "../lib/stages";

interface Props {
  jobs: Job[];
  activeJob: string | null;
  onOpen: (id: string) => void;
  onDelete: (job: Job) => void;
}

// status backend ("downloading") → key stage ("ingest"). Tanpa map ini
// findIndex selalu -1 → bar 0% tak terlihat selama job jalan.
const STATUS_TO_STAGE: Record<string, string> = {
  downloading: "ingest",
  transcribing: "transcribe",
  analyzing: "analyze",
  clipping: "clip",
  reframing: "reframe",
  captioning: "caption",
};

export function JobsView({ jobs, activeJob, onOpen, onDelete }: Props) {
  const running = jobs.filter((j) => j.running).length;
  const done = jobs.filter((j) => j.status === "done").length;
  const failed = jobs.filter((j) => j.status === "failed").length;

  const stats = [
    { label: "Total episode", value: jobs.length, accent: "text-slate-200" },
    { label: "Selesai", value: done, accent: "text-emerald-400" },
    { label: "Sedang jalan", value: running, accent: "text-cyan-400", pulse: running > 0 },
    { label: "Gagal", value: failed, accent: "text-red-400" },
  ];

  return (
    <div className="space-y-6">
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {stats.map((s, i) => (
          <div
            key={s.label}
            className="glass animate-fadeUp px-4 py-3"
            style={{ animationDelay: `${i * 60}ms` }}
          >
            <div className={`font-display text-2xl font-bold ${s.accent}`}>
              {s.pulse && <span className="inline-block h-2 w-2 animate-pulseGlow rounded-full bg-cyan-400 align-middle" />}{" "}
              {s.value}
            </div>
            <div className="mt-0.5 text-[11px] uppercase tracking-wider text-slate-500">{s.label}</div>
          </div>
        ))}
      </div>

      {jobs.length === 0 ? (
        <div className="glass animate-fadeUp flex flex-col items-center gap-3 py-16 text-center">
          <div className="relative h-16 w-16">
            <div className="absolute inset-0 animate-spinSlow rounded-full border border-dashed border-accent/40" />
            <svg className="absolute inset-0 m-auto h-8 w-8 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={1.5}>
              <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
            </svg>
          </div>
          <p className="font-display text-lg font-semibold text-slate-300">Studio kosong</p>
          <p className="max-w-sm text-sm text-slate-500">
            Tempel link podcast di atas. Klip produk yang siap direview akan muncul di sini.
          </p>
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map((j, i) => (
            <JobCard key={j.id} job={j} index={i} active={j.id === activeJob} onOpen={() => onOpen(j.id)} onDelete={() => onDelete(j)} />
          ))}
        </div>
      )}
    </div>
  );
}

function JobCard({ job, index, active, onOpen, onDelete }: { job: Job; index: number; active: boolean; onOpen: () => void; onDelete: () => void }) {
  const meta = statusMeta(job.status);
  const stageIdx = STAGES.findIndex((s) => s.key === (STATUS_TO_STAGE[job.status] ?? job.status));

  return (
    <div
      className={`glass card-hover animate-fadeUp cursor-pointer p-4 sm:p-5 ${active ? "border-accent/50" : ""}`}
      style={{ animationDelay: `${index * 50}ms` }}
      onClick={onOpen}
    >
      <div className="flex items-start gap-4">
        <img
          src={`https://i.ytimg.com/vi/${job.id}/mqdefault.jpg`}
          alt=""
          loading="lazy"
          className="h-20 w-32 shrink-0 rounded-xl object-cover"
          onError={(e) => { (e.currentTarget as HTMLImageElement).style.display = "none"; }}
        />
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="font-display truncate text-[15px] font-semibold text-slate-100">
              {job.title || `Episode ${job.id}`}
            </h3>
            {job.channel && (
              <span className="text-xs text-slate-500">· {job.channel}</span>
            )}
            <button
              className="ml-auto rounded px-1.5 py-0.5 text-[11px] text-slate-600 transition-colors hover:bg-red-900/40 hover:text-red-400"
              title="Hapus episode + semua file"
              onClick={(e) => { e.stopPropagation(); onDelete(); }}
            >
              ✕ hapus
            </button>
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-slate-500">
            <span className="font-mono">{job.id}</span>
            <span>{fmtDate(job.created_at)}</span>
            <span>{fmtDuration(job.duration_sec)}</span>
            {!!job.segment_count && (
              <span className="chip border border-accent/30 bg-accent/10 text-cyan-300">
                <svg className="h-3 w-3" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
                {job.segment_count} klip
              </span>
            )}
          </div>
          <div className="mt-3.5 space-y-1.5">
            <div className="flex items-center justify-between gap-2 text-[11px]">
              <div className="flex items-center gap-1.5 text-slate-400 font-medium">
                {job.running ? (
                  <span className="font-mono text-cyan-300 flex items-center gap-1.5">
                    <span className="h-1.5 w-1.5 rounded-full bg-cyan-400 animate-pulseGlow" />
                    Tahap {stageIdx >= 0 ? stageIdx + 1 : 1}/6 · {STAGES[stageIdx >= 0 ? stageIdx : 0]?.label}
                  </span>
                ) : job.status === "done" ? (
                  <span className="text-emerald-400 flex items-center gap-1">
                    <svg className="h-3 w-3 text-emerald-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                    </svg>
                    6/6 Selesai
                  </span>
                ) : job.status === "failed" ? (
                  <span className="text-red-400">Gagal di tahap {stageIdx >= 0 ? STAGES[stageIdx]?.label : ""}</span>
                ) : (
                  <span className="text-slate-500">Menunggu antrean</span>
                )}
              </div>
              <span className={`chip border ${meta.color} gap-1.5 py-0 px-2 text-[10px]`}>
                {renderStageIcon(job.status, "h-3 w-3 shrink-0")}
                {meta.label}
              </span>
            </div>

            {/* ── 6-Segment Pipeline Progress Rail ── */}
            <div className="flex h-2 w-full gap-1.5">
              {STAGES.map((s, i) => {
                const isPassed = job.status === "done" || (stageIdx >= 0 && i < stageIdx);
                const isCurrent = job.running && (stageIdx === i || (stageIdx < 0 && i === 0));
                const isError = (job.status === "failed" || job.status === "killed") && stageIdx === i;

                return (
                  <div
                    key={s.key}
                    title={`${s.label}: ${s.hint}`}
                    className={`relative flex-1 rounded-full transition-all duration-500 ${
                      isPassed
                        ? "bg-gradient-to-r from-teal-500 to-emerald-400 shadow-[0_0_8px_rgba(20,184,166,0.3)]"
                        : isCurrent
                        ? "bg-gradient-to-r from-accent via-cyan-400 to-neon shadow-[0_0_12px_rgba(34,211,238,0.7)] animate-pulse"
                        : isError
                        ? "bg-red-500/80 shadow-[0_0_8px_rgba(239,68,68,0.4)]"
                        : "bg-raise/80 border border-edge/40"
                    }`}
                  />
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
