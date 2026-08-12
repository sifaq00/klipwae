import { useEffect, useRef, useState } from "react";
import type { CaptionStyle } from "../types";
import { getStylePreview, listFonts } from "../lib/api";

const DEFAULTS: CaptionStyle = {
  enabled: true,
  font: "Segoe UI",
  size: 96,
  bold: true,
  italic: false,
  uppercase: false,
  pop: false,
  spacing: 0,
  line_spacing: 0,
  text_color: "#FFFFFF",
  highlight_color: "#FFFF00",
  outline: 6,
  outline_color: "#000000",
  border_style: "outline",
  shadow: 3,
  shadow_color: "#000000",
  position: "bottom",
  margin_v: 100,
  style: "highlight",
};

interface Preset {
  name: string;
  style: Partial<CaptionStyle>;
}

const PRESETS: Preset[] = [
  {
    name: "Karaoke klasik",
    style: { font: "Poppins", size: 100, bold: true, italic: false, uppercase: false, pop: false, spacing: 0, text_color: "#FFFFFF", highlight_color: "#FFD400", outline: 7, outline_color: "#000000", border_style: "outline", shadow: 3, shadow_color: "#000000", position: "bottom", margin_v: 100, style: "highlight" },
  },
  {
    name: "Pop besar",
    style: { font: "Poppins", size: 104, bold: true, pop: true, highlight_color: "#FFD400", outline: 7, shadow: 4, style: "highlight" },
  },
  {
    name: "Bold tengah",
    style: { font: "Poppins ExtraBold", size: 118, bold: true, uppercase: false, outline: 7, shadow: 4, margin_v: 90, style: "static" },
  },
  {
    name: "Minimal atas",
    style: { font: "Segoe UI", size: 68, bold: false, outline: 3, shadow: 1, position: "top", margin_v: 40, style: "static" },
  },
  {
    name: "Neon",
    style: { font: "Poppins", size: 96, bold: true, outline: 0, shadow: 6, shadow_color: "#00E5FF", text_color: "#FFFFFF", highlight_color: "#FF2EC4", style: "highlight" },
  },
  {
    name: "Uppercase tebal",
    style: { font: "Anton", size: 108, bold: true, uppercase: true, spacing: 2, outline: 5, shadow: 2, style: "static" },
  },
  {
    name: "Kotak berita",
    style: { font: "Lato", size: 84, bold: true, border_style: "box", outline: 4, shadow: 2, margin_v: 80, style: "static" },
  },
];

function presetNameOf(s: CaptionStyle): string | null {
  for (const p of PRESETS) {
    const merged = { ...defaultStyle(), ...p.style };
    if (JSON.stringify(merged) === JSON.stringify(s)) return p.name;
  }
  return null;
}

export function defaultStyle(): CaptionStyle {
  return { ...DEFAULTS };
}

interface Props {
  value: CaptionStyle;
  onChange: (s: CaptionStyle) => void;
  compact?: boolean;
  previewSide?: "right" | "bottom";
}

