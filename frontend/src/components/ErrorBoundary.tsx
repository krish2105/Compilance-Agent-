import { AlertTriangle, RotateCw } from "lucide-react";
import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
}
interface State {
  error: Error | null;
}

/** Catches render errors anywhere below and shows a friendly recover screen
 * instead of a blank white page. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): State {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error("UI error:", error, info.componentStack);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return (
      <div
        role="alert"
        className="flex min-h-screen items-center justify-center p-6 text-center"
      >
        <div className="glass max-w-md p-8">
          <div className="mx-auto mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-danger/15 text-danger">
            <AlertTriangle size={26} />
          </div>
          <h1 className="text-lg font-bold text-ink">Something went wrong</h1>
          <p className="mt-2 text-sm text-ink-muted">
            The interface hit an unexpected error. Your data is safe — reloading usually fixes it.
          </p>
          <p className="mt-2 break-words font-mono text-[11px] text-ink-faint">
            {this.state.error.message}
          </p>
          <button onClick={() => window.location.reload()} className="btn-brand mx-auto mt-5">
            <RotateCw size={15} /> Reload
          </button>
        </div>
      </div>
    );
  }
}
