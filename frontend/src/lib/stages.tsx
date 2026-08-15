import type { ReactNode } from "react";

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

export const STATUS_TO_STAGE: Record<string, string> = {
  downloading: "ingest",
  transcribing: "transcribe",
  analyzing: "analyze",
  clipping: "clip",
  reframing: "reframe",
  captioning: "caption",
};

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
  if (sec < 60) return `${Math.round(sec)} dtk`;
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

export function renderStageIcon(stageOrStatus: string, className: string = "h-3.5 w-3.5 shrink-0"): ReactNode {
  const key = STATUS_TO_STAGE[stageOrStatus] ?? stageOrStatus;
  switch (key) {
    case "ingest":
    case "download":
    case "downloading":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
        </svg>
      );
    case "transcribe":
    case "transcribing":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      );
    case "analyze":
    case "analyzing":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.813 15.904L9 18.75l-.813-2.846a4.5 4.5 0 00-3.09-3.09L2.25 12l2.846-.813a4.5 4.5 0 003.09-3.09L9 5.25l.813 2.846a4.5 4.5 0 003.09 3.09L15.75 12l-2.846.813a4.5 4.5 0 00-3.09 3.09zM18.259 8.715L18 9.75l-.259-1.035a3.375 3.375 0 00-2.455-2.456L14.25 6l1.036-.259a3.375 3.375 0 002.455-2.456L18 2.25l.259 1.035a3.375 3.375 0 002.456 2.456L21.75 6l-1.035.259a3.375 3.375 0 00-2.456 2.456z" />
        </svg>
      );
    case "clip":
    case "clipping":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.121 14.121L19 19m-7-7l7-7m-7 7l-2.879 2.879a3 3 0 11-4.242-4.242 3 3 0 014.242 0M9.879 9.879l2.121 2.121m0 0L9.879 9.879m0 0L7 7a3 3 0 10-4.243 4.243 3 3 0 004.243 0" />
        </svg>
      );
    case "reframe":
    case "reframing":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 18h.01M7 21h10a2 2 0 002-2V5a2 2 0 00-2-2H7a2 2 0 00-2 2v14a2 2 0 002 2z" />
        </svg>
      );
    case "caption":
    case "captioning":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 8h10M7 12h4m1 8l-4-4H5a2 2 0 01-2-2V6a2 2 0 012-2h14a2 2 0 012 2v8a2 2 0 01-2 2h-3l-4 4z" />
        </svg>
      );
    case "done":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "failed":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
        </svg>
      );
    case "killed":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
        </svg>
      );
    case "pending":
    default:
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
  }
}

export function renderPresetIcon(presetId: string, className: string = "h-3.5 w-3.5 shrink-0"): ReactNode {
  switch (presetId) {
    case "affiliate":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M16 11V7a4 4 0 00-8 0v4M5 9h14l1 12H4L5 9z" />
        </svg>
      );
    case "podcast":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
        </svg>
      );
    case "comedy":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M14.828 14.828a4 4 0 01-5.656 0M9 10h.01M15 10h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      );
    case "education":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
        </svg>
      );
    case "storytelling":
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M12 6.253v13m0-13C10.832 5.477 9.246 5 7.5 5S4.168 5.477 3 6.253v13C4.168 18.477 5.754 18 7.5 18s3.332.477 4.5 1.253m0-13C13.168 5.477 14.754 5 16.5 5c1.747 0 3.332.477 4.5 1.253v13C19.832 18.477 18.247 18 16.5 18c-1.746 0-3.332.477-4.5 1.253" />
        </svg>
      );
    default:
      return (
        <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M7 7h.01M7 3h5c.512 0 1.024.195 1.414.586l7 7a2 2 0 010 2.828l-7 7a2 2 0 01-2.828 0l-7-7A1.994 1.994 0 013 12V7a4 4 0 014-4z" />
        </svg>
      );
  }
}
