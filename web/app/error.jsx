"use client";

import { useEffect } from "react";

export default function ErrorPage({ error, reset }) {
  useEffect(() => {
    console.error("SM Terminal route error", error);
  }, [error]);

  return (
    <main className="login-shell" role="alert">
      <section className="login-card">
        <div className="login-mark">SM<span>_</span></div>
        <p className="eyebrow">MARKET TERMINAL / RECOVERY</p>
        <h1>Something went wrong</h1>
        <p className="muted">The terminal encountered an unexpected error. Your session and saved watchlist have not been cleared.</p>
        <button type="button" onClick={() => reset()}>RETRY TERMINAL →</button>
        {error?.digest ? <p className="login-foot">REFERENCE: {error.digest}</p> : null}
      </section>
    </main>
  );
}
