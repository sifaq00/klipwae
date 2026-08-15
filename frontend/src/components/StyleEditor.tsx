import { useEffect, useRef, useState } from "react";
import type { CaptionStyle, FontItem } from "../types";
import { getStylePreview, listFonts } from "../lib/api";

const DEFAULTS: CaptionStyle = {
  enabled: true,
  font: "Montserrat Black",
  size: 96,
  bold: true,
  italic: false,
  uppercase: false,
  pop: false,
  bounce: true,
  auto_emoji: true,
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
  margin_v: 240,
  style: "highlight",
};

export const DEFAULT_VIRAL_FONTS: FontItem[] = [
  { name: "Montserrat Black", label: "Montserrat Black", tag: "Viral TikTok", sample: "AA" },
  { name: "Segoe UI Black", label: "Segoe UI Black", tag: "Bold Clean", sample: "AA" },
  { name: "Impact", label: "Impact", tag: "Punchy Meme", sample: "AA" },
  { name: "Arial Black", label: "Arial Black", tag: "Universal Heavy", sample: "AA" },
  { name: "Trebuchet MS", label: "Trebuchet MS", tag: "Dynamic Modern", sample: "AA" },
  { name: "Verdana Bold", label: "Verdana Bold", tag: "High Legibility", sample: "AA" },
];

interface Preset {
  name: string;
  style: Partial<CaptionStyle>;
}

const PRESETS: Preset[] = [
  {
    name: "Karaoke TikTok",
    style: {
      font: "Montserrat Black",
      size: 100,
      bold: true,
      italic: false,
      uppercase: true,
      pop: false,
      bounce: true,
      spacing: 0,
      text_color: "#FFFFFF",
      highlight_color: "#FFFF00",
      outline: 7,
      outline_color: "#000000",
      border_style: "outline",
      shadow: 3,
      shadow_color: "#000000",
      position: "bottom",
      margin_v: 240,
      style: "highlight",
    },
  },
  {
    name: "Clean High-Impact",
    style: {
      font: "Segoe UI Black",
      size: 96,
      bold: true,
      uppercase: true,
      pop: false,
      bounce: true,
      highlight_color: "#00E5FF",
      text_color: "#FFFFFF",
      outline: 6,
      shadow: 3,
      margin_v: 240,
      style: "highlight",
    },
  },
  {
    name: "Punchy Meme",
    style: {
      font: "Impact",
      size: 108,
      bold: true,
      uppercase: true,
      outline: 8,
      shadow: 4,
      highlight_color: "#FFD400",
      margin_v: 240,
      style: "highlight",
    },
  },
  {
    name: "Universal Heavy",
    style: {
      font: "Arial Black",
      size: 100,
      bold: true,
      uppercase: true,
      outline: 7,
      shadow: 3,
      margin_v: 240,
      style: "static",
    },
  },
  {
    name: "Dynamic Smooth",
    style: {
      font: "Trebuchet MS",
      size: 96,
      bold: true,
      italic: false,
      outline: 5,
      shadow: 3,
      highlight_color: "#FF2EC4",
      margin_v: 240,
      style: "highlight",
    },
  },
  {
    name: "Pop Besar",
    style: {
      font: "Montserrat Black",
      size: 104,
      bold: true,
      pop: true,
      bounce: true,
      highlight_color: "#FFD400",
      outline: 7,
      shadow: 4,
      style: "highlight",
    },
  },
  {
    name: "Minimal Atas",
    style: {
      font: "Segoe UI",
      size: 68,
      bold: false,
      outline: 3,
      shadow: 1,
      position: "top",
      margin_v: 40,
      style: "static",
    },
  },
  {
    name: "Kotak Berita",
    style: {
      font: "Verdana Bold",
      size: 84,
      bold: true,
      border_style: "box",
      outline: 4,
      shadow: 2,
      margin_v: 80,
      style: "static",
    },
  },
];

