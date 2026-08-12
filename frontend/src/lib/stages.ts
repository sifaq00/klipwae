export interface StageMeta {
  key: string;
  label: string;
  hint: string;
}

export const STAGES: StageMeta[] = [
  { key: "ingest", label: "Download", hint: "yt-dlp · 720p" },
  { key: "transcribe", label: "Transkrip", hint: "whisper · word-level" },
  { key: "analyze", label: "Analisis", hint: "gemini · deteksi produk" },
  { key: "clip", label: "Klip", hint: "split 30–60 dtk" },
  { key: "reframe", label: "Reframe", hint: "vertikal 9:16" },
  { key: "caption", label: "Subtitle", hint: "karaoke burn-in" },
];

export const JOB_STATUS: Record<string, { label: string; color: string; dot: string }> = {
  pending: { label: "Antre", color: "text-slate-400 bg-slate-400/10 border-slate-400/30", dot: "bg-slate-400" },
  downloading: { label: "Downloading", color: "text-cyan-300 bg-cyan-400/10 border-cyan-400/30", dot: "bg-cyan-400" },
  transcribing: { label: "Transcribing", color: "text-cyan-300 bg-cyan-400/10 border-cyan-400/30", dot: "bg-cyan-400" },
  analyzing: { label: "Analyzing", color: "text-sky-300 bg-sky-400/10 border-sky-400/30", dot: "bg-sky-400" },
  clipping: { label: "Clipping", color: "text-amber-300 bg-amber-400/10 border-amber-400/30", dot: "bg-amber-400" },
  reframing: { label: "Reframing", color: "text-teal-300 bg-teal-400/10 border-teal-400/30", dot: "bg-teal-400" },
  captioning: { label: "Captioning", color: "text-lime-300 bg-lime-400/10 border-lime-400/30", dot: "bg-lime-400" },
  done: { label: "Selesai", color: "text-emerald-300 bg-emerald-400/10 border-emerald-400/30", dot: "bg-emerald-400" },
  failed: { label: "Gagal", color: "text-red-300 bg-red-400/10 border-red-400/30", dot: "bg-red-400" },
  killed: { label: "Dihentikan", color: "text-orange-300 bg-orange-400/10 border-orange-400/30", dot: "bg-orange-400" },
};

export function statusMeta(status: string) {
  return JOB_STATUS[status] ?? { label: status, color: "text-slate-400 bg-slate-400/10 border-slate-400/30", dot: "bg-slate-400" };
}

export function fmtDuration(sec: number | null): string {
  if (!sec) return "";
  const h = Math.floor(sec / 3600);
  const m = Math.floor((sec % 3600) / 60);
  return h > 0 ? `${h}j ${m}m` : `${m} menit`;
}

export function fmtDate(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso + "Z");
  if (isNaN(d.getTime())) return iso.slice(0, 10);
  return d.toLocaleDateString("id-ID", { day: "numeric", month: "short" });
}
