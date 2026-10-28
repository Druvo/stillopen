"use client";

import { Component, type ReactNode } from "react";

/**
 * One screen that fails must not take the whole page with it. This shows what happened in plain words with a way back, and keeps the
 * sidebar and the rest of the app usable. A changed `resetKey` (the person moved to another screen) clears the error.
 */
export class ScreenBoundary extends Component<{ children: ReactNode; resetKey: string }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: unknown) {
    console.error("A screen could not be shown:", error);
  }

  componentDidUpdate(prev: { resetKey: string }) {
    if (prev.resetKey !== this.props.resetKey && this.state.failed) this.setState({ failed: false });
  }

  render() {
    if (!this.state.failed) return this.props.children;
    return (
      <div role="alert" className="rounded-2xl border border-border bg-surface p-6">
        <h1 className="text-lg font-semibold">This screen could not be shown</h1>
        <p className="mt-2 text-theme-sm text-muted">
          Something unexpected happened here. Your data is safe. Try again, and if it keeps happening, reload the page; if the app was just
          updated, restart the server so it matches.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <button type="button" onClick={() => this.setState({ failed: false })} className="min-h-11 rounded-lg border border-border px-4 text-theme-sm font-medium sm:min-h-9">
            Try again
          </button>
          <button type="button" onClick={() => window.location.reload()} className="min-h-11 rounded-lg border border-border px-4 text-theme-sm font-medium sm:min-h-9">
            Reload the page
          </button>
        </div>
      </div>
    );
  }
}
