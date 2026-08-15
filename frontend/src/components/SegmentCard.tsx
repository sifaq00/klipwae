import { useState } from "react";
import type { Segment } from "../types";

interface Props {
  seg: Segment;
  index: number;
  onPlay: () => void;
  onReject: () => void;
  onToggle: (field: "reviewed" | "posted") => void;
  onToast?: (msg: string) => void;
}

export function SegmentCard({ seg, index, onPlay, onReject, onToggle, onToast }: Props) {
  const [copied, setCopied] = useState(false);
  const [copiedAffiliate, setCopiedAffiliate] = useState(false);
  const conf = seg.confidence ?? 0;

  const copyCaption = async () => {
    if (!seg.caption_text) return;
    try {
      await navigator.clipboard.writeText(seg.caption_text);
      setCopied(true);
      onToast?.("Caption tersalin ke clipboard");
      setTimeout(() => setCopied(false), 1600);
    } catch {
      /* ignore */
    }
  };

  const copyAffiliateCaption = async () => {
    const textToCopy = seg.affiliate_caption
      ? (seg.hashtags && seg.hashtags.length > 0
          ? `${seg.affiliate_caption}\n\n${seg.hashtags.join(" ")}`
          : seg.affiliate_caption)
      : (seg.caption_text || "");
    if (!textToCopy) return;
    try {
      await navigator.clipboard.writeText(textToCopy);
      setCopiedAffiliate(true);
      onToast?.("Affiliate caption tersalin ke clipboard");
      setTimeout(() => setCopiedAffiliate(false), 1600);
    } catch {
      /* ignore */
    }
  };

  return (
    <div
      className={`glass card-hover animate-fadeUp overflow-hidden ${seg.posted ? "border-gold/50" : ""} ${seg.reviewed ? "border-emerald-500/40" : ""}`}
      style={{ animationDelay: `${index * 60}ms` }}
    >
      {/* Thumbnail / player */}
      <div className="group relative aspect-[9/12] cursor-pointer overflow-hidden bg-black" onClick={onPlay}>
        {seg.thumb_url ? (
          <img
            src={seg.thumb_url}
            alt={seg.product_mentioned ?? "klip"}
            loading="lazy"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
          />
        ) : (
          <video
            src={seg.preview_url ?? undefined}
            preload="metadata"
            className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.04]"
          />
        )}
        <div className="absolute inset-0 bg-gradient-to-t from-black/70 via-transparent to-black/20 opacity-80 transition-opacity group-hover:opacity-100" />
        <div className="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-200 group-hover:opacity-100">
          <span className="flex h-12 w-12 items-center justify-center rounded-full bg-white/15 backdrop-blur-sm">
            <svg className="ml-0.5 h-5 w-5 text-white" fill="currentColor" viewBox="0 0 24 24"><path d="M8 5v14l11-7z" /></svg>
          </span>
        </div>
        <div className="absolute left-2.5 top-2.5 flex flex-wrap items-center gap-1.5 max-w-[85%]">
          <span className="chip border border-gold/40 bg-black/50 text-gold backdrop-blur-sm">
            <svg className="h-3 w-3" fill="currentColor" viewBox="0 0 24 24">
              <path d="M12 2l2.4 7.2H22l-6 4.4 2.3 7.1-6.3-4.5-6.3 4.5L8 13.6 2 9.2h7.6z" />
            </svg>
            {seg.product_mentioned || "produk"}
          </span>
        </div>
        <div className="absolute bottom-2.5 right-2.5 flex items-center gap-1.5">
          {seg.layout_type && (
            <span className="chip border border-white/10 bg-black/50 text-slate-300 backdrop-blur-sm">
              {seg.layout_type.replace("_", " ")}
            </span>
          )}
          {seg.start_time && (
            <span className="chip border border-white/10 bg-black/50 font-mono text-slate-200 backdrop-blur-sm">
              {seg.start_time.slice(0, 8)}–{seg.end_time?.slice(0, 8)}
            </span>
          )}
        </div>
      </div>

      <div className="space-y-2.5 p-3.5">
        <div className="flex items-center gap-2">
          <ConfRing value={conf} />
          <p className="line-clamp-2 flex-1 text-[13px] leading-snug text-slate-300">{seg.topic || "Tanpa topik"}</p>
        </div>

        {seg.affiliate_caption ? (
          <div className="relative rounded-lg border border-amber-500/30 bg-amber-500/10 p-2.5">
            <div className="flex items-center justify-between gap-1 mb-1">
              <span className="text-[10px] font-semibold text-amber-300 flex items-center gap-1">
                <svg className="h-3 w-3 text-amber-400 shrink-0" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
                </svg>
                <span>Affiliate Copy</span>
              </span>
              <button
                onClick={copyAffiliateCaption}
                className={`flex h-6 w-6 items-center justify-center rounded-md transition-all ${
                  copiedAffiliate ? "bg-emerald-500/20 text-emerald-300" : "bg-amber-500/20 text-amber-300 hover:bg-amber-500/30"
                }`}
                title="Salin caption & hashtag"
              >
                {copiedAffiliate ? (
                  <svg className="h-3.5 w-3.5 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                  </svg>
                ) : (
                  <svg className="h-3.5 w-3.5 text-amber-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                    <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                  </svg>
                )}
              </button>
            </div>
            <p className="whitespace-pre-wrap text-[11px] leading-relaxed text-slate-300">{seg.affiliate_caption}</p>
            {seg.hashtags && seg.hashtags.length > 0 && (
              <p className="mt-1.5 text-[10px] text-amber-200/70 font-mono">{seg.hashtags.join(" ")}</p>
            )}
            {seg.virality_reason && (
              <p className="mt-1 text-[10px] italic text-slate-400 flex items-start gap-1">
                <svg className="h-3 w-3 text-amber-400 shrink-0 mt-0.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
                </svg>
                <span>{seg.virality_reason}</span>
              </p>
            )}
          </div>
        ) : seg.caption_text ? (
          <div className="relative rounded-lg border border-edge bg-raise/70 p-2.5">
            <button
              onClick={copyCaption}
              className={`absolute right-2 top-2 flex h-6 w-6 items-center justify-center rounded-md transition-all ${
                copied ? "bg-emerald-500/20 text-emerald-300" : "bg-accent/20 text-accent hover:bg-accent/30"
              }`}
              title="Salin caption"
            >
              {copied ? (
                <svg className="h-3.5 w-3.5 text-emerald-300" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2.5}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M5 13l4 4L19 7" />
                </svg>
              ) : (
                <svg className="h-3.5 w-3.5 text-accent" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M8 16H6a2 2 0 01-2-2V6a2 2 0 012-2h8a2 2 0 012 2v2m-6 12h8a2 2 0 002-2v-8a2 2 0 00-2-2h-8a2 2 0 00-2 2v8a2 2 0 002 2z" />
                </svg>
              )}
            </button>
            <pre className="whitespace-pre-wrap pr-8 text-[11px] leading-relaxed text-slate-400">{seg.caption_text}</pre>
          </div>
        ) : null}


        <div className="flex items-center gap-1.5 pt-0.5">
          <button
            onClick={() => onToggle("reviewed")}
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
          <button
            onClick={onReject}
            className="rounded-lg border border-edge bg-raise/50 px-2 py-1.5 text-[11px] font-semibold text-slate-500 transition-all hover:border-red-500/50 hover:text-red-400 active:scale-[0.97]"
            title="Buang klip + hapus file"
          >
            Buang
          </button>
          {seg.preview_url && (
            <a
              href={seg.preview_url}
              download
              onClick={(e) => e.stopPropagation()}
              className="flex items-center justify-center rounded-lg border border-edge bg-raise/50 px-2 py-1.5 text-[11px] font-semibold text-slate-400 transition-all hover:border-teal-400/50 hover:text-teal-300 active:scale-[0.97]"
              title="Download klip final"
            >
              <svg className="h-3.5 w-3.5" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
              </svg>
            </a>
          )}
        </div>
      </div>
    </div>
  );
}

function ConfRing({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const r = 11;
  const c = 2 * Math.PI * r;
  const color = value >= 0.8 ? "#34d399" : value >= 0.6 ? "#fbbf24" : "#94a3b8";
  return (
    <div className="relative h-8 w-8 shrink-0" title={`Confidence ${pct}%`}>
      <svg viewBox="0 0 28 28" className="h-8 w-8 -rotate-90">
        <circle cx="14" cy="14" r={r} fill="none" stroke="rgba(148,163,184,0.15)" strokeWidth="3" />
        <circle
          cx="14" cy="14" r={r} fill="none" stroke={color} strokeWidth="3"
          strokeLinecap="round" strokeDasharray={c} strokeDashoffset={c * (1 - value)}
        />
      </svg>
      <span className="absolute inset-0 flex items-center justify-center text-[9px] font-semibold text-slate-300">
        {pct}
      </span>
    </div>
  );
}