function getTagBadgeStyle(tag: string, active: boolean) {
  const t = tag.toLowerCase();
  if (t.includes("tiktok") || t.includes("viral")) {
    return active
      ? "bg-rose-500/25 text-rose-300 border-rose-400/60"
      : "bg-rose-500/15 text-rose-400 border-rose-500/30";
  }
  if (t.includes("clean") || t.includes("bold clean")) {
    return active
      ? "bg-sky-500/25 text-sky-300 border-sky-400/60"
      : "bg-sky-500/15 text-sky-400 border-sky-500/30";
  }
  if (t.includes("meme") || t.includes("punchy")) {
    return active
      ? "bg-amber-500/25 text-amber-300 border-amber-400/60"
      : "bg-amber-500/15 text-amber-400 border-amber-500/30";
  }
  if (t.includes("heavy") || t.includes("universal")) {
    return active
      ? "bg-purple-500/25 text-purple-300 border-purple-400/60"
      : "bg-purple-500/15 text-purple-400 border-purple-500/30";
  }
  if (t.includes("dynamic") || t.includes("modern")) {
    return active
      ? "bg-teal-500/25 text-teal-300 border-teal-400/60"
      : "bg-teal-500/15 text-teal-400 border-teal-500/30";
  }
  return active
    ? "bg-emerald-500/25 text-emerald-300 border-emerald-400/60"
    : "bg-emerald-500/15 text-emerald-400 border-emerald-500/30";
}

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
  const [viralFonts, setViralFonts] = useState<FontItem[]>(DEFAULT_VIRAL_FONTS);
  const [fontOpen, setFontOpen] = useState(false);
  const [fontQuery, setFontQuery] = useState("");
  const [previewUrl, setPreviewUrl] = useState<string | null>(null);
  const [previewBusy, setPreviewBusy] = useState(false);
  const previewTimer = useRef<number | null>(null);

  useEffect(() => {
    listFonts()
      .then((res) => {
        setFonts(res.fonts || []);
        if (res.available_fonts && res.available_fonts.length > 0) {
          setViralFonts(res.available_fonts);
        }
      })
      .catch(() => setFonts([]));
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

  const currentViralMatch = viralFonts.find(
    (f) => f.name.toLowerCase() === (value.font || "").toLowerCase()
  );

  const form = (
    <div className={`space-y-4 ${compact ? "text-xs" : ""}`}>
      {/* Toggle Enable */}
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

      {/* Preset Buttons */}
      <div>
        <p className="mb-1.5 text-[11px] uppercase tracking-wider text-slate-500">Preset Gaya</p>
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

      {/* Viral Font Pack Selector */}
      <div className="rounded-2xl border border-edge/80 bg-raise/40 p-3.5 space-y-3">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="flex h-5 w-5 items-center justify-center rounded-lg bg-accent/20 text-[11px] font-bold text-accent">
              🔤
            </span>
            <p className="text-[11px] font-bold uppercase tracking-wider text-slate-300">
              Font Pack Viral
            </p>
          </div>
          {currentViralMatch ? (
            <span
              className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-0.5 text-[10px] font-bold transition-all ${getTagBadgeStyle(
                currentViralMatch.tag,
                true
              )}`}
            >
              <span className="h-1.5 w-1.5 rounded-full bg-current animate-pulse" />
              {currentViralMatch.tag} ({currentViralMatch.name})
            </span>
          ) : (
            <span className="rounded-full border border-edge bg-raise px-2 py-0.5 text-[10px] text-slate-400">
              Font Kustom: {value.font || "Default"}
            </span>
          )}
        </div>

        {/* 1-Click Viral Font Cards Grid */}
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-3">
          {viralFonts.map((f) => {
            const isSelected =
              (value.font || "").toLowerCase() === f.name.toLowerCase() ||
              (value.font || "").toLowerCase() === f.label.toLowerCase();
            return (
              <button
                key={f.name}
                type="button"
                onClick={() => set("font", f.name)}
                className={`group relative flex flex-col justify-between rounded-xl border p-2.5 text-left transition-all ${
                  isSelected
                    ? "border-accent bg-accent/15 shadow-sm shadow-accent/20 ring-1 ring-accent/50"
                    : "border-edge bg-raise/60 hover:border-slate-600 hover:bg-raise/90"
                }`}
              >
                <div className="flex items-center justify-between gap-1">
                  <span
                    className={`inline-block rounded-md border px-1.5 py-0.5 text-[9px] font-semibold transition-colors ${getTagBadgeStyle(
                      f.tag,
                      isSelected
                    )}`}
                  >
                    {f.tag}
                  </span>
                  {isSelected && (
                    <span className="flex h-4 w-4 shrink-0 items-center justify-center rounded-full bg-accent text-[10px] font-black text-slate-950">
                      ✓
                    </span>
                  )}
                </div>
                <div className="mt-2.5">
                  <div
                    className={`text-sm leading-tight transition-colors ${
                      isSelected ? "font-bold text-accent" : "font-semibold text-slate-200 group-hover:text-white"
                    }`}
                    style={{ fontFamily: f.name }}
                  >
                    {f.label}
                  </div>
                  <div
                    className="mt-0.5 text-[11px] text-slate-400/80"
                    style={{ fontFamily: f.name }}
                  >
                    {f.sample || "AA"} Viral Impact
                  </div>
                </div>
              </button>
            );
          })}
        </div>

        {/* System Font Selector Dropdown */}
        <div className="border-t border-edge/60 pt-2.5">
          <div className="flex items-center justify-between">
            <button
              type="button"
              onClick={() => {
                setFontOpen((o) => !o);
                setFontQuery("");
              }}
              className="flex items-center gap-1.5 text-[11px] font-medium text-slate-400 hover:text-slate-200 transition-colors"
            >
              <span>{fontOpen ? "▲ Tutup font sistem" : "▼ Atau pilih dari semua font sistem..."}</span>
              {fonts.length > 0 && (
                <span className="text-[10px] text-slate-500">({fonts.length} terpasang)</span>
              )}
            </button>
          </div>

          {fontOpen && (
            <div className="mt-2 overflow-hidden rounded-xl border border-edge bg-panel shadow-2xl">
              <div className="border-b border-edge p-2">
                <div className="relative">
                  <svg
                    className="absolute left-2.5 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-500"
                    fill="none"
                    viewBox="0 0 24 24"
                    stroke="currentColor"
                    strokeWidth={2}
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      d="M21 21l-4.35-4.35M17 10.5a6.5 6.5 0 11-13 0 6.5 6.5 0 0113 0z"
                    />
                  </svg>
                  <input
                    autoFocus
                    value={fontQuery}
                    onChange={(e) => setFontQuery(e.target.value)}
                    placeholder="Cari font sistem…"
                    className="w-full rounded-lg border border-edge bg-raise py-1.5 pl-8 pr-2 text-xs outline-none focus:border-accent/60"
                  />
                </div>
              </div>
              <div className="max-h-44 overflow-y-auto p-1 space-y-0.5">
                {filteredFonts.length === 0 && (
                  <div className="px-3 py-2 text-xs text-slate-500">Font tidak ditemukan</div>
                )}
                {filteredFonts.map((f) => (
                  <button
                    key={f}
                    type="button"
                    onClick={() => {
                      set("font", f);
                      setFontOpen(false);
                    }}
                    className={`flex w-full items-center justify-between rounded-lg px-2.5 py-1.5 text-left text-xs transition-colors hover:bg-accent/15 ${
                      value.font === f ? "bg-accent/10 font-semibold text-accent" : "text-slate-300"
                    }`}
                    style={{ fontFamily: f }}
                  >
                    <span className="truncate">{f}</span>
                    {value.font === f && <span className="text-[10px] text-accent">✓ Aktif</span>}
                  </button>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>

      {/* Font Size & Spacing Controls */}
      <div className="grid grid-cols-2 gap-3">
        <Field label="Ukuran Teks">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={60}
              max={140}
              step={2}
              value={value.size}
              onChange={(e) => set("size", Number(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-9 text-right font-mono text-slate-300">{value.size}</span>
          </div>
        </Field>
        <Field label="Line Spacing">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={80}
              step={2}
              value={value.line_spacing}
              onChange={(e) => set("line_spacing", Number(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-6 text-right font-mono text-slate-300">{value.line_spacing}</span>
          </div>
        </Field>
      </div>

      {/* Typography Effects */}
      <div className="grid grid-cols-2 gap-3">
        <ToggleField label="Bold" value={value.bold} onChange={(v) => set("bold", v)} />
        <ToggleField label="Italic" value={value.italic} onChange={(v) => set("italic", v)} />
        <ToggleField label="ALL CAPS" value={value.uppercase} onChange={(v) => set("uppercase", v)} />
        <ToggleField label="Animasi Pop" value={value.pop} onChange={(v) => set("pop", v)} />
        <ToggleField label="Animasi Bounce" value={value.bounce ?? true} onChange={(v) => set("bounce", v)} />
        <ToggleField label="Auto Emoji" value={value.auto_emoji ?? true} onChange={(v) => set("auto_emoji", v)} />
        <Field label="Letter Spacing">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={8}
              step={1}
              value={value.spacing}
              onChange={(e) => set("spacing", Number(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-6 text-right font-mono text-slate-300">{value.spacing}</span>
          </div>
        </Field>
        <Field label="Margin Bawah">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={30}
              max={240}
              step={5}
              value={value.margin_v}
              onChange={(e) => set("margin_v", Number(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-8 text-right font-mono text-slate-300">{value.margin_v}</span>
          </div>
        </Field>
      </div>

      {/* Colors & Styling */}
      <div className="grid grid-cols-2 gap-3">
        <ColorField label="Warna Teks" value={value.text_color} onChange={(v) => set("text_color", v)} />
        <ColorField label="Highlight Karaoke" value={value.highlight_color} onChange={(v) => set("highlight_color", v)} />
        <Field label="Outline">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={10}
              step={1}
              value={value.outline}
              onChange={(e) => set("outline", Number(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-6 text-right font-mono text-slate-300">{value.outline}</span>
          </div>
        </Field>
        <ColorField label="Warna Outline" value={value.outline_color} onChange={(v) => set("outline_color", v)} />
        <Field label="Outline Mode">
          <div className="flex overflow-hidden rounded-lg border border-edge">
            {(["outline", "box"] as const).map((b) => (
              <button
                key={b}
                type="button"
                onClick={() => set("border_style", b)}
                className={`flex-1 py-1.5 text-[11px] font-semibold capitalize transition-all ${
                  value.border_style === b
                    ? "bg-accent/25 text-accent"
                    : "bg-raise/50 text-slate-500 hover:text-slate-300"
                }`}
              >
                {b === "outline" ? "Garis" : "Kotak"}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Shadow">
          <div className="flex items-center gap-2">
            <input
              type="range"
              min={0}
              max={6}
              step={1}
              value={value.shadow}
              onChange={(e) => set("shadow", Number(e.target.value))}
              className="flex-1 accent-cyan-400"
            />
            <span className="w-6 text-right font-mono text-slate-300">{value.shadow}</span>
          </div>
        </Field>
        <ColorField label="Warna Shadow" value={value.shadow_color} onChange={(v) => set("shadow_color", v)} />
        <Field label="Posisi">
          <div className="flex overflow-hidden rounded-lg border border-edge">
            {(["bottom", "top"] as const).map((p) => (
              <button
                key={p}
                type="button"
                onClick={() => set("position", p)}
                className={`flex-1 py-1.5 text-[11px] font-semibold capitalize transition-all ${
                  value.position === p
                    ? "bg-accent/25 text-accent"
                    : "bg-raise/50 text-slate-500 hover:text-slate-300"
                }`}
              >
                {p === "bottom" ? "Bawah" : "Atas"}
              </button>
            ))}
          </div>
        </Field>
        <Field label="Gaya Teks">
          <div className="flex overflow-hidden rounded-lg border border-edge">
            {(["highlight", "static"] as const).map((s) => (
              <button
                key={s}
                type="button"
                onClick={() => set("style", s)}
                className={`flex-1 py-1.5 text-[11px] font-semibold capitalize transition-all ${
                  value.style === s
                    ? "bg-accent/25 text-accent"
                    : "bg-raise/50 text-slate-500 hover:text-slate-300"
                }`}
              >
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

function ToggleField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: (v: boolean) => void;
}) {
  return (
    <label className="flex items-center justify-between rounded-xl border border-edge bg-raise/60 px-3 py-2">
      <span className="text-[11px] uppercase tracking-wider text-slate-500">{label}</span>
      <button
        type="button"
        onClick={() => onChange(!value)}
        className={`relative h-5 w-9 rounded-full transition-colors ${value ? "bg-accent" : "bg-slate-700"}`}
      >
        <span
          className={`absolute top-0.5 h-4 w-4 rounded-full bg-white transition-all ${
            value ? "left-[18px]" : "left-0.5"
          }`}
        />
      </button>
    </label>
  );
}

function ColorField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
}) {
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
