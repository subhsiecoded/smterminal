"use client";

import { useEffect } from "react";

export default function ErrorPage({ error, reset }) {
  useEffect(() => {
    console.error("SM Terminal route error", error);
  }, [error]);

  return (
    <main className="error-shell" role="alert">
      <section className="error-window">
        <div className="error-window-bar">
          <span className="error-lights"><i /><i /><i /></span>
          <span>SM TERMINAL / SYSTEM RECOVERY</span>
          <span className="error-bar-code">ERR / 500</span>
        </div>
        <div className="error-window-body">
          <div className="error-symbol" aria-hidden="true">!</div>
          <p className="eyebrow">APPLICATION RECOVERY</p>
          <h1>Terminal interrupted</h1>
          <p className="error-copy">
            A critical interface error prevented this view from rendering. Your browser-local watchlist has not been cleared.
          </p>
          {error?.digest ? (
            <div className="error-reference">
              <span>DIAGNOSTIC REFERENCE</span>
              <code>{error.digest}</code>
            </div>
          ) : null}
          <button type="button" onClick={() => reset()}>RETRY TERMINAL <span aria-hidden="true">→</span></button>
          <p className="error-foot">MARKET DATA MAY CONTINUE UPDATING AFTER THE VIEW RECOVERS</p>
        </div>
      </section>
    </main>
  );
}
