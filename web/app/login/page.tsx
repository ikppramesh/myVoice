"use client";
import { useState } from "react";

export default function Login() {
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true);
    setError("");
    const res = await fetch("/api/login", { method: "POST", body: JSON.stringify({ password }) });
    if (res.ok) window.location.href = "/";
    else { setError("Wrong password"); setBusy(false); }
  }

  return (
    <main style={{ maxWidth: 380, marginTop: "15vh" }}>
      <h1>🎙️ myVoice</h1>
      <form className="card" onSubmit={submit} style={{ marginTop: 16 }}>
        <label htmlFor="pw">Password</label>
        <input id="pw" type="password" autoFocus value={password} onChange={(e) => setPassword(e.target.value)} />
        <div className="actions"><button className="primary" disabled={busy || !password}>Sign in</button></div>
        {error && <p className="error">{error}</p>}
      </form>
    </main>
  );
}
