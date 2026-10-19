"use client";
import { useEffect, useState } from "react";

type Voice = { id: string; name: string; language: string; indic_samples: string[] };
type Lang = { code: string; name: string; indian: boolean };
type Job = { status: string; progress: number; message: string; result: { text?: string; model?: string; audio?: string } | null };

async function api<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  const body = await res.json().catch(() => ({}));
  if (res.status === 401) window.location.href = "/login";
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body as T;
}

// Start a job on the engine and poll until it finishes.
async function runJob(body: object, onProgress: (j: Job) => void): Promise<Job["result"]> {
  const { id } = await api<{ id: string }>("/api/jobs", { method: "POST", body: JSON.stringify(body) });
  for (;;) {
    await new Promise((r) => setTimeout(r, 2000));
    const job = await api<Job>(`/api/jobs/${id}`);
    onProgress(job);
    if (job.status === "done") return job.result;
    if (job.status === "error") throw new Error(job.message);
  }
}

const looksEnglish = (t: string) => {
  const letters = [...t].filter((c) => /\p{L}/u.test(c));
  return letters.length > 0 && letters.filter((c) => c.charCodeAt(0) < 128).length / letters.length > 0.5;
};

export default function Home() {
  const [voices, setVoices] = useState<Voice[]>([]);
  const [langs, setLangs] = useState<Lang[]>([]);
  const [studioUrl, setStudioUrl] = useState("");
  const [voice, setVoice] = useState("");
  const [lang, setLang] = useState("te");
  const [text, setText] = useState("");
  const [translated, setTranslated] = useState("");
  const [translatedFrom, setTranslatedFrom] = useState("");
  const [trModel, setTrModel] = useState("");
  const [expr, setExpr] = useState(0.5);
  const [pace, setPace] = useState(0.5);
  const [busy, setBusy] = useState("");
  const [progress, setProgress] = useState(0);
  const [error, setError] = useState("");
  const [audio, setAudio] = useState("");

  const load = () => {
    setError("");
    Promise.all([api<Voice[]>("/api/voices"), api<Lang[]>("/api/languages"), api<{ studioUrl: string }>("/api/config")])
      .then(([v, l, c]) => {
        setVoices(v);
        setLangs(l);
        setStudioUrl(c.studioUrl);
        if (v.length) setVoice((cur) => cur || v[0].id);
      })
      .catch((e) => setError(e.message));
  };
  useEffect(load, []);

  const langInfo = langs.find((l) => l.code === lang);
  const indian = !!langInfo?.indian;
  const selectedVoice = voices.find((v) => v.id === voice);

  async function translate(): Promise<string> {
    setBusy("Translating…");
    setProgress(0);
    const r = await runJob({ type: "translate", text, lang }, (j) => setProgress(j.progress));
    setTranslated(r?.text || "");
    setTranslatedFrom(text);
    setTrModel(r?.model || "");
    return r?.text || "";
  }

  async function wrap(fn: () => Promise<void>) {
    setError("");
    try { await fn(); } catch (e) { setError((e as Error).message); } finally { setBusy(""); }
  }

  const onTranslate = () => wrap(async () => { await translate(); });

  const onGenerate = () => wrap(async () => {
    let toSpeak = text;
    if (indian) {
      toSpeak = translated;
      if (looksEnglish(text) && (!translated.trim() || translatedFrom !== text)) toSpeak = await translate();
      if (!toSpeak.trim()) toSpeak = text;
    }
    setAudio("");
    setBusy("Generating audio…");
    setProgress(0);
    const r = await runJob(
      { type: "speak", text: toSpeak, voice, lang, exaggeration: expr, cfg_weight: pace },
      (j) => { setProgress(j.progress); setBusy(j.message || "Generating audio…"); });
    setAudio(r?.audio || "");
  });

  async function logout() {
    await fetch("/api/logout", { method: "POST" });
    window.location.href = "/login";
  }

  return (
    <main>
      <header>
        <h1>🎙️ myVoice</h1>
        <div className="row" style={{ flex: "0 0 auto", alignItems: "center" }}>
          {studioUrl && <a href={studioUrl} target="_blank" rel="noreferrer">Record / manage voices ↗</a>}
          <button onClick={logout}>Sign out</button>
        </div>
      </header>

      {error && (
        <div className="card error">
          {error} <button onClick={load} style={{ marginLeft: 8 }}>Retry</button>
        </div>
      )}

      <section className="card">
        <div className="row">
          <div>
            <label htmlFor="voice">Voice</label>
            <select id="voice" value={voice} onChange={(e) => setVoice(e.target.value)}>
              {voices.length === 0 && <option value="">No voices yet — create one in the studio</option>}
              {voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
            </select>
          </div>
          <div>
            <label htmlFor="lang">Language</label>
            <select id="lang" value={lang} onChange={(e) => setLang(e.target.value)}>
              {langs.map((l) => <option key={l.code} value={l.code}>{l.name}{l.indian ? " · Indian" : ""}</option>)}
            </select>
          </div>
        </div>
        {indian && selectedVoice && !selectedVoice.indic_samples.includes(lang) && (
          <p className="muted">
            Tip: record a short {langInfo?.name} sample for {selectedVoice.name} in the studio (Step 4) for a natural accent.
          </p>
        )}
      </section>

      <section className="card">
        <label htmlFor="text">{indian ? "English text (will be translated)" : "Text or podcast script"}</label>
        <textarea id="text" value={text} onChange={(e) => setText(e.target.value)}
          placeholder={"Paste any length of text.\n\nMulti-voice podcast: start lines with a voice name, e.g.\nRamesh: Welcome to the show!"} />

        {indian && (translated || busy === "Translating…") && (
          <div style={{ marginTop: 14 }}>
            <label htmlFor="translated">{langInfo?.name} text — review &amp; edit before generating</label>
            <textarea id="translated" value={translated} onChange={(e) => setTranslated(e.target.value)} />
            {trModel && <p className="muted">Translated with {trModel}. Fix anything that sounds unnatural.</p>}
            {translated && translatedFrom !== text && (
              <p className="muted">English changed since this translation — Generate will re-translate.</p>
            )}
          </div>
        )}

        {!indian && (
          <details style={{ marginTop: 12 }}>
            <summary>Delivery</summary>
            <div className="row" style={{ marginTop: 8 }}>
              <div>
                <label>Expressiveness: {expr.toFixed(2)}</label>
                <input type="range" min={0.25} max={2} step={0.05} value={expr} onChange={(e) => setExpr(+e.target.value)} />
              </div>
              <div>
                <label>Pace / guidance: {pace.toFixed(2)}</label>
                <input type="range" min={0} max={1} step={0.05} value={pace} onChange={(e) => setPace(+e.target.value)} />
              </div>
            </div>
          </details>
        )}

        <div className="actions">
          {indian && (
            <button onClick={onTranslate} disabled={!!busy || !text.trim()}>🌐 Translate to {langInfo?.name}</button>
          )}
          <button className="primary" onClick={onGenerate} disabled={!!busy || !voice || !(text.trim() || translated.trim())}>
            🔊 Generate
          </button>
        </div>

        {busy && (
          <div style={{ marginTop: 14 }}>
            <p className="muted">{busy} (long scripts take a few minutes)</p>
            <progress value={progress} max={1} />
          </div>
        )}
      </section>

      {audio && (
        <section className="card">
          <p className="ok">Listen and review your voice:</p>
          <audio controls src={audio} />
          <div className="actions"><a href={audio} download>⬇ Download MP3</a></div>
        </section>
      )}
    </main>
  );
}
