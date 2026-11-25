"use client";
import { useState } from "react";
export default function LoginForm() {
    const [password, setPassword] = useState("");
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);
    async function submit(event) {
        event.preventDefault();
        setBusy(true);
        setError("");
        try {
            const response = await fetch("/api/login", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ password })
            });
            const data = await response.json();
            if (!response.ok)
                throw new Error(data.detail || "Unable to sign in");
            window.location.assign("/");
        }
        catch (err) {
            setError(err instanceof Error ? err.message : "Unable to sign in");
        }
        finally {
            setBusy(false);
        }
    }
    return (<main className="login-shell">
      <form className="login-card" onSubmit={submit}>
        <div className="login-mark">SM<span>_</span></div>
        <p className="eyebrow">MARKET TERMINAL / ACCESS CONTROL</p>
        <h1>Terminal access</h1>
        <p className="muted">Enter the access password provided by the terminal owner.</p>
        <label htmlFor="terminal-password">ACCESS PASSWORD</label>
        <input id="terminal-password" type="password" autoComplete="current-password" value={password} onChange={(event) => setPassword(event.target.value)} required autoFocus/>
        {error && <p className="login-error">{error}</p>}
        <button type="submit" disabled={busy}>{busy ? "AUTHENTICATING…" : "CONNECT TO TERMINAL →"}</button>
        <p className="login-foot">PRIVATE MARKET-DATA WORKSPACE · READ-ONLY</p>
      </form>
    </main>);
}
