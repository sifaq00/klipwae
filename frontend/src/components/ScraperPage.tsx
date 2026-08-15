import { useState } from "react";
import type { ScrapeItem } from "../types";
import { scrape, createJob } from "../lib/api";

interface Props {
  onAdded: () => void;
  onBack: () => void;
  showToast: (msg: string) => void;
}

export function ScraperPage({ onAdded, onBack, showToast }: Props) {
  const [query, setQuery] = useState("");
  const [busy, setBusy] = useState(false);
  const [items, setItems] = useState<ScrapeItem[]>([]);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [adding, setAdding] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSearch = async () => {
    if (!query.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await scrape(query.trim());
      setItems(res.items);
      setSelected(new Set());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Gagal mencari video");
    } finally {
      setBusy(false);
    }
  };

  const toggle = (id: string) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const handleAdd = async () => {
    const chosen = items.filter((i) => selected.has(i.id));
    if (!chosen.length) return;
    setAdding(true);
    let ok = 0;
    for (const item of chosen) {
      try {
        await createJob(item.url);
        ok += 1;
      } catch {
        // job duplikat / gagal — lewati, tetap lanjut
      }
    }
    setAdding(false);
    showToast(`${ok}/${chosen.length} episode ditambahkan ke Studio`);
    setSelected(new Set());
    onAdded();
  };

  return (
    <div className="space-y-6">
      <div className="glass animate-fadeUp p-5">
        <div className="flex items-start gap-4">
          <button
            onClick={onBack}
            className="mt-0.5 rounded-lg border border-edge bg-raise/50 px-3 py-2 text-xs font-semibold text-slate-300 transition-colors hover:border-accent/40 hover:text-cyan-300"
          >
            ← Semua episode
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="font-display text-lg font-bold text-slate-100">Scraper YouTube</h1>
            <p className="mt-1 text-sm text-slate-500">
              Deskripsi video yang kamu cari — misal:{" "}
              <button
                className="text-cyan-400 underline-offset-2 hover:underline"
                onClick={() => setQuery("podcast indonesia review skincare produk sponsor")}
              >
                podcast indonesia yang bahas produk skincare sponsor
              </button>
            </p>
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && handleSearch()}
            placeholder="Kamu mau video kayak apa? (judul/deskripsi video di YouTube)"
            className="w-full rounded-xl border border-edge bg-raise/70 px-4 py-3 text-sm text-slate-100 placeholder:text-slate-500 outline-none transition-all focus:border-accent/70 focus:shadow-[0_0_0_3px_rgba(20,184,166,0.15)]"
          />
          <button
            onClick={handleSearch}
            disabled={busy || !query.trim()}
            className="btn-primary shrink-0 px-5 py-3 text-sm disabled:opacity-50"
          >
            {busy ? "Mencari…" : "Cari"}
          </button>
        </div>
        {error && <p className="mt-2 text-xs text-red-400">{error}</p>}
      </div>

      {items.length > 0 && (
        <>
          <div className="flex items-center justify-between">
            <span className="text-xs text-slate-500">
              {items.length} video · pilih yang mau ditambahkan
            </span>
            <button
              onClick={handleAdd}
              disabled={adding || selected.size === 0}
              className="btn-primary px-4 py-2 text-xs disabled:opacity-50"
            >
              {adding ? "Menambahkan…" : `Tambah ke Studio (${selected.size})`}
            </button>
          </div>
          <div className="space-y-2">
            {items.map((item) => (
              <button
                key={item.id}
                onClick={() => toggle(item.id)}
                className={`glass flex w-full items-center gap-3 p-2 text-left transition-all ${
                  selected.has(item.id) ? "border-accent/60 ring-1 ring-accent/40" : ""
                }`}
              >
                <img
                  src={`https://i.ytimg.com/vi/${item.id}/mqdefault.jpg`}
                  alt=""
                  loading="lazy"
                  className="h-14 w-24 shrink-0 rounded-lg object-cover"
                  onError={(e) => { (e.currentTarget as HTMLImageElement).style.visibility = "hidden"; }}
                />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-slate-100">{item.title || "(tanpa judul)"}</p>
                  <p className="mt-0.5 text-xs text-slate-500">
                    {item.channel ? `${item.channel} · ` : ""}
                    {item.duration ? `${Math.floor(item.duration / 60)}m${item.duration % 60}s` : "?m"} · {item.id}
                  </p>
                </div>
                <span
                  className={`flex h-5 w-5 shrink-0 items-center justify-center rounded-md border text-[10px] ${
                    selected.has(item.id)
                      ? "border-accent bg-accent text-ink"
                      : "border-edge bg-raise/60 text-transparent"
                  }`}
                >
                  ✓
                </span>
              </button>
            ))}
          </div>
        </>
      )}
      {!busy && items.length === 0 && !error && (
        <div className="glass animate-fadeUp py-14 text-center text-sm text-slate-500">
          Ketik deskripsi video yang dicari di atas, lalu tekan Cari.
        </div>
      )}
    </div>
  );
}
