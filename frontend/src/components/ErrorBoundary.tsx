import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

// #14: error render → jangan blank putih. Tampilkan pesan + tombol reload.
export class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  render() {
    if (this.state.error) {
      return (
        <div className="flex min-h-[60vh] flex-col items-center justify-center gap-4 p-8 text-center">
          <div className="text-4xl">⚠️</div>
          <h1 className="font-display text-lg font-bold text-slate-100">Terjadi kesalahan</h1>
          <p className="max-w-md text-sm text-slate-400">{this.state.error.message}</p>
          <button
            className="rounded-lg border border-accent/40 bg-accent/10 px-4 py-2 text-sm font-semibold text-cyan-300 transition-colors hover:bg-accent/20"
            onClick={() => this.setState({ error: null })}
          >
            Coba lagi
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
