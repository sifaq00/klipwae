import { useEffect, useState } from "react";

// #22: ganti window.confirm (native, tak bisa di-theme, beku thread)
// → dialog inline yang konsisten sama UI app.
export function useConfirm() {
  const [state, setState] = useState<{ msg: string; resolve: (v: boolean) => void } | null>(null);

  const confirm = (msg: string) =>
    new Promise<boolean>((resolve) => setState({ msg, resolve }));

  const done = (v: boolean) => {
    state?.resolve(v);
    setState(null);
  };

  useEffect(() => {
    if (!state) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") done(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [state]);

  const dialog = state && (
    <div
      className="fixed inset-0 z-[70] flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
      onClick={() => done(false)}
    >
      <div
        className="animate-fadeUp w-full max-w-sm rounded-2xl border border-edge bg-panel p-5 shadow-2xl"
        onClick={(e) => e.stopPropagation()}
        role="alertdialog"
        aria-modal="true"
      >
        <p className="text-sm leading-relaxed text-slate-200">{state.msg}</p>
        <div className="mt-5 flex justify-end gap-2">
          <button
            className="rounded-lg border border-edge bg-raise/50 px-4 py-2 text-xs font-semibold text-slate-400 transition-colors hover:text-slate-200"
            onClick={() => done(false)}
          >
            Batal
          </button>
          <button
            className="rounded-lg border border-red-500/40 bg-red-500/15 px-4 py-2 text-xs font-semibold text-red-300 transition-colors hover:bg-red-500/25"
            onClick={() => done(true)}
          >
            Ya, lanjut
          </button>
        </div>
      </div>
    </div>
  );

  return { confirm, dialog };
}
