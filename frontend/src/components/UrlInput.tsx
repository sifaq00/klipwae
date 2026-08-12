import { useState } from "react";

interface Props {
  onSubmit: (url: string) => Promise<void>;
}

export function UrlInput({ onSubmit }: Props) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const handle = async () => {
    if (!url.trim() || loading) return;
    setLoading(true);
    setErr("");
    try {
      await onSubmit(url.trim());
      setUrl("");
    } catch (e: unknown) {
      setErr(e instanceof Error ? e.message : "Gagal membuat job");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="animate-fadeUp">
      <div className="relative">
        <div className="absolute -inset-0.5 rounded-2xl bg-gradient-to-r from-accent/40 via-sky-500/30 to-neon/40 opacity-70 blur-md transition-opacity duration-300 group-hover:opacity-100" />
        <div className="glass relative flex gap-2 p-2">
          <svg
            className="ml-3 self-center h-4 w-4 shrink-0 text-slate-500"
            fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}
          >
            <path strokeLinecap="round" strokeLinejoin="round"
              d="M13.19 8.688a4.5 4.5 0 011.242 7.244l-4.5 4.5a4.5 4.5 0 01-6.364-6.364l1.757-1.757m13.35-.622l1.757-1.757a4.5 4.5 0 00-6.364-6.364l-4.5 4.5a4.5 4.5 0 001.242 7.244" />
          </svg>
          <input
            className="flex-1 bg-transparent font-mono text-sm placeholder:text-slate-500 focus:outline-none"
            placeholder="Tempel link YouTube podcast — biarkan AI memotong bagian produk…"
            value={url}
            onChange={(e) => setUrl(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handle()}
            spellCheck={false}
          />
          <button
            className="btn-primary px-5 py-2.5 text-sm"
            disabled={loading || !url.trim()}
            onClick={handle}
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <svg className="h-4 w-4 animate-spin" viewBox="0 0 24 24" fill="none">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
                </svg>
                Memulai…
              </span>
            ) : (
              <span className="flex items-center gap-2">
                <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                  <path strokeLinecap="round" strokeLinejoin="round" d="M13 10V3L4 14h7v7l9-11h-7z" />
                </svg>
                Bikin Klip
              </span>
            )}
          </button>
        </div>
      </div>
      {err && (
        <p className="mt-2 animate-fadeUp text-xs text-red-400">⚠ {err}</p>
      )}
      <p className="mt-3 text-xs text-slate-500">
        Pipeline otomatis: download → transkrip → deteksi produk → klip 30–60 dtk → vertikal → subtitle karaoke
      </p>
    </div>
  );
}
