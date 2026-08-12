import type { Job } from "../types";
import { fmtDate, fmtDuration, STAGES, statusMeta } from "../lib/stages";

interface Props {
  jobs: Job[];
  activeJob: string | null;
  onOpen: (id: string) => void;
  onDelete: (job: Job) => void;
}

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
  const stageIdx = STAGES.findIndex((s) => s.key === job.status);
  const progress = stageIdx >= 0 ? ((stageIdx + 1) / STAGES.length) * 100 : job.status === "done" ? 100 : 0;

  return (
    <div
      className={`glass card-hover animate-fadeUp cursor-pointer p-4 sm:p-5 ${active ? "border-accent/50" : ""}`}
      style={{ animationDelay: `${index * 50}ms` }}
      onClick={onOpen}
    >
      <div className="flex items-start gap-4">
        <div className={`relative mt-1 h-2.5 w-2.5 shrink-0 rounded-full ${meta.dot} ${job.running ? "animate-pulseGlow" : ""}`}>
          {job.running && (
            <span className={`absolute inset-0 animate-ping rounded-full ${meta.dot} opacity-40`} />
          )}
        </div>
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
          <div className="mt-3">
            <div className="flex items-center gap-2">
              <div className="h-1 flex-1 overflow-hidden rounded-full bg-raise">
                <div
                  className={`h-full rounded-full transition-all duration-700 ${
                    job.status === "failed" || job.status === "killed"
                      ? "bg-red-500/70"
                      : job.running
                      ? "animated-stripes animate-barStripes bg-gradient-to-r from-accent to-neon"
                      : "bg-gradient-to-r from-emerald-500 to-emerald-400"
                  }`}
                  style={{ width: `${progress}%` }}
                />
              </div>
              <span className={`chip border ${meta.color}`}>{meta.label}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