export function StyleEditor({ value, onChange, compact, previewSide = "bottom" }: Props) {
  const [fonts, setFonts] = useState<string[]>([]);
  const [fontOpen, setFontOpen] = useState(false);
  const [fontQuery, setFontQuery] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const previewTimer = useRef<number | null>(null);

  useEffect(() => {
    listFonts().then(setFonts).catch(() => setFonts([]));
  }, []);

  // Preview REAL via libass (engine sama dengan burn-in) — debounce 500ms
  useEffect(() => {
    if (previewTimer.current) window.clearTimeout(previewTimer.current);
    previewTimer.current = window.setTimeout(() => {
      setPreviewBusy(true);
      getStylePreview(value)
        .then(setPreviewUrl)
        .catch(() => {})
        .finally(() => setPreviewBusy(false));
    }, 500);
    return () => {
      if (previewTimer.current) window.clearTimeout(previewTimer.current);
    };
  }, [value]);

  const set = <K extends keyof CaptionStyle>(k: K, v: CaptionStyle[K]) =>
    onChange({ ...value, [k]: v });

  const filteredFonts = fontQuery
    ? fonts.filter((f) => f.toLowerCase().includes(fontQuery.toLowerCase()))
    : fonts;

  const form = (
    <div className={`space-y-4 ${compact ? "text-xs" : ""}`}>
      <button
        type="button"
        onClick={() => onChange({ ...value, enabled: !value.enabled })}
        className={`flex w-full items-center justify-between rounded-xl border px-3 py-2.5 text-left transition-all ${
          value.enabled
            ? "border-emerald-400/40 bg-emerald-400/10"
            : "border-edge bg-raise/60 opacity-80"
        }`}
      >
        <div>
          <p className="text-xs font-semibold text-slate-200">Aktifkan subtitle</p>
          <p className="text-[10px] text-slate-500">
            {value.enabled
              ? "Subtitle karaoke di-burn ke klip final"
              : "Stage subtitle di-skip — klip tetap jadi tanpa teks"}
          </p>
        </div>
        <span
          className={`relative h-5 w-9 shrink-0 rounded-full transition-colors ${
            value.enabled ? "bg-emerald-400" : "bg-slate-700"
          }`}
        >
          <span
            className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
              value.enabled ? "left-[18px]" : "left-0.5"
            }`}
          />
        </span>
      </button>

      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">Preset</p>
        <div className="flex flex-wrap gap-1.5">
          {PRESETS.map((p) => (
            <button
              key={p.name}
              type="button"
              onClick={() => onChange({ ...defaultStyle(), ...p.style })}
              className={`rounded-full border px-3 py-1 text-[11px] font-semibold transition-all ${
                presetNameOf(value) === p.name
                  ? "border-accent/60 bg-accent/20 text-accent"
                  : "border-edge bg-raise/50 text-slate-400 hover:border-accent/40 hover:text-slate-200"
              }`}
            >
              {p.name}
            </button>
          ))}
          {presetNameOf(value) === null && (
            <span className="rounded-full border border-edge px-3 py-1 text-[11px] font-semibold text-slate-500">
              Kustom
            </span>
          )}
        </div>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <Field label="Font">
          <div className="relative">
            <button
              type="button"
              onClick={() => { setFontOpen((o) => !o); setFontQuery(""); }}
              className="input-glass flex w-full items-center justify-between py-2 text-left"
              style={{ fontFamily: value.font }}
            >
              <span className="truncate">{value.font || "Segoe UI"}</span>
              <svg className="h-3.5 w-3.5 shrink-0 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
              </svg>
            </button>
            {fontOpen && (
              <>
                <div className="fixed inset-0 z-10" onClick={() => setFontOpen(false)} />
                <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-xl border border-edge bg-raise shadow-2xl">
                  <div className="border-b border-edge p-2">
                    <div className="relative">
                      <svg className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                        <path strokeLinecap="round" strokeLinejoin="round" d="M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z" />
                      </svg>
                      <input
                        autoFocus
                        value={fontQuery}
                        onChange={(e) => setFontQuery(e.target.value)}
                        placeholder="Cari font… (205 terinstall)"
                        className="w-full rounded-lg border border-edge bg-panel py-1.5 pl-8 pr-2 text-xs outline-none focus:border-accent/60"
                      />
                    </div>
                  </div>
                  <div className="max-h-44 overflow-y-auto">
                    {filteredFonts.length === 0 && (
                      <div className="px-3 py-2 text-xs text-slate-500">Font tidak ditemukan</div>
                    )}
                    {filteredFonts.map((f) => (
                      <button
                        key={f}
                        type="button"
                        onClick={() => { set("font", f); setFontOpen(false); }}
                        className={`block w-full px-3 py-1.5 text-left hover:bg-accent/15 ${value.font === f ? "text-accent" : "text-slate-300"}`}
                        style={{ fontFamily: f }}
                      >
                        {f}
                      </button>
                    ))}
                  </div>
                </div>
              </>
            )}
          </div>
        </Field>
        <Field label="Ukuran">
          <div className="flex items-center gap-2">
            <input type="range" min={60} max={140} step={2} value={value.size}
              onChange={(e) => set("size", Number(e.target.value))} className="flex-1 accent-cyan-400" />
            <span className="w-9 text-right font-mono text-slate-300">{value.size}</span>
          </div>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <ToggleField label="Bold" value={value.bold} onChange={(v) => set("bold", v)} />
        <ToggleField label="Italic" value={value.italic} onChange={(v) => set("italic", v)} />
        <ToggleField label="ALL CAPS" value={value.uppercase} onChange={(v) => set("uppercase", v)} />
        <ToggleField label="Animasi pop" value={value.pop} onChange={(v) => set("pop", v)} />
        <Field label="Line spacing">
          <div className="flex items-center gap-2">
            <input type="range" min={0} max={80} step={2} value={value.line_spacing}
              onChange={(e) => set("line_spacing", Number(e.target.value))} className="flex-1 accent-cyan-400" />
            <span className="w-6 text-right font-mono text-slate-300">{value.line_spacing}</span>
          </div>
        </Field>
        <Field label="Letter spacing">
          <div className="flex items-center gap-2">
            <input type="range" min={0} max={8} step={1} value={value.spacing}
              onChange={(e) => set("spacing", Number(e.target.value))} className="flex-1 accent-cyan-400" />
            <span className="w-6 text-right font-mono text-slate-300">{value.spacing}</span>
          </div>
        </Field>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <ColorField label="Warna teks" value={value.text_color} onChange={(v) => set("text_color", v)} />
        <ColorField label="Highlight karaoke" value={value.highlight_color} onChange={(v) => set("highlight_color", v)} />
        <Field label="Outline">
          <div className="flex items-center gap-2">
            <input type="range" min={0} max={10} step={1} value={value.outline}
              onChange={(e) => set("outline", Number(e.target.value))} className="flex-1 accent-cyan-400" />
            <span className="w-6 text-right font-mono text-slate-300">{value.outline}</span>
          </div>
        </Field>
        <ColorField label="Warna outline" value={value.outline_color} onChange={(v) => set("outline_color", v)} />
        <Field label="Outline mode">
          <div className="flex overflow-hidden rounded-lg border border-edge">
            {(["outline", "box"] as const).map((b) => (
              <button key={b} type="button"
                onClick={() => set("border_style", b)}
                className={`flex-1 py-1.5 text-[11px] font-semibold capitalize transition-all ${value.border_style === b ? "bg-accent/25 text-accent" : "bg-raise/50 text-slate-500 hover:text-slate-300"}`}>
                {b === "outline" ? "Garis" : "Kotak"}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Shadow">
          <div className="flex items-center gap-2">
            <input type="range" min={0} max={6} step={1} value={value.shadow}
              onChange={(e) => set("shadow", Number(e.target.value))} className="flex-1 accent-cyan-400" />
            <span className="w-6 text-right font-mono text-slate-300">{value.shadow}</span>
          </div>
        </Field>
        <ColorField label="Warna shadow" value={value.shadow_color} onChange={(v) => set("shadow_color", v)} />
        <Field label="Posisi">
          <div className="flex overflow-hidden rounded-lg border border-edge">
            {(["bottom", "top"] as const).map((p) => (
              <button key={p} type="button"
                onClick={() => set("position", p)}
                className={`flex-1 py-1.5 text-[11px] font-semibold capitalize transition-all ${value.position === p ? "bg-accent/25 text-accent" : "bg-raise/50 text-slate-500 hover:text-slate-300"}`}>
                {p === "bottom" ? "Bawah" : "Atas"}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Margin bawah">
          <div className="flex items-center gap-2">
            <input type="range" min={30} max={240} step={5} value={value.margin_v}
              onChange={(e) => set("margin_v", Number(e.target.value))} className="flex-1 accent-cyan-400" />
            <span className="w-8 text-right font-mono text-slate-300">{value.margin_v}</span>
          </div>
        </Field>
        <Field label="Gaya">
          <div className="flex overflow-hidden rounded-lg border border-edge">
            {(["highlight", "static"] as const).map((s) => (
              <button key={s} type="button"
                onClick={() => set("style", s)}
                className={`flex-1 py-1.5 text-[11px] font-semibold capitalize transition-all ${value.style === s ? "bg-accent/25 text-accent" : "bg-raise/50 text-slate-500 hover:text-slate-300"}`}>
                {s === "highlight" ? "Karaoke" : "Statis"}
              </button>
            ))}
          </div>
        </Field>
      </div>
    </div>
  );

  const preview = (
    <div className="w-full max-w-[220px]">
      <p className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">
        Preview
        {previewBusy && (
          <svg className="ml-1.5 inline h-3 w-3 animate-spin text-accent" viewBox="0 0 24 24" fill="none">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
            <path className="opacity-90" fill="currentColor" d="M4 12a8 8 0 018-8v3a5 5 0 00-5 5H4z" />
          </svg>
        )}
      </p>
      <div className="relative aspect-[9/16] w-full overflow-hidden rounded-xl border border-edge bg-slate-900">
        {previewUrl ? (
          <img src={previewUrl} alt="Preview subtitle" className="h-full w-full object-cover" />
        ) : (
          <div className="flex h-full items-center justify-center text-xs text-slate-600">
            {previewBusy ? "Merender…" : "—"}
          </div>
        )}
      </div>
      <p className="mt-1 text-[9px] leading-snug text-slate-600">
        — dirender ffmpeg/libass, sama persis dengan hasil burn-in
      </p>
    </div>
  );

  if (previewSide === "right") {
    return (
      <div className="grid gap-8 lg:grid-cols-[1fr_auto]">
        {form}
        <div className="lg:sticky lg:top-4">{preview}</div>
      </div>
    );
  }
  return (
    <div className="space-y-4">
      {form}
      {preview}
    </div>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      {children}
    </label>
  );
}

function ToggleField({ label, value, onChange }: { label: string; value: boolean; onChange: (v: boolean) => void }) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-edge bg-raise/60 px-3 py-2">
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative h-5 w-9 rounded-full transition-colors ${value ? "bg-accent" : "bg-slate-700"}`}
      >
        <span className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${value ? "left-[18px]" : "left-0.5"}`} />
      </button>
    </label>
  );
}

function ColorField({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="block">
      <span className="mb-1 block text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <div className="flex items-center gap-2 rounded-xl border border-edge bg-raise/60 px-2 py-1">
        <input
          type="color"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="h-7 w-9 cursor-pointer rounded border-0 bg-transparent p-0"
        />
        <span className="font-mono text-xs uppercase text-slate-400">{value}</span>
      </div>
    </label>
  );
}
